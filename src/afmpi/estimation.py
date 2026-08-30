"""Alkire-Foster estimation with design-based Taylor variance.

The pipeline follows PLAN.md §5: the deprivation engine turns raw indicators
into ``c_i``, the estimand compiler turns ``c_i`` into ratios, the linearization
stage turns ratios into influence values, and only then does the design get
involved.
"""

from __future__ import annotations

from collections.abc import Sequence
from math import isfinite
from numbers import Real

import pandas as pd
import polars as pl

from . import deprivation, domain as domain_module, estimands as estimands_module
from . import linearization
from .deprivation import DeprivationMatrix
from .results import EstimationResult
from .specification import Specification
from .survey_design import SurveyDesign
from .variance import (
    CI_METHODS,
    coefficient_of_variation,
    confidence_interval,
    design_degrees,
    design_variance,
    standard_error,
)

DECOMPOSITION_TOLERANCE = 1e-9

_CLUSTER_WEIGHT = "__afmpi_cluster_weight"
_CLUSTER_ROWS = "__afmpi_cluster_rows"

_ESTIMATE_SCHEMA = {
    "measure": pl.String,
    "indicator": pl.String,
    "dimension": pl.String,
    "weight": pl.Float64,
    "k": pl.Float64,
    "over": pl.String,
    "subgroup": pl.String,
    "est": pl.Float64,
    "se": pl.Float64,
    "lci": pl.Float64,
    "uci": pl.Float64,
    "cv": pl.Float64,
    "df": pl.Int64,
    "psus": pl.Int64,
    "strata": pl.Int64,
    "obs": pl.Int64,
    "population": pl.Float64,
}


def estimate(
    df: pd.DataFrame | pl.DataFrame,
    spec: Specification,
    design: SurveyDesign | None = None,
    *,
    k: float | Sequence[float] = 1 / 3,
    over: str | Sequence[str] | None = None,
    domain: str | pl.Expr | None = None,
    ci_method: str = "logit",
    level: float = 0.95,
    check_decomposability: bool = True,
) -> EstimationResult:
    """Estimate Alkire-Foster measures with design-based standard errors."""

    if design is None:
        design = SurveyDesign()
    cutoffs = _validate_cutoffs(k)
    variables = _validate_over(over)
    if ci_method not in CI_METHODS:
        raise ValueError(f"ci_method must be one of {CI_METHODS}; got {ci_method!r}")

    matrix = deprivation.build(
        df,
        spec,
        design,
        required_columns=tuple(variables) + design.design_columns,
    )
    return _estimate_from_matrix(
        matrix,
        cutoffs=cutoffs,
        variables=variables,
        domain=domain,
        ci_method=ci_method,
        level=level,
        check_decomposability=check_decomposability,
    )


def _stage_group_columns(frame: pl.DataFrame, design: SurveyDesign) -> tuple[str, ...]:
    stages = design.resolved_stages
    depth = max(1, len(stages))
    cols: list[str] = []
    for level in range(1, depth + 1):
        cols.append(deprivation.stratum_column(level))
        cols.append(deprivation.psu_column(level))
        cols.append(deprivation.fraction_column(level))
    if deprivation.PI in frame.columns:
        cols.append(deprivation.PI)
    return tuple(cols)


def _estimate_from_matrix(
    matrix: DeprivationMatrix,
    *,
    cutoffs: tuple[float, ...],
    variables: tuple[str, ...],
    domain: str | pl.Expr | None,
    ci_method: str,
    level: float,
    check_decomposability: bool,
) -> EstimationResult:
    frame = matrix.frame
    spec = matrix.spec
    design = matrix.design

    base = domain_module.POPULATION
    if domain is not None:
        base = domain_module.from_expression(domain)
        domain_module.validate(frame, base)
    base_weight = base.weight()

    group_cols = _stage_group_columns(frame, design)
    universe = frame.select(list(group_cols)).unique(maintain_order=True)
    subgroups = {variable: domain_module.levels(frame, variable) for variable in variables}
    rows: list[dict[str, object]] = []
    decomposition: list[dict[str, object]] = []

    for cutoff in cutoffs:
        estimands = estimands_module.build(spec, cutoff)
        keys = tuple(item.key for item in estimands)

        national_sums = linearization.cluster_sums(
            frame, estimands, base_weight, group_columns=group_cols
        )
        national = _context_rows(
            national_sums, estimands, keys, cutoff, None, None, ci_method, level, design
        )
        rows.extend(national)
        national_population = national[0]["population"] if national else 0.0
        national_m0 = _pick(national, "M0")

        for variable in variables:
            cells = linearization.cluster_sums(
                frame,
                estimands,
                base_weight,
                group_columns=group_cols + (variable,),
            )
            share_total = 0.0
            weighted_m0 = 0.0
            for subgroup in subgroups[variable]:
                sums = _align(cells, universe, variable, subgroup, group_cols)
                subgroup_rows = _context_rows(
                    sums, estimands, keys, cutoff, variable, subgroup, ci_method, level, design
                )
                rows.extend(subgroup_rows)
                if national_population:
                    share = subgroup_rows[0]["population"] / national_population
                    share_total += share
                    subgroup_m0 = _pick(subgroup_rows, "M0")
                    if subgroup_m0 is not None:
                        weighted_m0 += share * subgroup_m0
            if national_m0 is not None:
                decomposition.append(
                    {
                        "k": cutoff,
                        "over": variable,
                        "shares": share_total,
                        "M0": national_m0,
                        "decomposed_M0": weighted_m0,
                        "error": abs(weighted_m0 - national_m0),
                    }
                )

    estimates = pl.DataFrame(rows, schema=_ESTIMATE_SCHEMA)
    decomposition_frame = pl.DataFrame(
        decomposition,
        schema={
            "k": pl.Float64,
            "over": pl.String,
            "shares": pl.Float64,
            "M0": pl.Float64,
            "decomposed_M0": pl.Float64,
            "error": pl.Float64,
        },
    )
    if check_decomposability and decomposition_frame.height:
        _assert_decomposable(decomposition_frame)

    return EstimationResult(
        _estimates=estimates,
        _decomposition=decomposition_frame,
        _matrix=matrix,
        _cutoffs=cutoffs,
        _over=variables,
        _domain=(base.over, base.subgroup) if not base.is_population else None,
        _ci_method=ci_method,
        _level=level,
        observations=matrix.observations,
        excluded_observations=matrix.excluded_observations,
    )


