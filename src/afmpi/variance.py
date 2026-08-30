"""Design-based variance, degrees of freedom and confidence intervals.

This module implements the **Taylor** branch of PLAN.md §5 only: it consumes the
linearized values produced by :mod:`afmpi.linearization` and never re-evaluates
an estimand. The replication branch (phase 5) will produce its own variance from
the dispersion of re-estimated replicates and share only the result interface.

Variance estimator (single stage, ultimate cluster, clusters drawn with
replacement)::

    V = sum_h [ m_h / (m_h - 1) * sum_c (u_hc - mean_h(u))^2 ]

where ``u_hc`` is the influence of the sample summed over cluster ``c`` of
stratum ``h`` and ``m_h`` is the number of sampled clusters in that stratum.
With a single stratum ``mean_h(u) = 0`` exactly, because ``sum_i u_i = 0``, and
the formula collapses to ``m/(m-1) * sum_c u_c^2`` -- the estimator used by
``PythonIPM/pipeline/05_indices_ipm.py::ratio_et_ic``, which is therefore
reproduced exactly rather than approximated.

Finite population corrections, several stages, PPS and the five lonely-PSU
behaviours are deliberately out of scope here; see PLAN.md §9 phases 4a-4c.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import exp, isfinite, log, nan, sqrt
from statistics import NormalDist

import polars as pl
from scipy import stats

from .deprivation import PSU, STRATUM

CI_METHODS = ("normal", "t", "logit")

_CLUSTER_ROWS = "__afmpi_cluster_rows"


@dataclass(frozen=True, slots=True)
class DesignDegrees:
    """Degrees of freedom of one design context, kept explicit (PLAN.md §6).

    ``df = psus - strata`` is *one* convention, and it is the one implemented
    here. It is a first-class, inspectable object precisely because two
    implementations can agree on the point estimate and the standard error and
    still disagree on the interval through the degrees of freedom alone.

    For a domain the counts are those of the clusters and strata that actually
    contain domain observations, while the variance itself is computed over the
    whole design -- the same rule as ``degf()`` applied to a subset design in
    the R ``survey`` package.
    """

    psus: int
    strata: int
    lonely_strata: int

    @property
    def df(self) -> int:
        return self.psus - self.strata

    @property
    def estimable(self) -> bool:
        return self.lonely_strata == 0 and self.df >= 1


def design_degrees(clusters: pl.DataFrame) -> DesignDegrees:
    """Count the clusters and strata backing one domain."""

    in_domain = clusters.filter(pl.col(_CLUSTER_ROWS) > 0)
    psus = in_domain.height
    strata = in_domain.select(pl.col(STRATUM).n_unique()).item() if psus else 0
    sizes = clusters.group_by(STRATUM).agg(
        pl.len().alias("m"),
        (pl.col(_CLUSTER_ROWS) > 0).any().alias("used"),
    )
    lonely = sizes.filter(pl.col("used") & (pl.col("m") < 2)).height
    return DesignDegrees(psus=psus, strata=int(strata), lonely_strata=int(lonely))


def taylor_variance(
    clusters: pl.DataFrame,
    keys: tuple[str, ...],
    degrees: DesignDegrees,
) -> dict[str, float]:
    """Variance of every linearized estimand, from the collapsed cluster table.

    ``clusters`` holds one row per (stratum, PSU) with the influence value of
    each estimand summed over the cluster, as produced by
    :func:`afmpi.linearization.cluster_influence`.
    """

    if not degrees.estimable:
        # A stratum with a single sampled cluster leaves the variance
        # unidentified. Reporting nothing is the honest answer; inventing a
        # value is not. The five documented alternatives (fail, certainty,
        # adjust, average, collapse) belong to phase 4c.
        return {key: nan for key in keys}

    # An estimand whose ratio was undefined carries no influence value at all.
    # Polars skips nulls when summing, which would quietly turn "not measurable"
    # into a variance of zero, so those keys are answered explicitly.
    undefined = clusters.select(
        [pl.col(key).null_count().alias(key) for key in keys]
    ).row(0, named=True)

    per_stratum = clusters.group_by(STRATUM).agg(
        pl.len().alias("__afmpi_m"),
        *[((pl.col(key) - pl.col(key).mean()) ** 2).sum().alias(key) for key in keys],
    )
    contributions = per_stratum.select(
        *[
            (
                pl.col("__afmpi_m").cast(pl.Float64)
                / (pl.col("__afmpi_m").cast(pl.Float64) - 1.0)
                * pl.col(key)
            )
            .sum()
            .alias(key)
            for key in keys
        ]
    ).row(0, named=True)

    variances: dict[str, float] = {}
    for key in keys:
        value = contributions[key]
        if undefined[key] or value is None:
            variances[key] = nan
        else:
            variances[key] = float(value)
    return variances


def standard_error(variance: float) -> float:
    """Square root of a variance, tolerant of the not-estimable case."""

    if variance is None or not isfinite(variance) or variance < 0:
        return nan
    return sqrt(variance)


def confidence_interval(
    estimate: float | None,
    se: float,
    df: int,
    *,
    method: str = "logit",
    level: float = 0.95,
    bounded: bool = True,
) -> tuple[float, float]:
    """Confidence interval for a proportion-like estimate.

    ``normal`` and ``t`` build a symmetric interval and, when ``bounded``, clip
    it to ``[0, 1]``; that is the truncation convention of
    ``PythonIPM``. ``logit`` builds the interval on the logit scale and maps it
    back, so the bounds are respected by construction rather than by clipping;
    that is the convention of ``svyciprop()`` in R, used by ``mpitb``. PLAN.md §4
    asks for both, and for the choice to be the caller's.
    """

    if method not in CI_METHODS:
        raise ValueError(f"ci_method must be one of {CI_METHODS}; got {method!r}")
    if not 0 < level < 1:
        raise ValueError("level must be strictly between 0 and 1")
    if estimate is None or se is None or not isfinite(se):
        return (nan, nan)

    tail = 0.5 + level / 2
    if method == "normal":
        quantile = NormalDist().inv_cdf(tail)
    else:
        if df < 1:
            return (nan, nan)
        quantile = float(stats.t.ppf(tail, df))

    if method == "logit":
        spread = estimate * (1.0 - estimate)
        if spread <= 0:
            # On a boundary the logit transform is undefined; fall back to the
            # truncated interval rather than returning a degenerate point.
            return _clip(estimate - quantile * se, estimate + quantile * se, bounded)
        centre = log(estimate / (1.0 - estimate))
        margin = quantile * se / spread
        return (_expit(centre - margin), _expit(centre + margin))

    margin = quantile * se
    return _clip(estimate - margin, estimate + margin, bounded)


def coefficient_of_variation(estimate: float | None, se: float) -> float:
    """``se / estimate``, the usual relative-precision diagnostic."""

    if estimate is None or not isfinite(se) or estimate == 0:
        return nan
    return se / estimate


def _clip(lower: float, upper: float, bounded: bool) -> tuple[float, float]:
    if not bounded:
        return (lower, upper)
    return (max(lower, 0.0), min(upper, 1.0))


def _expit(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + exp(-value))
    exponential = exp(value)
    return exponential / (1.0 + exponential)


__all__ = [
    "CI_METHODS",
    "DesignDegrees",
    "PSU",
    "STRATUM",
    "coefficient_of_variation",
    "confidence_interval",
    "design_degrees",
    "standard_error",
    "taylor_variance",
]
