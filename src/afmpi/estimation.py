"""Polars-native Alkire-Foster point estimation."""

from __future__ import annotations

from math import isfinite
from numbers import Real

import pandas as pd
import polars as pl

from .results import EstimationResult, InputKind
from .specification import Specification
from .survey_design import SurveyDesign


def estimate(
    df: pd.DataFrame | pl.DataFrame,
    spec: Specification,
    design: SurveyDesign | None = None,
    *,
    k: float = 1 / 3,
) -> EstimationResult:
    """Estimate one Alkire-Foster adjusted headcount ratio.

    The implemented identities are:

    ``c_i = sum_j(w_j * g_ij)``, ``poor_i = 1(c_i >= k)``,
    ``c_i(k) = c_i * poor_i``,
    ``H = sum_i(n_i * poor_i) / sum_i(n_i)``,
    ``A = sum_i(n_i * c_i(k)) / sum_i(n_i * poor_i)``, and
    ``M0 = H * A = sum_i(n_i * c_i(k)) / sum_i(n_i)``.
    """

    if not isinstance(spec, Specification):
        raise TypeError("spec must be a Specification")
    indicators = spec.indicators  # also verifies that the specification is configured
    if design is None:
        design = SurveyDesign()
    if not isinstance(design, SurveyDesign):
        raise TypeError("design must be a SurveyDesign or None")
    cutoff = _validate_cutoff(k)

    frame, input_kind = _to_polars(df)
    if frame.height == 0:
        raise ValueError("df must contain at least one observation")
    _validate_required_columns(frame, indicators, design)
    frame = _validate_and_normalize_indicators(frame, indicators)
    frame = _add_population_weight(frame, design)

    initial_observations = frame.height
    frame, score_exprs = _apply_missing_policy(frame, spec)
    if frame.height == 0:
        raise ValueError("no observations remain after applying missing_policy")

    scored = frame.select(
        pl.col("__afmpi_population_weight"),
        score_exprs["score"].alias("score"),
        *[
            expression.alias(f"__afmpi_contribution_{index}")
            for index, expression in enumerate(score_exprs["weighted_deprivations"])
        ],
    ).with_columns(
        (pl.col("score") >= cutoff).alias("poor"),
    ).with_columns(
        pl.when(pl.col("poor"))
        .then(pl.col("score"))
        .otherwise(0.0)
        .alias("censored_score")
    )

    totals = scored.select(
        pl.col("__afmpi_population_weight").sum().alias("population"),
        (pl.col("__afmpi_population_weight") * pl.col("poor").cast(pl.Float64))
        .sum()
        .alias("poor_population"),
        (pl.col("__afmpi_population_weight") * pl.col("censored_score"))
        .sum()
        .alias("weighted_censored_score"),
    ).row(0, named=True)
    population = float(totals["population"])
    poor_population = float(totals["poor_population"])
    weighted_censored_score = float(totals["weighted_censored_score"])
    H = poor_population / population
    A = weighted_censored_score / poor_population if poor_population > 0 else 0.0
    M0 = weighted_censored_score / population

    indicator_results = _indicator_results(frame, scored, spec, population, M0)
    dimension_results = _dimension_results(indicator_results, spec)
    scores = scored.select(
        pl.col("score"),
        pl.col("poor"),
        pl.col("censored_score"),
        pl.col("__afmpi_population_weight").alias("population_weight"),
    )

    return EstimationResult(
        k=cutoff,
        observations=frame.height,
        excluded_observations=initial_observations - frame.height,
        population=population,
        H=H,
        A=A,
        M0=M0,
        _indicator_results=indicator_results,
        _dimension_results=dimension_results,
        _scores=scores,
        _input_kind=input_kind,
    )


def _to_polars(df: pd.DataFrame | pl.DataFrame) -> tuple[pl.DataFrame, InputKind]:
    if isinstance(df, pl.DataFrame):
        return df, "polars"
    if isinstance(df, pd.DataFrame):
        return pl.from_pandas(df, include_index=False, rechunk=False), "pandas"
    raise TypeError("df must be a pandas.DataFrame or polars.DataFrame")


def _validate_cutoff(k: float) -> float:
    if isinstance(k, bool) or not isinstance(k, Real):
        raise TypeError("k must be a real number between 0 and 1")
    cutoff = float(k)
    if not isfinite(cutoff) or not 0 <= cutoff <= 1:
        raise ValueError("k must be finite and between 0 and 1, inclusive")
    return cutoff


