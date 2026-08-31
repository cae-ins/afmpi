"""Estimand compiler: the point-estimate function ``T(.)`` (PLAN.md §5).

Every Alkire-Foster quantity this package reports is a ratio of two weighted
totals::

    R = sum_i(n_i * y_i) / sum_i(n_i * x_i)

That is the single structural fact the whole inference stage rests on. ``H`` and
``M0`` happen to have ``x_i = 1`` and are therefore weighted means, but ``A``
and the relative contributions ``pctb_j`` have a random denominator and are
genuine ratios (§5). Writing all of them in one form is what makes the variance
composable instead of one hand-written formula per estimand.

The table below is the whole compiler:

===============  =========================  ===========================
measure          ``y_i``                    ``x_i``
===============  =========================  ===========================
``H``            ``poor_i``                 ``1``
``A``            ``c_i(k)``                 ``poor_i``
``M0``           ``c_i(k)``                 ``1``
``hd``           ``g_ij``                   ``observed_ij``
``hdk``          ``g_ij * poor_i``          ``observed_ij``
``actb``         ``w_j g_ij * poor_i``      ``1``
``pctb``         ``w_j g_ij * poor_i``      ``c_i(k)``
``actb_dim``     ``sum_{j in d}(...)``      ``1``
``pctb_dim``     ``sum_{j in d}(...)``      ``c_i(k)``
===============  =========================  ===========================

``pctb_j = w_j CH_j / M0`` is written directly as a ratio of totals because the
population total cancels between numerator and denominator, which keeps it a
single ratio rather than a ratio of two ratios.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import polars as pl

from .deprivation import (
    SCORE,
    contribution_column,
    deprived_column,
    observed_column,
)
from .specification import Specification

#: Measures reported for the whole population.
AGGREGATE_MEASURES = ("H", "A", "M0")
#: Measures reported once per indicator.
INDICATOR_MEASURES = ("hd", "hdk", "actb", "pctb")
#: Measures reported once per dimension.
DIMENSION_MEASURES = ("actb_dim", "pctb_dim")

MEASURE_LABELS = {
    "H": "incidence",
    "A": "intensity",
    "M0": "adjusted headcount ratio",
    "hd": "uncensored deprivation headcount",
    "hdk": "censored deprivation headcount",
    "actb": "absolute contribution",
    "pctb": "relative contribution",
    "actb_dim": "absolute contribution of the dimension",
    "pctb_dim": "relative contribution of the dimension",
}


@dataclass(frozen=True, slots=True)
class RatioEstimand:
    """One ratio ``sum(n*y) / sum(n*x)`` with its identifying metadata."""

    key: str
    measure: str
    y: pl.Expr = field(compare=False)
    x: pl.Expr = field(compare=False)
    indicator: str | None = None
    dimension: str | None = None
    weight: float | None = None

    @property
    def label(self) -> str:
        return MEASURE_LABELS.get(self.measure, self.measure)


def poor_expr(k: float) -> pl.Expr:
    """``poor_i = 1(c_i >= k)`` as a float, for use inside ratio expressions."""

    return (pl.col(SCORE) >= k).cast(pl.Float64)


def censored_score_expr(k: float) -> pl.Expr:
    """``c_i(k) = c_i * poor_i``."""

    return pl.col(SCORE) * poor_expr(k)


def build(spec: Specification, k: float) -> tuple[RatioEstimand, ...]:
    """Compile every reported estimand at one poverty cutoff ``k``."""

    indicators = spec.indicators
    weights = spec.indicator_weights
    dimensions = spec.dimensions
    poor = poor_expr(k)
    censored = censored_score_expr(k)
    one = pl.lit(1.0)

    estimands: list[RatioEstimand] = [
        RatioEstimand("H", "H", poor, one),
        RatioEstimand("A", "A", censored, poor),
        RatioEstimand("M0", "M0", censored, one),
    ]

    for index, indicator in enumerate(indicators):
        dimension = spec.dimension_of(indicator)
        g = pl.col(deprived_column(index))
        observed = pl.col(observed_column(index))
        weighted = pl.col(contribution_column(index)) * poor
        estimands.extend(
            (
                RatioEstimand(
                    f"hd::{indicator}",
                    "hd",
                    g,
                    observed,
                    indicator,
                    dimension,
                    weights[indicator],
                ),
                RatioEstimand(
                    f"hdk::{indicator}",
                    "hdk",
                    g * poor,
                    observed,
                    indicator,
                    dimension,
                    weights[indicator],
                ),
                RatioEstimand(
                    f"actb::{indicator}",
                    "actb",
                    weighted,
                    one,
                    indicator,
                    dimension,
                    weights[indicator],
                ),
                RatioEstimand(
                    f"pctb::{indicator}",
                    "pctb",
                    weighted,
                    censored,
                    indicator,
                    dimension,
                    weights[indicator],
                ),
            )
        )

    positions = {indicator: index for index, indicator in enumerate(indicators)}
    for dimension, members in dimensions.items():
        weighted = (
            pl.sum_horizontal(
                [pl.col(contribution_column(positions[item])) for item in members]
            )
            * poor
        )
        estimands.extend(
            (
                RatioEstimand(
                    f"actb_dim::{dimension}",
                    "actb_dim",
                    weighted,
                    one,
                    None,
                    dimension,
                    spec.dimension_weights[dimension],
                ),
                RatioEstimand(
                    f"pctb_dim::{dimension}",
                    "pctb_dim",
                    weighted,
                    censored,
                    None,
                    dimension,
                    spec.dimension_weights[dimension],
                ),
            )
        )
    return tuple(estimands)
