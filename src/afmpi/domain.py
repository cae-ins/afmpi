"""Domain (subpopulation) estimation without breaking the design (PLAN.md §6).

The classic mistake this module exists to prevent::

    df_abidjan = df.filter(pl.col("region") == "Abidjan")
    afmpi.estimate(df_abidjan, spec, design, ...)   # WRONG

Filtering rows before estimating changes the sampling design: the number of PSUs
and strata seen by the variance shrinks, so the standard error is wrong even
though the point estimate looks right.

The correct mechanism, and the one implemented here, is the one ``subset()``
uses in the R ``survey`` package: keep every row, and multiply the weight by the
domain indicator. Rows outside the domain then contribute exactly zero to every
total and to every influence value, while the strata and clusters they belong to
still exist for the variance. The degrees of freedom, by contrast, are counted
on the clusters and strata that do contain domain observations -- see
:class:`afmpi.variance.DesignDegrees`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import polars as pl

from .deprivation import WEIGHT

#: Name given to the whole-population domain in result tables.
NATIONAL = "__afmpi_national"


@dataclass(frozen=True, slots=True)
class Domain:
    """A subpopulation, carried as an indicator over the full sample."""

    over: str | None
    subgroup: str | None
    indicator: pl.Expr | None = field(default=None, compare=False)

    @property
    def is_population(self) -> bool:
        return self.indicator is None

    @property
    def label(self) -> str:
        if self.is_population:
            return "population"
        return f"{self.over}={self.subgroup}" if self.over else str(self.subgroup)

    def weight(self) -> pl.Expr:
        """The domain weight ``n_i * 1(i in domain)``."""

        if self.indicator is None:
            return pl.col(WEIGHT)
        return pl.col(WEIGHT) * self.indicator.cast(pl.Float64)


POPULATION = Domain(over=None, subgroup=None, indicator=None)


def levels(frame: pl.DataFrame, variable: str) -> tuple[str, ...]:
    """The subgroups of one ``over`` variable, in sorted order.

    Several ``over`` variables produce several *separate* one-way breakdowns,
    not their cross-tabulation -- the same reading as ``over = c("area",
    "region")`` in ``mpitb``. Missing values are refused: an ``over`` variable
    whose levels do not cover the whole sample would silently break the
    decomposition ``sum_l phi_l * M0_l = M0``.
    """

    if variable not in frame.columns:
        raise ValueError(f"over variable {variable!r} is absent from df")
    column = pl.col(variable)
    if frame.select(column.is_null().any()).item():
        raise ValueError(
            f"over variable {variable!r} contains missing values; an 'over' variable "
            "must partition the sample for the decomposition to hold"
        )
    return tuple(
        frame.select(column.unique().sort().cast(pl.String).alias("level"))
        .to_series()
        .to_list()
    )


def of_level(variable: str, level: str) -> Domain:
    """The domain made of one level of an ``over`` variable."""

    return Domain(
        over=variable,
        subgroup=level,
        indicator=(pl.col(variable).cast(pl.String) == pl.lit(level)),
    )


def from_expression(expression: str | pl.Expr, label: str | None = None) -> Domain:
    """Build a single domain from a boolean expression.

    A string is read as a SQL-flavoured boolean expression over the input
    columns, so both ``"region == 'Abidjan'"`` and ``"region = 'Abidjan'"``
    work.
    """

    if isinstance(expression, str):
        indicator = pl.sql_expr(expression)
        name = label if label is not None else expression
    elif isinstance(expression, pl.Expr):
        indicator = expression
        name = label if label is not None else "domain"
    else:
        raise TypeError("domain must be a string expression or a polars expression")
    return Domain(over=None, subgroup=name, indicator=indicator)


def validate(frame: pl.DataFrame, domain: Domain) -> None:
    """Check that the domain indicator is boolean and selects something."""

    if domain.is_population:
        return
    try:
        flags = frame.select(domain.indicator.alias("__afmpi_flag")).to_series()
    except Exception as error:  # pragma: no cover - message passthrough
        raise ValueError(f"domain expression could not be evaluated: {error}") from error
    if flags.dtype != pl.Boolean:
        raise TypeError("a domain expression must evaluate to a boolean column")
    if flags.fill_null(False).sum() == 0:
        raise ValueError(f"domain {domain.label!r} selects no observation")
