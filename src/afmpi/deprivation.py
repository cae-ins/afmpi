"""Deprivation engine: raw indicators to ``g_ij`` and ``c_i`` (PLAN.md §5, §14.4a-4c).

This stage knows nothing about the sampling design calculations. It validates the
indicator columns, applies the missing-value policy, builds the weighted deprivation
score ``c_i = sum_j(w_j * g_ij)``, and materialises the design identifiers that the
variance stage consumes later.
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
PI = "__afmpi_pi"


def stratum_column(level: int) -> str:
    """Stratum identifier for sampling stage ``level`` (1-indexed)."""

    return STRATUM if level == 1 else f"__afmpi_stratum{level}"


def psu_column(level: int) -> str:
    """PSU identifier for sampling stage ``level`` (1-indexed)."""

    return PSU if level == 1 else f"__afmpi_psu{level}"


def fraction_column(level: int) -> str:
    """Sampling fraction f for sampling stage ``level`` (1-indexed)."""

    return f"__afmpi_f{level}"


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
    pps_needed = ()
    if design.pps is not None and design.pps.inclusion_probability is not None:
        pps_needed = (design.pps.inclusion_probability,)
    needed = set(indicators) | set(design.required_columns) | set(extra) | set(pps_needed)
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


def _validate_no_missing_design_columns(frame: pl.DataFrame, design: SurveyDesign) -> None:
    if design.missing_design != "error":
        return

    cols_to_check: list[str] = []
    if design.stages is None:
        if design.strata is not None:
            cols_to_check.append(design.strata)
        if design.psu is not None:
            cols_to_check.append(design.psu)
    else:
        for stage in design.stages:
            if stage.strata is not None:
                cols_to_check.append(stage.strata)
            if stage.id is not None:
                cols_to_check.append(stage.id)
            if stage.fpc is not None:
                cols_to_check.append(stage.fpc)

    for col in cols_to_check:
        null_count = frame.select(pl.col(col).is_null().sum()).item()
        if null_count > 0:
            raise ValueError(
                f"design column {col!r} contains {null_count} missing value(s); missing_design='error' (the default) rejects missing design identifiers"
            )


def _add_design_identifiers(frame: pl.DataFrame, design: SurveyDesign) -> pl.DataFrame:
    """Materialise stratum, PSU and FPC keys across sampling stages."""

    _validate_no_missing_design_columns(frame, design)

    stages = design.resolved_stages
    if len(stages) == 0:
        stratum = (
            pl.col(design.strata).cast(pl.String).fill_null("__afmpi_null__")
            if design.strata is not None
            else pl.lit("__afmpi_all__")
        )
        if design.psu is not None:
            psu = pl.col(design.psu).cast(pl.String).fill_null("__afmpi_null__")
        else:
            psu = pl.int_range(pl.len(), dtype=pl.Int64).cast(pl.String)
        frame = frame.with_columns(
            stratum.alias(STRATUM),
            (stratum + pl.lit("|") + psu).alias(PSU),
            pl.lit(0.0).alias(fraction_column(1)),
        )
    else:
        for index, stage in enumerate(stages, start=1):
            s_col = stratum_column(index)
            p_col = psu_column(index)
            f_col = fraction_column(index)

            if index == 1:
                stratum_expr = (
                    pl.col(stage.strata).cast(pl.String).fill_null("__afmpi_null__")
                    if stage.strata
                    else pl.lit("__afmpi_all__")
                )
            else:
                prev_psu = pl.col(psu_column(index - 1))
                stratum_expr = prev_psu + pl.lit("|") + (
                    pl.col(stage.strata).cast(pl.String).fill_null("__afmpi_null__")
                    if stage.strata
                    else pl.lit("")
                )

            psu_expr = stratum_expr + pl.lit("|") + pl.col(stage.id).cast(pl.String).fill_null("__afmpi_null__")

            frame = frame.with_columns(
                stratum_expr.alias(s_col),
                psu_expr.alias(p_col),
            )

            if stage.fpc is not None:
                grouped_fpc = frame.group_by(s_col).agg(
                    pl.col(stage.fpc).drop_nulls().unique().alias("u_fpc")
                )
                non_const = grouped_fpc.filter(pl.col("u_fpc").list.len() > 1)
                if non_const.height > 0:
                    strat_val = non_const.row(0, named=True)[s_col]
                    raise ValueError(
                        f"fpc column {stage.fpc!r} is not constant within stratum {strat_val!r}"
                    )

                fpc_series = frame.select(
                    pl.col(stage.fpc).cast(pl.Float64).drop_nulls().drop_nans()
                ).to_series()
                if len(fpc_series) > 0:
                    has_le_1 = (fpc_series <= 1.0).any()
                    has_gt_1 = (fpc_series > 1.0).any()
                    if has_le_1 and has_gt_1:
                        raise ValueError(f"fpc column {stage.fpc!r} mixes values <= 1 and > 1")
                    if has_le_1:
                        if (fpc_series < 0.0).any() or (fpc_series > 1.0).any():
                            raise ValueError(f"sampling fraction fpc {stage.fpc!r} must be in [0, 1]")
                        frame = frame.with_columns(
                            pl.col(stage.fpc).cast(pl.Float64).fill_null(0.0).alias(f_col)
                        )
                    else:
                        counts = frame.group_by(s_col).agg(
                            pl.col(p_col).n_unique().alias("__m"),
                            pl.col(stage.fpc).cast(pl.Float64).first().alias("__N"),
                        )
                        invalid_N = counts.filter(pl.col("__N") < pl.col("__m"))
                        if invalid_N.height > 0:
                            row = invalid_N.row(0, named=True)
                            raise ValueError(
                                f"fpc N={row['__N']} is smaller than the m={row['__m']} sampled units in stratum {row[s_col]!r}"
                            )
                        f_frame = counts.with_columns(
                            (pl.col("__m").cast(pl.Float64) / pl.col("__N")).alias(f_col)
                        ).select(s_col, f_col)
                        frame = frame.join(f_frame, on=s_col, how="left")
                else:
                    frame = frame.with_columns(pl.lit(0.0).alias(f_col))
            else:
                frame = frame.with_columns(pl.lit(0.0).alias(f_col))

    if design.pps is not None and design.pps.inclusion_probability is not None:
        pi_name = design.pps.inclusion_probability
        pi_col = pl.col(pi_name).cast(pl.Float64)
        invalid = frame.select(
            (pi_col.is_null() | pi_col.is_nan() | (pi_col <= 0) | (pi_col > 1)).any()
        ).item()
        if invalid:
            raise ValueError(f"inclusion_probability column {pi_name!r} must be in (0, 1]")

        grouped_pi = frame.group_by(PSU).agg(pi_col.unique().alias("u_pi"))
        non_const = grouped_pi.filter(pl.col("u_pi").list.len() > 1)
        if non_const.height > 0:
            psu_val = non_const.row(0, named=True)[PSU]
            raise ValueError(
                f"inclusion_probability column {pi_name!r} is not constant within PSU {psu_val!r}"
            )

        frame = frame.with_columns(pi_col.alias(PI))

    return frame