def _context_rows(
    sums: pl.DataFrame,
    estimands: tuple[estimands_module.RatioEstimand, ...],
    keys: tuple[str, ...],
    cutoff: float,
    over: str | None,
    subgroup: str | None,
    ci_method: str,
    level: float,
    design: SurveyDesign,
) -> list[dict[str, object]]:
    """Point estimates, variance and intervals for one (k, domain) context."""

    ratios = linearization.totals_from_clusters(sums, estimands)
    influence = linearization.cluster_influence(sums, ratios)
    degrees = design_degrees(influence)
    variances, degrees = design_variance(influence, keys, degrees, design)

    totals = sums.select(
        pl.col(_CLUSTER_WEIGHT).sum().alias("population"),
        pl.col(_CLUSTER_ROWS).sum().alias("obs"),
    ).row(0, named=True)
    population = float(totals["population"] or 0.0)
    observations = int(totals["obs"] or 0)

    rows: list[dict[str, object]] = []
    for ratio in ratios:
        estimand = ratio.estimand
        value = ratio.value
        se = standard_error(variances[estimand.key])
        lower, upper = confidence_interval(
            value, se, degrees.df, method=ci_method, level=level
        )
        rows.append(
            {
                "measure": estimand.measure,
                "indicator": estimand.indicator,
                "dimension": estimand.dimension,
                "weight": estimand.weight,
                "k": cutoff,
                "over": over,
                "subgroup": subgroup,
                "est": value,
                "se": se,
                "lci": lower,
                "uci": upper,
                "cv": coefficient_of_variation(value, se),
                "df": degrees.df,
                "psus": degrees.psus,
                "strata": degrees.strata,
                "obs": observations,
                "population": population,
            }
        )
    return rows


def _align(
    cells: pl.DataFrame,
    universe: pl.DataFrame,
    variable: str,
    subgroup: str,
    group_columns: tuple[str, ...],
) -> pl.DataFrame:
    """Restrict per-cluster sums to one level, keeping every design cluster."""

    selected = cells.filter(pl.col(variable).cast(pl.String) == pl.lit(subgroup)).drop(
        variable
    )
    value_columns = [column for column in selected.columns if column not in group_columns]
    aligned = universe.join(selected, on=list(group_columns), how="left")
    return aligned.with_columns(
        [pl.col(column).fill_null(0).alias(column) for column in value_columns]
    )


def _pick(rows: list[dict[str, object]], measure: str) -> float | None:
    for row in rows:
        if row["measure"] == measure:
            return row["est"]
    return None


def _assert_decomposable(frame: pl.DataFrame) -> None:
    worst = frame.filter(pl.col("error") == pl.col("error").max()).row(0, named=True)
    if worst["error"] > DECOMPOSITION_TOLERANCE:
        raise ValueError(
            "decomposability check failed: sum_l phi_l * M0_l = "
            f"{worst['decomposed_M0']!r} but M0 = {worst['M0']!r} "
            f"(over={worst['over']!r}, k={worst['k']!r}, "
            f"difference {worst['error']:.3e} > {DECOMPOSITION_TOLERANCE:.0e})"
        )


def _validate_cutoffs(k: float | Sequence[float]) -> tuple[float, ...]:
    values = [k] if isinstance(k, (Real, bool)) else list(k)
    if not values:
        raise ValueError("k must contain at least one cutoff")
    cutoffs: list[float] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, Real):
            raise TypeError("k must be a real number between 0 and 1")
        cutoff = float(value)
        if not isfinite(cutoff) or not 0 <= cutoff <= 1:
            raise ValueError("k must be finite and between 0 and 1, inclusive")
        cutoffs.append(cutoff)
    if len(set(cutoffs)) != len(cutoffs):
        raise ValueError(f"k contains duplicate cutoffs: {cutoffs}")
    return tuple(cutoffs)


def _validate_over(over: str | Sequence[str] | None) -> tuple[str, ...]:
    if over is None:
        return ()
    variables = [over] if isinstance(over, str) else list(over)
    for variable in variables:
        if not isinstance(variable, str) or not variable.strip():
            raise ValueError("over must contain non-empty column names")
    if len(set(variables)) != len(variables):
        raise ValueError(f"over contains duplicate variables: {variables}")
    return tuple(variables)


__all__ = ["DECOMPOSITION_TOLERANCE", "estimate"]