def _validate_required_columns(
    frame: pl.DataFrame,
    indicators: tuple[str, ...],
    design: SurveyDesign,
) -> None:
    missing = sorted(set(indicators + design.required_columns) - set(frame.columns))
    if missing:
        raise ValueError(f"columns absent from df: {missing}")


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
    result = frame.with_columns(population_weight.alias("__afmpi_population_weight"))
    total = result.select(pl.col("__afmpi_population_weight").sum()).item()
    if total is None or not isfinite(float(total)) or total <= 0:
        raise ValueError("effective population weights must have a positive finite sum")
    return result


def _apply_missing_policy(
    frame: pl.DataFrame,
    spec: Specification,
) -> tuple[pl.DataFrame, dict[str, pl.Expr | list[pl.Expr]]]:
    weights = spec.indicator_weights
    indicators = spec.indicators

    if spec.missing_policy == "listwise_deletion":
        complete = pl.all_horizontal([pl.col(item).is_not_null() for item in indicators])
        filtered = frame.filter(complete)
        weighted = [
            pl.col(item).cast(pl.Float64) * weights[item] for item in indicators
        ]
        return filtered, {"score": pl.sum_horizontal(weighted), "weighted_deprivations": weighted}

    observed_weight = pl.sum_horizontal(
        [
            pl.when(pl.col(item).is_not_null()).then(weights[item]).otherwise(0.0)
            for item in indicators
        ]
    )
    filtered = frame.filter(observed_weight > 0)
    weighted = [
        pl.when(pl.col(item).is_not_null())
        .then(pl.col(item).cast(pl.Float64) * weights[item] / observed_weight)
        .otherwise(0.0)
        for item in indicators
    ]
    return filtered, {"score": pl.sum_horizontal(weighted), "weighted_deprivations": weighted}


def _indicator_results(
    frame: pl.DataFrame,
    scored: pl.DataFrame,
    spec: Specification,
    population: float,
    M0: float,
) -> pl.DataFrame:
    indicators = spec.indicators
    weights = spec.indicator_weights
    combined = pl.concat(
        [
            frame.select(
                pl.col("__afmpi_population_weight"),
                *[pl.col(item) for item in indicators],
            ),
            scored.select(
                pl.col("poor"),
                *[pl.col(f"__afmpi_contribution_{i}") for i in range(len(indicators))],
            ),
        ],
        how="horizontal",
    )

    aggregations: list[pl.Expr] = []
    for index, indicator in enumerate(indicators):
        observed = pl.col(indicator).is_not_null()
        deprivation = pl.col(indicator).cast(pl.Float64).fill_null(0.0)
        aggregations.extend(
            (
                pl.when(observed)
                .then(pl.col("__afmpi_population_weight"))
                .otherwise(0.0)
                .sum()
                .alias(f"observed_population_{index}"),
                (pl.col("__afmpi_population_weight") * deprivation)
                .sum()
                .alias(f"deprived_{index}"),
                (
                    pl.col("__afmpi_population_weight")
                    * deprivation
                    * pl.col("poor").cast(pl.Float64)
                )
                .sum()
                .alias(f"censored_deprived_{index}"),
                (
                    pl.col("__afmpi_population_weight")
                    * pl.col(f"__afmpi_contribution_{index}")
                    * pl.col("poor").cast(pl.Float64)
                )
                .sum()
                .alias(f"absolute_numerator_{index}"),
            )
        )
    totals = combined.select(aggregations).row(0, named=True)

    rows: list[dict[str, str | float | None]] = []
    for index, indicator in enumerate(indicators):
        indicator_population = float(totals[f"observed_population_{index}"])
        if indicator_population > 0:
            H_j = float(totals[f"deprived_{index}"]) / indicator_population
            CH_j = float(totals[f"censored_deprived_{index}"]) / indicator_population
        else:
            H_j = None
            CH_j = None
        actb_j = float(totals[f"absolute_numerator_{index}"]) / population
        rows.append(
            {
                "dimension": spec.dimension_of(indicator),
                "indicator": indicator,
                "weight": weights[indicator],
                "H_j": H_j,
                "CH_j": CH_j,
                "actb_j": actb_j,
                "pctb_j": actb_j / M0 if M0 > 0 else None,
            }
        )
    return pl.DataFrame(rows)


def _dimension_results(
    indicator_results: pl.DataFrame,
    spec: Specification,
) -> pl.DataFrame:
    dimensions = spec.dimension_weights
    return (
        indicator_results.group_by("dimension", maintain_order=True)
        .agg(
            pl.col("actb_j").sum().alias("actb_dim"),
            pl.when(pl.col("pctb_j").count() > 0)
            .then(pl.col("pctb_j").sum())
            .otherwise(None)
            .alias("pctb_dim"),
        )
        .with_columns(
            pl.col("dimension").replace_strict(dimensions).alias("weight")
        )
        .select("dimension", "weight", "actb_dim", "pctb_dim")
    )
