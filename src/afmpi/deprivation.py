"""Deprivation engine: raw indicators to ``g_ij`` and ``c_i`` (PLAN.md §5).

This stage knows nothing about the sampling design. It validates the indicator
columns, applies the missing-value policy, builds the weighted deprivation score
``c_i = sum_j(w_j * g_ij)``, and materialises the design identifiers that the
variance stage consumes later. The same output feeds the Taylor path, and would
feed the replication and census paths unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

import pandas as pd
import polars as pl

from .specification import Specification
from .survey_design import SurveyDesign

InputKind = str

WEIGHT = "__afmpi_n"
SCORE = "__afmpi_c"
STRATUM = "__afmpi_stratum"
PSU = "__afmpi_psu"


def deprived_column(index: int) -> str:
    """Column holding ``g_ij`` as a float, with missing values read as zero."""

    return f"__afmpi_g{index}"


def observed_column(index: int) -> str:
    """Column holding ``1`` when indicator ``j`` is observed for the row."""

    return f"__afmpi_obs{index}"


def contribution_column(index: int) -> str:
    """Column holding the weighted deprivation ``w_j * g_ij`` used by ``c_i``."""

    return f"__afmpi_wc{index}"


@dataclass(frozen=True, slots=True)
class DeprivationMatrix:
    """Row-level deprivation quantities plus the columns the design needs."""

    frame: pl.DataFrame
    spec: Specification
    design: SurveyDesign
    observations: int
    excluded_observations: int
    population: float
    input_kind: InputKind

    @property
    def indicators(self) -> tuple[str, ...]:
        return self.spec.indicators


def build(
    df: pd.DataFrame | pl.DataFrame,
    spec: Specification,
    design: SurveyDesign,
    *,
    required_columns: tuple[str, ...] = (),
) -> DeprivationMatrix:
    """Validate ``df`` and compute ``g_ij``, ``c_i``, weights and design ids."""

    if not isinstance(spec, Specification):
        raise TypeError("spec must be a Specification")
    if not isinstance(design, SurveyDesign):
        raise TypeError("design must be a SurveyDesign or None")

    indicators = spec.indicators  # also verifies that the specification is configured
    frame, input_kind = _to_polars(df)
    if frame.height == 0:
        raise ValueError("df must contain at least one observation")

    _validate_required_columns(frame, indicators, design, required_columns)
    frame = _validate_and_normalize_indicators(frame, indicators)
    frame = _add_population_weight(frame, design)

    initial_observations = frame.height
    frame = _apply_missing_policy(frame, spec)
    if frame.height == 0:
        raise ValueError("no observations remain after applying missing_policy")

    frame = _add_design_identifiers(frame, design)
    population = float(frame.select(pl.col(WEIGHT).sum()).item())

    return DeprivationMatrix(
        frame=frame,
        spec=spec,
        design=design,
        observations=frame.height,
        excluded_observations=initial_observations - frame.height,
        population=population,
        input_kind=input_kind,
    )


def _to_polars(df: pd.DataFrame | pl.DataFrame) -> tuple[pl.DataFrame, InputKind]:
    if isinstance(df, pl.DataFrame):
        return df, "polars"
    if isinstance(df, pd.DataFrame):
        return pl.from_pandas(df, include_index=False, rechunk=False), "pandas"
    raise TypeError("df must be a pandas.DataFrame or polars.DataFrame")


def _validate_required_columns(
    frame: pl.DataFrame,
    indicators: tuple[str, ...],
    design: SurveyDesign,
    extra: tuple[str, ...],
) -> None:
    needed = set(indicators) | set(design.required_columns) | set(extra)
    missing = sorted(needed - set(frame.columns))
    if missing:
        raise ValueError(f"columns absent from df: {missing}")
    reserved = sorted(name for name in frame.columns if name.startswith("__afmpi"))
    if reserved:
        raise ValueError(f"column names starting with '__afmpi' are reserved: {reserved}")


def _validate_and_normalize_indicators(
    frame: pl.DataFrame,
    indicators: tuple[str, ...],
) -> pl.DataFrame:
    normalized: list[pl.Expr] = []
    for indicator in indicators:
        dtype = frame.schema[indicator]
        if dtype == pl.Boolean:
            normalized.append(pl.col(indicator))
            continue
        if not dtype.is_numeric():
            raise TypeError(
                f"indicator {indicator!r} must be boolean or numeric 0/1; got {dtype}"
            )
        expression = pl.col(indicator)
        if dtype.is_float():
            expression = expression.fill_nan(None)
        invalid = (
            frame.select(expression.drop_nulls().filter(~expression.is_in([0, 1])).unique())
            .to_series()
            .to_list()
        )
        if invalid:
            raise ValueError(
                f"indicator {indicator!r} contains values other than 0/1: {invalid[:5]}"
            )
        normalized.append(expression.alias(indicator))
    return frame.with_columns(normalized)


def _add_population_weight(frame: pl.DataFrame, design: SurveyDesign) -> pl.DataFrame:
    expressions: list[pl.Expr] = []
    for column in design.required_columns:
        dtype = frame.schema[column]
        if not dtype.is_numeric() or dtype == pl.Boolean:
            raise TypeError(f"survey column {column!r} must be numeric; got {dtype}")
        value = pl.col(column).cast(pl.Float64)
        invalid = frame.select(
            (value.is_null() | value.is_nan() | ~value.is_finite()).any()
        ).item()
        if invalid:
            raise ValueError(f"survey column {column!r} contains missing or non-finite values")
        if column == design.household_size:
            bad_sign = frame.select((value <= 0).any()).item()
            message = "strictly positive"
        else:
            bad_sign = frame.select((value < 0).any()).item()
            message = "non-negative"
        if bad_sign:
            raise ValueError(f"survey column {column!r} must be {message}")
        expressions.append(value)

    population_weight = pl.lit(1.0)
    for expression in expressions:
        population_weight = population_weight * expression
    result = frame.with_columns(population_weight.alias(WEIGHT))
    total = result.select(pl.col(WEIGHT).sum()).item()
    if total is None or not isfinite(float(total)) or total <= 0:
        raise ValueError("effective population weights must have a positive finite sum")
    return result


def _apply_missing_policy(frame: pl.DataFrame, spec: Specification) -> pl.DataFrame:
    """Add ``g_ij``, the observation flags, ``w_j * g_ij`` and ``c_i``.

    ``listwise_deletion`` drops rows with any missing indicator. ``reweighting``
    keeps them and redistributes the weight of the missing indicators over the
    observed ones, so that ``c_i`` stays comparable across rows.
    """

    weights = spec.indicator_weights
    indicators = spec.indicators

    if spec.missing_policy == "listwise_deletion":
        complete = pl.all_horizontal([pl.col(item).is_not_null() for item in indicators])
        frame = frame.filter(complete)
        contributions = [
            (pl.col(item).cast(pl.Float64) * weights[item]).alias(contribution_column(index))
            for index, item in enumerate(indicators)
        ]
    else:
        observed_weight = pl.sum_horizontal(
            [
                pl.when(pl.col(item).is_not_null()).then(weights[item]).otherwise(0.0)
                for item in indicators
            ]
        )
        frame = frame.filter(observed_weight > 0)
        contributions = [
            pl.when(pl.col(item).is_not_null())
            .then(pl.col(item).cast(pl.Float64) * weights[item] / observed_weight)
            .otherwise(0.0)
            .alias(contribution_column(index))
            for index, item in enumerate(indicators)
        ]

    if frame.height == 0:
        return frame

    frame = frame.with_columns(
        *contributions,
        *[
            pl.col(item).cast(pl.Float64).fill_null(0.0).alias(deprived_column(index))
            for index, item in enumerate(indicators)
        ],
        *[
            pl.col(item).is_not_null().cast(pl.Float64).alias(observed_column(index))
            for index, item in enumerate(indicators)
        ],
    )
    return frame.with_columns(
        pl.sum_horizontal(
            [pl.col(contribution_column(index)) for index in range(len(indicators))]
        ).alias(SCORE)
    )


def _add_design_identifiers(frame: pl.DataFrame, design: SurveyDesign) -> pl.DataFrame:
    """Materialise the stratum and PSU keys used by the Taylor variance.

    Without declared strata the whole sample is one stratum. Without declared
    PSUs every row is its own PSU, which reproduces the with-replacement simple
    random sampling variance -- the same convention as ``ids = ~1`` in the R
    ``survey`` package.

    PSU identifiers are read as nested inside their stratum: a design that
    numbers its clusters ``1, 2, ...`` inside each stratum is then read
    correctly, and a PSU can never straddle two strata. When cluster identifiers
    are already unique across strata this nesting changes nothing.
    """

    stratum = (
        pl.col(design.strata).cast(pl.String).fill_null("__afmpi_null__")
        if design.strata is not None
        else pl.lit("__afmpi_all__")
    )
    if design.psu is not None:
        psu = pl.col(design.psu).cast(pl.String).fill_null("__afmpi_null__")
    else:
        psu = pl.int_range(pl.len(), dtype=pl.Int64).cast(pl.String)
    return frame.with_columns(stratum.alias(STRATUM)).with_columns(
        (pl.col(STRATUM) + pl.lit("|") + psu).alias(PSU)
    )
