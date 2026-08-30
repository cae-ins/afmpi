"""Design-based variance, degrees of freedom and confidence intervals (PLAN.md §5, §14.4a-4c).

This module implements the Taylor branch of variance estimation: multi-stage designs,
FPC, PPS sampling and the five lonely-PSU policies.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import exp, isfinite, log, nan, sqrt
import warnings

import polars as pl
from scipy import stats

from .deprivation import (
    PI,
    PSU,
    STRATUM,
    fraction_column,
    psu_column,
    stratum_column,
)
from .pps import normalize_joint_probability
from .survey_design import SurveyDesign

CI_METHODS = ("normal", "t", "logit")

_CLUSTER_ROWS = "__afmpi_cluster_rows"


class LonelyPSUWarning(UserWarning):
    """Warning emitted when a stratum contains only a single PSU."""


@dataclass(frozen=True, slots=True)
class DesignDegrees:
    """Degrees of freedom of one design context, kept explicit (PLAN.md §6, §14.7).

    For Taylor designs: ``psus`` is total sampled clusters, ``strata`` is number
    of strata. For replication designs: ``psus`` holds ``R`` (number of replicates),
    ``strata`` holds number of variance strata ``H``, and ``lonely_strata`` is ``0``.

    Normative table of degrees of freedom per design case (PLAN.md §14.7):

    +--------------------------------------+------------------------------------------------------------------------+
    | Case                                 | df                                                                     |
    +======================================+========================================================================+
    | Single-stage design, stratified/not  | #PSU - #strata, counted on clusters/strata used by the domain          |
    +--------------------------------------+------------------------------------------------------------------------+
    | Multi-stage design                   | identical -- stage 1 only counts                                       |
    +--------------------------------------+------------------------------------------------------------------------+
    | Domain or subgroup                   | identical -- design clusters count, even if empty on domain            |
    +--------------------------------------+------------------------------------------------------------------------+
    | Lonely PSU, lonely_psu="certainty"   | stratum and its single cluster removed from both counts                |
    +--------------------------------------+------------------------------------------------------------------------+
    | Lonely PSU, "adjust"/"average"       | counted normally (net contribution zero)                               |
    +--------------------------------------+------------------------------------------------------------------------+
    | Lonely PSU, "collapse"               | counted on the merged stratification                                   |
    +--------------------------------------+------------------------------------------------------------------------+
    | PPS                                  | unchanged                                                              |
    +--------------------------------------+------------------------------------------------------------------------+
    | Replication                          | see §14.5a table (R - 1 or H)                                          |
    +--------------------------------------+------------------------------------------------------------------------+
    | Census                               | df = 0, no intervals                                                   |
    +--------------------------------------+------------------------------------------------------------------------+
    | Change over time                     | df of combined two-wave design                                         |
    +--------------------------------------+------------------------------------------------------------------------+
    | degf= provided                       | the provided value in all cases                                        |
    +--------------------------------------+------------------------------------------------------------------------+
    """

    psus: int
    strata: int
    lonely_strata: int = 0
    override_df: int | None = None
    lonely_strata_keys: tuple[str, ...] = ()

    @property
    def df(self) -> int:
        if self.override_df is not None:
            return self.override_df
        return self.psus - self.strata

    @property
    def estimable(self) -> bool:
        return self.lonely_strata == 0 and self.df >= 1


def design_degrees(clusters: pl.DataFrame) -> DesignDegrees:
    """Count the clusters and strata backing one domain."""

    in_domain = clusters.filter(pl.col(_CLUSTER_ROWS) > 0)
    psus = in_domain.select(pl.col(PSU).n_unique()).item() if in_domain.height else 0
    strata = in_domain.select(pl.col(STRATUM).n_unique()).item() if in_domain.height else 0
    sizes = clusters.group_by(STRATUM).agg(
        pl.col(PSU).n_unique().alias("m"),
        (pl.col(_CLUSTER_ROWS) > 0).any().alias("used"),
    )
    lonely_df = sizes.filter(pl.col("used") & (pl.col("m") < 2))
    lonely = lonely_df.height
    lonely_keys = tuple(str(k) for k in lonely_df.select(STRATUM).to_series().to_list())
    return DesignDegrees(
        psus=int(psus),
        strata=int(strata),
        lonely_strata=int(lonely),
        lonely_strata_keys=lonely_keys,
    )


def taylor_variance(
    clusters: pl.DataFrame,
    keys: tuple[str, ...],
    degrees: DesignDegrees,
) -> dict[str, float]:
    """Variance of every linearized estimand, single stage ultimate cluster."""

    if not degrees.estimable:
        return {key: nan for key in keys}

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


def design_variance(
    influence: pl.DataFrame,
    keys: tuple[str, ...],
    degrees: DesignDegrees,
    design: SurveyDesign,
) -> tuple[dict[str, float], DesignDegrees]:
    """Point of entry for design variance calculation, returning variances and degrees."""

    policy = design.lonely_psu
    stages = design.resolved_stages
    S = max(1, len(stages))

    sizes = influence.group_by(STRATUM).agg(
        pl.col(PSU).n_unique().alias("m"),
        (pl.col(_CLUSTER_ROWS) > 0).any().alias("used"),
    )
    used_sizes = sizes.filter(pl.col("used"))
    lonely_strata_keys = used_sizes.filter(pl.col("m") < 2).select(STRATUM).to_series().to_list()
    h2_strata_keys = used_sizes.filter(pl.col("m") >= 2).select(STRATUM).to_series().to_list()

    current_influence = influence
    res_degrees = degrees
    orig_lonely_keys = tuple(str(k) for k in lonely_strata_keys) if lonely_strata_keys else ()

    if lonely_strata_keys:
        if policy == "fail":
            warnings.warn(
                f"Stratum/strata {lonely_strata_keys} contain(s) a single PSU; lonely_psu='fail'",
                category=LonelyPSUWarning,
                stacklevel=2,
            )
            return {key: nan for key in keys}, DesignDegrees(
                degrees.psus, degrees.strata, len(lonely_strata_keys), degrees.override_df, orig_lonely_keys
            )

        elif policy == "certainty":
            # Exclude lonely strata from degrees counting
            without_lonely = current_influence.filter(~pl.col(STRATUM).is_in(lonely_strata_keys))
            res_degrees = design_degrees(without_lonely)
            res_degrees = DesignDegrees(
                res_degrees.psus, res_degrees.strata, res_degrees.lonely_strata, res_degrees.override_df, orig_lonely_keys
            )

        elif policy == "collapse":
            collapsed_key = "__afmpi_collapsed"
            cond = pl.col(STRATUM).is_in(lonely_strata_keys)
            current_influence = current_influence.with_columns(
                pl.when(cond).then(pl.lit(collapsed_key)).otherwise(pl.col(STRATUM)).alias(STRATUM)
            )
            m_collapsed = (
                current_influence.filter(pl.col(STRATUM) == collapsed_key)
                .select(pl.col(PSU).n_unique())
                .item()
            )
            if m_collapsed < 2:
                if h2_strata_keys:
                    h_min = sorted(h2_strata_keys)[0]
                    current_influence = current_influence.with_columns(
                        pl.when(pl.col(STRATUM) == collapsed_key)
                        .then(pl.lit(h_min))
                        .otherwise(pl.col(STRATUM))
                        .alias(STRATUM)
                    )
                else:
                    warnings.warn(
                        f"Collapse failed because H2 is empty; lonely_psu='fail'",
                        category=LonelyPSUWarning,
                        stacklevel=2,
                    )
                    return {key: nan for key in keys}, DesignDegrees(
                        degrees.psus, degrees.strata, len(lonely_strata_keys), degrees.override_df, orig_lonely_keys
                    )
            res_degrees = design_degrees(current_influence)
            lonely_strata_keys = []

        elif policy == "average" and not h2_strata_keys:
            warnings.warn(
                f"H2 is empty for lonely_psu='average'; falling back to 'fail'",
                category=LonelyPSUWarning,
                stacklevel=2,
            )
            return {key: nan for key in keys}, DesignDegrees(
                degrees.psus, degrees.strata, len(lonely_strata_keys), degrees.override_df, orig_lonely_keys
            )

    if orig_lonely_keys:
        res_degrees = DesignDegrees(
            res_degrees.psus, res_degrees.strata, res_degrees.lonely_strata, res_degrees.override_df, orig_lonely_keys
        )

    if design.pps is not None:
        v = _pps_variance(
            current_influence, keys, res_degrees, design, lonely_strata_keys, h2_strata_keys
        )
        return v, res_degrees

    v = multistage_variance(
        current_influence,
        keys,
        depth=S,
        lonely_psu=policy,
        lonely_strata_keys=lonely_strata_keys,
        h2_strata_keys=h2_strata_keys,
    )
    return v, res_degrees


def multistage_variance(
    influence: pl.DataFrame,
    keys: tuple[str, ...],
    *,
    depth: int,
    lonely_psu: str = "fail",
    lonely_strata_keys: list[str] | None = None,
    h2_strata_keys: list[str] | None = None,
) -> dict[str, float]:
    """Variance calculation supporting multi-stage and FPC."""

    if lonely_strata_keys is None:
        sizes = influence.group_by(STRATUM).agg(
            pl.col(PSU).n_unique().alias("m"),
            (pl.col(_CLUSTER_ROWS) > 0).any().alias("used"),
        )
        used_sizes = sizes.filter(pl.col("used"))
        lonely_strata_keys = used_sizes.filter(pl.col("m") < 2).select(STRATUM).to_series().to_list()
        h2_strata_keys = used_sizes.filter(pl.col("m") >= 2).select(STRATUM).to_series().to_list()

    undefined = influence.select(
        [pl.col(key).null_count().alias(key) for key in keys]
    ).row(0, named=True)

    units_df = influence
    final_stage_cells = None

    for s in range(depth, 0, -1):
        s_strat = stratum_column(s)
        s_psu = psu_column(s)
        s_frac = fraction_column(s)

        strat_aggs = [
            pl.len().alias("__m"),
            pl.col(s_frac).first().alias("__f"),
        ]
        if s > 1:
            strat_aggs.append(pl.col(psu_column(s - 1)).first().alias("__parent_psu"))
            strat_aggs.append(pl.col(stratum_column(s - 1)).first().alias("__parent_strat"))
            strat_aggs.append(pl.col(fraction_column(s - 1)).first().alias("__parent_frac"))

        for key in keys:
            strat_aggs.append(
                ((pl.col(key) - pl.col(key).mean()) ** 2).sum().alias(f"__ssd_{key}")
            )
            strat_aggs.append(pl.col(key).sum().alias(key))
            if s < depth:
                strat_aggs.append(pl.col(f"__child_term_{key}").sum().alias(f"__child_term_{key}"))

        group_s = units_df.group_by(s_strat).agg(strat_aggs)

        term_exprs = []
        for key in keys:
            v_expr = (
                pl.when(pl.col("__m") >= 2)
                .then(pl.col("__m").cast(pl.Float64) / (pl.col("__m").cast(pl.Float64) - 1.0) * pl.col(f"__ssd_{key}"))
                .otherwise(0.0)
            )
            if s == depth:
                term_expr = (1.0 - pl.col("__f")) * v_expr
            else:
                term_expr = (1.0 - pl.col("__f")) * v_expr + pl.col("__f") * pl.col(f"__child_term_{key}")
            term_exprs.append(term_expr.alias(f"__term_{key}"))

        stage_s_cells = group_s.with_columns(term_exprs)

        if s > 1:
            units_df = stage_s_cells.group_by("__parent_psu").agg(
                pl.col("__parent_strat").first().alias(stratum_column(s - 1)),
                pl.col("__parent_frac").first().alias(fraction_column(s - 1)),
                *[pl.col(key).sum().alias(key) for key in keys],
                *[pl.col(f"__term_{key}").sum().alias(f"__child_term_{key}") for key in keys],
            ).rename({"__parent_psu": psu_column(s - 1)})
        else:
            final_stage_cells = stage_s_cells

    res_dict: dict[str, float] = {}

    if lonely_strata_keys and lonely_psu in ("adjust", "average", "certainty"):
        tot_clusters = influence.select(pl.col(PSU).n_unique()).item()
        all_means = {
            key: float(influence.select(pl.col(key).sum()).item() or 0.0) / tot_clusters
            for key in keys
        }

        h2_vars = {key: 0.0 for key in keys}
        if lonely_psu == "average" and h2_strata_keys:
            h2_rows = final_stage_cells.filter(pl.col(STRATUM).is_in(h2_strata_keys))
            for key in keys:
                h2_vars[key] = float(h2_rows.select(pl.col(f"__term_{key}").sum()).item() or 0.0) / len(h2_strata_keys)

        for key in keys:
            val = 0.0
            for row in final_stage_cells.to_dicts():
                st = row[STRATUM]
                if st in lonely_strata_keys:
                    if lonely_psu == "certainty":
                        contrib = 0.0
                    elif lonely_psu == "adjust":
                        u_h1 = float(row[key] or 0.0)
                        contrib = (u_h1 - all_means[key]) ** 2
                    elif lonely_psu == "average":
                        contrib = h2_vars[key]
                    val += contrib
                else:
                    val += float(row[f"__term_{key}"] or 0.0)
            res_dict[key] = val
    else:
        for key in keys:
            total_val = float(final_stage_cells.select(pl.col(f"__term_{key}").sum()).item() or 0.0)
            res_dict[key] = total_val

    for key in keys:
        if undefined[key]:
            res_dict[key] = nan

    return res_dict


def _pps_variance(
    influence: pl.DataFrame,
    keys: tuple[str, ...],
    degrees: DesignDegrees,
    design: SurveyDesign,
    lonely_strata_keys: list[str],
    h2_strata_keys: list[str],
) -> dict[str, float]:
    """Variance calculation for PPS designs."""

    pps = design.pps
    assert pps is not None

    if pps.method == "with_replacement":
        # PPS with replacement (Hansen-Hurwitz estimator):
        # Under sampling with replacement with selection probabilities p_i, when analysis
        # weights w_i = 1 / (m * p_i) are passed, computing the single-stage ultimate cluster
        # variance on the weighted cluster influences u_hc = sum_{j in c} w_hcj * u_hcj yields
        # V_HH(Y_hat) = [m / (m - 1)] * sum_c (u_hc - u_bar_h)^2.
        # This is mathematically identical to the Hansen-Hurwitz variance estimator.
        return multistage_variance(
            influence,
            keys,
            depth=1,
            lonely_psu=design.lonely_psu,
            lonely_strata_keys=lonely_strata_keys,
            h2_strata_keys=h2_strata_keys,
        )

    var_method = pps.resolved_variance
    undefined = influence.select(
        [pl.col(key).null_count().alias(key) for key in keys]
    ).row(0, named=True)

    psu_sums = influence.group_by([STRATUM, PSU]).agg(
        pl.col(PI).first().alias("__pi"),
        pl.col(PSU).first().alias("__psu_str"),
        *[pl.col(key).sum().alias(key) for key in keys],
    )

    if var_method == "sen_yates_grundy":
        assert pps.joint_probability is not None
        jp = normalize_joint_probability(pps.joint_probability)
        has_stratum = "stratum" in jp.columns
        jp_dict: dict[tuple, float] = {}
        for row in jp.to_dicts():
            p = float(row["pi_ab"])
            if has_stratum:
                s, a, b = row["stratum"], row["psu_a"], row["psu_b"]
                jp_dict[(s, a, b)] = p
                jp_dict[(s, b, a)] = p
            else:
                a, b = row["psu_a"], row["psu_b"]
                jp_dict[(a, b)] = p
                jp_dict[(b, a)] = p

        res: dict[str, float] = {key: 0.0 for key in keys}

        for strat_key, strat_df in psu_sums.group_by(STRATUM):
            rows = strat_df.to_dicts()
            m_h = len(rows)
            if m_h < 2:
                pi_1 = float(rows[0]["__pi"])
                if pi_1 == 1.0 or design.lonely_psu == "certainty":
                    continue
                continue

            strat_raw = strat_key.split("|")[-1] if isinstance(strat_key, str) and "|" in strat_key else strat_key

            for key in keys:
                v_h = 0.0
                for i in range(m_h):
                    for j in range(m_h):
                        if i == j:
                            continue
                        c_row, d_row = rows[i], rows[j]
                        c_id = c_row["__psu_str"].split("|")[-1]
                        d_id = d_row["__psu_str"].split("|")[-1]

                        if has_stratum:
                            pair = (strat_raw, c_id, d_id)
                            if pair not in jp_dict:
                                pair = (c_row[STRATUM], c_id, d_id)
                        else:
                            pair = (c_id, d_id)

                        if pair not in jp_dict:
                            strat_ctx = f" in stratum {strat_raw!r}" if has_stratum else ""
                            raise ValueError(f"missing joint probability for pair ({c_id!r}, {d_id!r}){strat_ctx}")
                        pi_cd = jp_dict[pair]
                        pi_c = float(c_row["__pi"])
                        pi_d = float(d_row["__pi"])
                        t_c = float(c_row[key])
                        t_d = float(d_row[key])

                        coeff = (pi_cd - pi_c * pi_d) / pi_cd
                        v_h += -0.5 * coeff * ((t_c - t_d) ** 2)
                res[key] += v_h

        for key in keys:
            if undefined[key]:
                res[key] = nan
        return res

    elif var_method == "hajek":
        res = {key: 0.0 for key in keys}

        for strat, strat_df in psu_sums.group_by(STRATUM):
            rows = strat_df.to_dicts()
            m_h = len(rows)
            if m_h < 2:
                pi_1 = float(rows[0]["__pi"])
                if pi_1 == 1.0 or design.lonely_psu == "certainty":
                    continue
                continue

            s_denom = sum(1.0 - float(r["__pi"]) for r in rows)
            if s_denom == 0.0:
                continue

            for key in keys:
                t_star = sum((1.0 - float(r["__pi"])) * float(r[key]) for r in rows) / s_denom
                v_h = (m_h / (m_h - 1.0)) * sum(
                    (1.0 - float(r["__pi"])) * ((float(r[key]) - t_star) ** 2) for r in rows
                )
                res[key] += v_h

        for key in keys:
            if undefined[key]:
                res[key] = nan
        return res

    return {key: nan for key in keys}


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
    """Confidence interval for a proportion-like estimate."""

    if method not in CI_METHODS:
        raise ValueError(f"ci_method must be one of {CI_METHODS}; got {method!r}")
    if not 0 < level < 1:
        raise ValueError("level must be strictly between 0 and 1")
    if estimate is None or se is None or not isfinite(se):
        return (nan, nan)

    tail = 0.5 + level / 2
    if method == "normal":
        quantile = stats.norm.ppf(tail)
    else:
        if df < 1:
            return (nan, nan)
        quantile = float(stats.t.ppf(tail, df))

    if method == "logit":
        spread = estimate * (1.0 - estimate)
        if spread <= 0:
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


def taylor_vcov(
    clusters: pl.DataFrame,
    keys: tuple[str, ...],
    degrees: DesignDegrees,
) -> dict[tuple[str, str], float]:
    """VCOV matrix of every linearized estimand, single stage ultimate cluster."""

    if not degrees.estimable:
        return {(k1, k2): nan for k1 in keys for k2 in keys}

    undefined = clusters.select(
        [pl.col(key).null_count().alias(key) for key in keys]
    ).row(0, named=True)

    agg_exprs: list[pl.Expr] = []
    pairs: list[tuple[str, str]] = []
    for i, k1 in enumerate(keys):
        for j in range(i, len(keys)):
            k2 = keys[j]
            pairs.append((k1, k2))
            pair_name = f"__ssd_{i}_{j}"
            if k1 == k2:
                expr = ((pl.col(k1) - pl.col(k1).mean()) ** 2).sum()
            else:
                expr = ((pl.col(k1) - pl.col(k1).mean()) * (pl.col(k2) - pl.col(k2).mean())).sum()
            agg_exprs.append(expr.alias(pair_name))

    per_stratum = clusters.group_by(STRATUM).agg(
        pl.len().alias("__afmpi_m"),
        *agg_exprs,
    )

    cont_exprs: list[pl.Expr] = []
    for i, k1 in enumerate(keys):
        for j in range(i, len(keys)):
            pair_name = f"__ssd_{i}_{j}"
            cont_exprs.append(
                (
                    pl.col("__afmpi_m").cast(pl.Float64)
                    / (pl.col("__afmpi_m").cast(pl.Float64) - 1.0)
                    * pl.col(pair_name)
                )
                .sum()
                .alias(pair_name)
            )

    contributions = per_stratum.select(*cont_exprs).row(0, named=True)

    vcov: dict[tuple[str, str], float] = {}
    for i, k1 in enumerate(keys):
        for j in range(i, len(keys)):
            k2 = keys[j]
            pair_name = f"__ssd_{i}_{j}"
            value = contributions[pair_name]
            if undefined[k1] or undefined[k2] or value is None:
                val = nan
            else:
                val = float(value)
            vcov[(k1, k2)] = val
            vcov[(k2, k1)] = val

    return vcov


def design_vcov(
    influence: pl.DataFrame,
    keys: tuple[str, ...],
    degrees: DesignDegrees,
    design: SurveyDesign,
) -> tuple[dict[tuple[str, str], float], DesignDegrees]:
    """Point of entry for design VCOV calculation, returning VCOV dict and degrees."""

    policy = design.lonely_psu
    stages = design.resolved_stages
    S = max(1, len(stages))

    sizes = influence.group_by(STRATUM).agg(
        pl.col(PSU).n_unique().alias("m"),
        (pl.col(_CLUSTER_ROWS) > 0).any().alias("used"),
    )
    used_sizes = sizes.filter(pl.col("used"))
    lonely_strata_keys = used_sizes.filter(pl.col("m") < 2).select(STRATUM).to_series().to_list()
    h2_strata_keys = used_sizes.filter(pl.col("m") >= 2).select(STRATUM).to_series().to_list()

    current_influence = influence
    res_degrees = degrees
    orig_lonely_keys = tuple(str(k) for k in lonely_strata_keys) if lonely_strata_keys else ()

    if lonely_strata_keys:
        if policy == "fail":
            warnings.warn(
                f"Stratum/strata {lonely_strata_keys} contain(s) a single PSU; lonely_psu='fail'",
                category=LonelyPSUWarning,
                stacklevel=2,
            )
            return {(k1, k2): nan for k1 in keys for k2 in keys}, DesignDegrees(
                degrees.psus, degrees.strata, len(lonely_strata_keys), degrees.override_df, orig_lonely_keys
            )

        elif policy == "certainty":
            without_lonely = current_influence.filter(~pl.col(STRATUM).is_in(lonely_strata_keys))
            res_degrees = design_degrees(without_lonely)
            res_degrees = DesignDegrees(
                res_degrees.psus, res_degrees.strata, res_degrees.lonely_strata, res_degrees.override_df, orig_lonely_keys
            )

        elif policy == "collapse":
            collapsed_key = "__afmpi_collapsed"
            cond = pl.col(STRATUM).is_in(lonely_strata_keys)
            current_influence = current_influence.with_columns(
                pl.when(cond).then(pl.lit(collapsed_key)).otherwise(pl.col(STRATUM)).alias(STRATUM)
            )
            m_collapsed = (
                current_influence.filter(pl.col(STRATUM) == collapsed_key)
                .select(pl.col(PSU).n_unique())
                .item()
            )
            if m_collapsed < 2:
                if h2_strata_keys:
                    h_min = sorted(h2_strata_keys)[0]
                    current_influence = current_influence.with_columns(
                        pl.when(pl.col(STRATUM) == collapsed_key)
                        .then(pl.lit(h_min))
                        .otherwise(pl.col(STRATUM))
                        .alias(STRATUM)
                    )
                else:
                    warnings.warn(
                        f"Collapse failed because H2 is empty; lonely_psu='fail'",
                        category=LonelyPSUWarning,
                        stacklevel=2,
                    )
                    return {(k1, k2): nan for k1 in keys for k2 in keys}, DesignDegrees(
                        degrees.psus, degrees.strata, len(lonely_strata_keys), degrees.override_df, orig_lonely_keys
                    )
            res_degrees = design_degrees(current_influence)
            lonely_strata_keys = []

        elif policy == "average" and not h2_strata_keys:
            warnings.warn(
                f"H2 is empty for lonely_psu='average'; falling back to 'fail'",
                category=LonelyPSUWarning,
                stacklevel=2,
            )
            return {(k1, k2): nan for k1 in keys for k2 in keys}, DesignDegrees(
                degrees.psus, degrees.strata, len(lonely_strata_keys), degrees.override_df, orig_lonely_keys
            )

    if orig_lonely_keys:
        res_degrees = DesignDegrees(
            res_degrees.psus, res_degrees.strata, res_degrees.lonely_strata, res_degrees.override_df, orig_lonely_keys
        )

    if design.pps is not None:
        v = _pps_vcov(
            current_influence, keys, res_degrees, design, lonely_strata_keys, h2_strata_keys
        )
        return v, res_degrees

    v = multistage_vcov(
        current_influence,
        keys,
        depth=S,
        lonely_psu=policy,
        lonely_strata_keys=lonely_strata_keys,
        h2_strata_keys=h2_strata_keys,
    )
    return v, res_degrees


def multistage_vcov(
    influence: pl.DataFrame,
    keys: tuple[str, ...],
    *,
    depth: int,
    lonely_psu: str = "fail",
    lonely_strata_keys: list[str] | None = None,
    h2_strata_keys: list[str] | None = None,
) -> dict[tuple[str, str], float]:
    """VCOV calculation supporting multi-stage and FPC."""

    if lonely_strata_keys is None:
        sizes = influence.group_by(STRATUM).agg(
            pl.col(PSU).n_unique().alias("m"),
            (pl.col(_CLUSTER_ROWS) > 0).any().alias("used"),
        )
        used_sizes = sizes.filter(pl.col("used"))
        lonely_strata_keys = used_sizes.filter(pl.col("m") < 2).select(STRATUM).to_series().to_list()
        h2_strata_keys = used_sizes.filter(pl.col("m") >= 2).select(STRATUM).to_series().to_list()

    undefined = influence.select(
        [pl.col(key).null_count().alias(key) for key in keys]
    ).row(0, named=True)

    units_df = influence
    final_stage_cells = None

    pairs: list[tuple[str, str]] = []
    for i, k1 in enumerate(keys):
        for j in range(i, len(keys)):
            pairs.append((k1, keys[j]))

    for s in range(depth, 0, -1):
        s_strat = stratum_column(s)
        s_psu = psu_column(s)
        s_frac = fraction_column(s)

        strat_aggs = [
            pl.len().alias("__m"),
            pl.col(s_frac).first().alias("__f"),
        ]
        if s > 1:
            strat_aggs.append(pl.col(psu_column(s - 1)).first().alias("__parent_psu"))
            strat_aggs.append(pl.col(stratum_column(s - 1)).first().alias("__parent_strat"))
            strat_aggs.append(pl.col(fraction_column(s - 1)).first().alias("__parent_frac"))

        for key in keys:
            strat_aggs.append(pl.col(key).sum().alias(key))

        for idx, (k1, k2) in enumerate(pairs):
            pair_tag = f"{idx}"
            if k1 == k2:
                ssd_expr = ((pl.col(k1) - pl.col(k1).mean()) ** 2).sum()
            else:
                ssd_expr = ((pl.col(k1) - pl.col(k1).mean()) * (pl.col(k2) - pl.col(k2).mean())).sum()
            strat_aggs.append(ssd_expr.alias(f"__ssd_{pair_tag}"))
            if s < depth:
                strat_aggs.append(pl.col(f"__child_term_{pair_tag}").sum().alias(f"__child_term_{pair_tag}"))

        group_s = units_df.group_by(s_strat).agg(strat_aggs)

        term_exprs = []
        for idx, (k1, k2) in enumerate(pairs):
            pair_tag = f"{idx}"
            v_expr = (
                pl.when(pl.col("__m") >= 2)
                .then(pl.col("__m").cast(pl.Float64) / (pl.col("__m").cast(pl.Float64) - 1.0) * pl.col(f"__ssd_{pair_tag}"))
                .otherwise(0.0)
            )
            if s == depth:
                term_expr = (1.0 - pl.col("__f")) * v_expr
            else:
                term_expr = (1.0 - pl.col("__f")) * v_expr + pl.col("__f") * pl.col(f"__child_term_{pair_tag}")
            term_exprs.append(term_expr.alias(f"__term_{pair_tag}"))

        stage_s_cells = group_s.with_columns(term_exprs)

        if s > 1:
            units_df = stage_s_cells.group_by("__parent_psu").agg(
                pl.col("__parent_strat").first().alias(stratum_column(s - 1)),
                pl.col("__parent_frac").first().alias(fraction_column(s - 1)),
                *[pl.col(key).sum().alias(key) for key in keys],
                *[pl.col(f"__term_{idx}").sum().alias(f"__child_term_{idx}") for idx in range(len(pairs))],
            ).rename({"__parent_psu": psu_column(s - 1)})
        else:
            final_stage_cells = stage_s_cells

    res_dict: dict[tuple[str, str], float] = {}

    if lonely_strata_keys and lonely_psu in ("adjust", "average", "certainty"):
        tot_clusters = influence.select(pl.col(PSU).n_unique()).item()
        all_means = {
            key: float(influence.select(pl.col(key).sum()).item() or 0.0) / tot_clusters
            for key in keys
        }

        h2_vars = {pair: 0.0 for pair in pairs}
        if lonely_psu == "average" and h2_strata_keys:
            h2_rows = final_stage_cells.filter(pl.col(STRATUM).is_in(h2_strata_keys))
            for idx, (k1, k2) in enumerate(pairs):
                h2_vars[(k1, k2)] = float(h2_rows.select(pl.col(f"__term_{idx}").sum()).item() or 0.0) / len(h2_strata_keys)

        for idx, (k1, k2) in enumerate(pairs):
            val = 0.0
            for row in final_stage_cells.to_dicts():
                st = row[STRATUM]
                if st in lonely_strata_keys:
                    if lonely_psu == "certainty":
                        contrib = 0.0
                    elif lonely_psu == "adjust":
                        u_h1_k1 = float(row[k1] or 0.0)
                        u_h1_k2 = float(row[k2] or 0.0)
                        contrib = (u_h1_k1 - all_means[k1]) * (u_h1_k2 - all_means[k2])
                    elif lonely_psu == "average":
                        contrib = h2_vars[(k1, k2)]
                    val += contrib
                else:
                    val += float(row[f"__term_{idx}"] or 0.0)
            res_dict[(k1, k2)] = val
            res_dict[(k2, k1)] = val
    else:
        for idx, (k1, k2) in enumerate(pairs):
            total_val = float(final_stage_cells.select(pl.col(f"__term_{idx}").sum()).item() or 0.0)
            res_dict[(k1, k2)] = total_val
            res_dict[(k2, k1)] = total_val

    for k1 in keys:
        for k2 in keys:
            if undefined[k1] or undefined[k2]:
                res_dict[(k1, k2)] = nan

    return res_dict


def _pps_vcov(
    influence: pl.DataFrame,
    keys: tuple[str, ...],
    degrees: DesignDegrees,
    design: SurveyDesign,
    lonely_strata_keys: list[str],
    h2_strata_keys: list[str],
) -> dict[tuple[str, str], float]:
    """VCOV calculation for PPS designs."""

    pps = design.pps
    assert pps is not None

    if pps.method == "with_replacement":
        return multistage_vcov(
            influence,
            keys,
            depth=1,
            lonely_psu=design.lonely_psu,
            lonely_strata_keys=lonely_strata_keys,
            h2_strata_keys=h2_strata_keys,
        )

    var_method = pps.resolved_variance
    undefined = influence.select(
        [pl.col(key).null_count().alias(key) for key in keys]
    ).row(0, named=True)

    psu_sums = influence.group_by([STRATUM, PSU]).agg(
        pl.col(PI).first().alias("__pi"),
        pl.col(PSU).first().alias("__psu_str"),
        *[pl.col(key).sum().alias(key) for key in keys],
    )

    pairs: list[tuple[str, str]] = [(k1, keys[j]) for i, k1 in enumerate(keys) for j in range(i, len(keys))]

    if var_method == "sen_yates_grundy":
        assert pps.joint_probability is not None
        jp = normalize_joint_probability(pps.joint_probability)
        has_stratum = "stratum" in jp.columns
        jp_dict: dict[tuple, float] = {}
        for row in jp.to_dicts():
            p = float(row["pi_ab"])
            if has_stratum:
                s, a, b = row["stratum"], row["psu_a"], row["psu_b"]
                jp_dict[(s, a, b)] = p
                jp_dict[(s, b, a)] = p
            else:
                a, b = row["psu_a"], row["psu_b"]
                jp_dict[(a, b)] = p
                jp_dict[(b, a)] = p

        res: dict[tuple[str, str], float] = {(k1, k2): 0.0 for k1 in keys for k2 in keys}

        for strat_key, strat_df in psu_sums.group_by(STRATUM):
            rows = strat_df.to_dicts()
            m_h = len(rows)
            if m_h < 2:
                pi_1 = float(rows[0]["__pi"])
                if pi_1 == 1.0 or design.lonely_psu == "certainty":
                    continue
                continue

            strat_raw = strat_key.split("|")[-1] if isinstance(strat_key, str) and "|" in strat_key else strat_key

            for k1, k2 in pairs:
                v_h = 0.0
                for i in range(m_h):
                    for j in range(m_h):
                        if i == j:
                            continue
                        c_row, d_row = rows[i], rows[j]
                        c_id = c_row["__psu_str"].split("|")[-1]
                        d_id = d_row["__psu_str"].split("|")[-1]

                        if has_stratum:
                            pair = (strat_raw, c_id, d_id)
                            if pair not in jp_dict:
                                pair = (c_row[STRATUM], c_id, d_id)
                        else:
                            pair = (c_id, d_id)

                        if pair not in jp_dict:
                            strat_ctx = f" in stratum {strat_raw!r}" if has_stratum else ""
                            raise ValueError(f"missing joint probability for pair ({c_id!r}, {d_id!r}){strat_ctx}")
                        pi_cd = jp_dict[pair]
                        pi_c = float(c_row["__pi"])
                        pi_d = float(d_row["__pi"])
                        t_c_k1, t_d_k1 = float(c_row[k1]), float(d_row[k1])
                        t_c_k2, t_d_k2 = float(c_row[k2]), float(d_row[k2])

                        coeff = (pi_cd - pi_c * pi_d) / pi_cd
                        v_h += -0.5 * coeff * (t_c_k1 - t_d_k1) * (t_c_k2 - t_d_k2)
                res[(k1, k2)] += v_h
                res[(k2, k1)] += v_h

        for k1 in keys:
            for k2 in keys:
                if undefined[k1] or undefined[k2]:
                    res[(k1, k2)] = nan
        return res

    elif var_method == "hajek":
        res = {(k1, k2): 0.0 for k1 in keys for k2 in keys}

        for strat, strat_df in psu_sums.group_by(STRATUM):
            rows = strat_df.to_dicts()
            m_h = len(rows)
            if m_h < 2:
                pi_1 = float(rows[0]["__pi"])
                if pi_1 == 1.0 or design.lonely_psu == "certainty":
                    continue
                continue

            s_denom = sum(1.0 - float(r["__pi"]) for r in rows)
            if s_denom == 0.0:
                continue

            for k1, k2 in pairs:
                t_star_k1 = sum((1.0 - float(r["__pi"])) * float(r[k1]) for r in rows) / s_denom
                t_star_k2 = sum((1.0 - float(r["__pi"])) * float(r[k2]) for r in rows) / s_denom
                v_h = (m_h / (m_h - 1.0)) * sum(
                    (1.0 - float(r["__pi"])) * (float(r[k1]) - t_star_k1) * (float(r[k2]) - t_star_k2)
                    for r in rows
                )
                res[(k1, k2)] += v_h
                res[(k2, k1)] += v_h

        for k1 in keys:
            for k2 in keys:
                if undefined[k1] or undefined[k2]:
                    res[(k1, k2)] = nan
        return res

    return {(k1, k2): nan for k1 in keys for k2 in keys}


__all__ = [
    "CI_METHODS",
    "DesignDegrees",
    "LonelyPSUWarning",
    "PSU",
    "STRATUM",
    "coefficient_of_variation",
    "confidence_interval",
    "design_degrees",
    "design_variance",
    "design_vcov",
    "multistage_variance",
    "multistage_vcov",
    "standard_error",
    "taylor_variance",
    "taylor_vcov",
]

