"""Taylor linearization: influence functions for ratio estimands (PLAN.md §5).

This module feeds :class:`~afmpi.survey_design.SurveyDesign` and nothing else.
Replication designs do *not* linearize -- they re-evaluate the estimand compiler
once per replicate weight -- so no code here is shared with that path.

For a ratio of two weighted totals

.. code-block:: text

    R = Y / X,   Y = sum_i(n_i y_i),   X = sum_i(n_i x_i)

the influence (linearized) value of observation ``i`` is

.. code-block:: text

    u_i = n_i (y_i - R x_i) / X

so that ``R`` behaves, to first order, like the *total* ``sum_i u_i`` plus a
constant. Any design-based variance estimator for a total can then be applied to
``u_i`` unchanged: that is what makes the variance composable rather than one
bespoke formula per estimand. Two properties hold by construction and are
asserted in the tests:

* ``sum_i u_i = 0`` exactly;
* a small perturbation of one weight, ``n_i -> n_i + d``, moves ``R`` by
  ``d * (y_i - R x_i) / X = d * u_i / n_i`` to first order.

Because ``R`` and ``X`` are scalars computed in a first pass over the data, the
per-cluster influence can be obtained from per-cluster sums of ``n*y`` and
``n*x`` rather than from row-level values:

.. code-block:: text

    u_hc = sum_{i in hc} u_i = (SY_hc - R * SX_hc) / X

:func:`cluster_influence` uses that identity, which is what lets the variance
stage collapse tens of millions of rows to a few thousand clusters before doing
any statistical work (§7). :func:`influence` keeps the row-level form, which is
what the tests check the aggregated path against.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Sequence

import polars as pl

from .deprivation import PSU, STRATUM, WEIGHT
from .estimands import RatioEstimand

_NUMERATOR_PREFIX = "__afmpi_y::"
_DENOMINATOR_PREFIX = "__afmpi_x::"


@dataclass(frozen=True, slots=True)
class RatioTotals:
    """The two weighted totals behind one ratio estimand, and their ratio."""

    estimand: RatioEstimand
    numerator: float
    denominator: float

    @property
    def key(self) -> str:
        return self.estimand.key

    @property
    def value(self) -> float | None:
        """``R = Y / X``, or ``None`` when the denominator is not positive."""

        if not isfinite(self.denominator) or self.denominator <= 0:
            return None
        return self.numerator / self.denominator


def _totals_exprs(
    estimands: Sequence[RatioEstimand],
    weight: pl.Expr | str | None = None,
) -> list[pl.Expr]:
    n = pl.col(WEIGHT) if weight is None else (pl.col(weight) if isinstance(weight, str) else weight)
    exprs: list[pl.Expr] = []
    for item in estimands:
        exprs.append((n * item.y).sum().alias(_NUMERATOR_PREFIX + item.key))
    for item in estimands:
        exprs.append((n * item.x).sum().alias(_DENOMINATOR_PREFIX + item.key))
    return exprs


def totals_lazy(
    lf: pl.LazyFrame,
    estimands: Sequence[RatioEstimand],
    weight: pl.Expr | str | None = None,
) -> pl.LazyFrame:
    """First pass (lazy): select weighted totals Y and X of every estimand."""

    return lf.select(_totals_exprs(estimands, weight))


def totals(
    frame: pl.DataFrame,
    estimands: tuple[RatioEstimand, ...],
    weight: pl.Expr | None = None,
) -> tuple[RatioTotals, ...]:
    """First pass: the weighted totals ``Y`` and ``X`` of every estimand."""

    aggregated = totals_lazy(frame.lazy(), estimands, weight=weight).collect().row(0, named=True)
    return tuple(
        RatioTotals(
            estimand=item,
            numerator=float(aggregated[_NUMERATOR_PREFIX + item.key] or 0.0),
            denominator=float(aggregated[_DENOMINATOR_PREFIX + item.key] or 0.0),
        )
        for item in estimands
    )


def influence_expressions(
    ratios: tuple[RatioTotals, ...],
    weight: pl.Expr | None = None,
) -> list[pl.Expr]:
    """Row-level ``u_i`` for each ratio, aliased by the estimand key."""

    n = pl.col(WEIGHT) if weight is None else weight
    expressions: list[pl.Expr] = []
    for ratio in ratios:
        value = ratio.value
        if value is None:
            expressions.append(pl.lit(None, dtype=pl.Float64).alias(ratio.key))
            continue
        estimand = ratio.estimand
        expressions.append(
            (n * (estimand.y - pl.lit(value) * estimand.x) / pl.lit(ratio.denominator)).alias(
                ratio.key
            )
        )
    return expressions


def influence(
    frame: pl.DataFrame,
    ratios: tuple[RatioTotals, ...],
    weight: pl.Expr | None = None,
) -> pl.DataFrame:
    """Second pass, row level: one column of ``u_i`` per estimand."""

    return frame.select(influence_expressions(ratios, weight))


def _cluster_sums_exprs(
    estimands: Sequence[RatioEstimand],
    weight: pl.Expr | str | None = None,
) -> list[pl.Expr]:
    n = pl.col(WEIGHT) if weight is None else (pl.col(weight) if isinstance(weight, str) else weight)
    return [
        *_totals_exprs(estimands, n),
        n.sum().alias("__afmpi_cluster_weight"),
        (n > 0).sum().alias("__afmpi_cluster_rows"),
    ]


def cluster_sums_lazy(
    lf: pl.LazyFrame,
    estimands: Sequence[RatioEstimand],
    weight: pl.Expr | str | None = None,
    group_columns: Sequence[str] = (STRATUM, PSU),
) -> pl.LazyFrame:
    """Collapse the sample to one row per cluster (lazy)."""

    return lf.group_by(list(group_columns)).agg(_cluster_sums_exprs(estimands, weight))


def cluster_sums(
    frame: pl.DataFrame,
    estimands: tuple[RatioEstimand, ...],
    weight: pl.Expr | None = None,
    group_columns: tuple[str, ...] = (STRATUM, PSU),
) -> pl.DataFrame:
    """Collapse the sample to one row per cluster, keeping ``n*y`` and ``n*x``."""

    return cluster_sums_lazy(frame.lazy(), estimands, weight=weight, group_columns=group_columns).collect()


def cluster_influence(
    sums: pl.DataFrame,
    ratios: tuple[RatioTotals, ...],
) -> pl.DataFrame:
    """Per-cluster influence ``u_hc = (SY_hc - R * SX_hc) / X``."""

    expressions: list[pl.Expr] = []
    for ratio in ratios:
        value = ratio.value
        if value is None:
            expressions.append(pl.lit(None, dtype=pl.Float64).alias(ratio.key))
            continue
        expressions.append(
            (
                (
                    pl.col(_NUMERATOR_PREFIX + ratio.key)
                    - pl.lit(value) * pl.col(_DENOMINATOR_PREFIX + ratio.key)
                )
                / pl.lit(ratio.denominator)
            ).alias(ratio.key)
        )
    keep = [
        column
        for column in sums.columns
        if not column.startswith((_NUMERATOR_PREFIX, _DENOMINATOR_PREFIX))
    ]
    return sums.select(*keep, *expressions)


def totals_from_clusters(
    sums: pl.DataFrame,
    estimands: tuple[RatioEstimand, ...],
) -> tuple[RatioTotals, ...]:
    """Recover the global totals from the collapsed table."""

    aggregated = sums.select(
        [pl.col(_NUMERATOR_PREFIX + item.key).sum() for item in estimands]
        + [pl.col(_DENOMINATOR_PREFIX + item.key).sum() for item in estimands]
    ).row(0, named=True)
    return tuple(
        RatioTotals(
            estimand=item,
            numerator=float(aggregated[_NUMERATOR_PREFIX + item.key] or 0.0),
            denominator=float(aggregated[_DENOMINATOR_PREFIX + item.key] or 0.0),
        )
        for item in estimands
    )
