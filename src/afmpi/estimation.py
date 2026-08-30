"""Alkire-Foster estimation with design-based Taylor or replication variance.

The pipeline follows PLAN.md §5: the deprivation engine turns raw indicators
into ``c_i``, the estimand compiler turns ``c_i`` into ratios, and then either
the Taylor path (linearization) or the Replication path (re-estimation per
replicate) is called.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite
from numbers import Real

import pandas as pd
import polars as pl

from . import deprivation, domain as domain_module, estimands as estimands_module
from . import linearization
from .deprivation import DeprivationMatrix
from .design_base import Design
from .replicate_design import ReplicateDesign
from .replicate_estimation import (
    generate_replicate_weights,
    replicate_totals,
    replicate_variance,
    replicate_weight_expressions,
)
from .results import EstimationResult
from .specification import Specification
from .survey_design import SurveyDesign
from .variance import (
    CI_METHODS,
    DesignDegrees,
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


@dataclass(frozen=True, slots=True)
class VarianceReport:
    values: dict[str, float]
    degrees: DesignDegrees
    population: float
    observations: int


def estimate(
    df: pd.DataFrame | pl.DataFrame,
    spec: Specification,
    design: Design | None = None,
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

    rows: list[dict[str, object]] = []
    decomposition: list[dict[str, object]] = []

    if design.variance_path == "taylor":
        group_cols = _stage_group_columns(frame, design)  # type: ignore[arg-type]
        universe = frame.select(list(group_cols)).unique(maintain_order=True)
        subgroups = {
            variable: domain_module.levels(frame, variable) for variable in variables
        }

        for cutoff in cutoffs:
            estimands = estimands_module.build(spec, cutoff)
            keys = tuple(item.key for item in estimands)

            national_sums = linearization.cluster_sums(
                frame, estimands, base_weight, group_columns=group_cols
            )
            ratios, report = _taylor_report(
                national_sums, estimands, keys, design  # type: ignore[arg-type]
            )
            national = _context_rows(
                ratios, report, cutoff, None, None, ci_method, level
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
                    sub_ratios, sub_report = _taylor_report(
                        sums, estimands, keys, design  # type: ignore[arg-type]
                    )
                    subgroup_rows = _context_rows(
                        sub_ratios, sub_report, cutoff, variable, subgroup, ci_method, level
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
    elif design.variance_path == "replication":
        rep_design: ReplicateDesign = design  # type: ignore[assignment]

        if rep_design.replicate_weights is None:
            frame_work, repw_cols, scale, rscales = generate_replicate_weights(
                frame, rep_design
            )
            if rep_design.method == "JKn" and rep_design.strata is not None:
                H = frame_work.select(
                    pl.col(rep_design.strata).cast(pl.String)
                ).n_unique()
            else:
                H = 1
            rep_design_active = ReplicateDesign(
                weights=rep_design.weights,
                household_size=rep_design.household_size,
                replicate_weights=repw_cols,
                method=rep_design.method,
                strata=rep_design.strata,
                psu=rep_design.psu,
                fay=rep_design.fay,
                scale=scale,
                rscales=rscales,
                combined_weights=rep_design.combined_weights,
                mse=rep_design.mse,
                degf=rep_design.degf,
            )
        else:
            frame_work = frame
            repw_cols = rep_design.replicate_weights
            R = len(repw_cols)
            if rep_design.scale is not None:
                scale = rep_design.scale
            elif rep_design.method == "JK1":
                scale = (R - 1) / R
            elif rep_design.method == "BRR":
                scale = 1.0 / R
            elif rep_design.method == "Fay_BRR":
                rho = rep_design.fay if rep_design.fay is not None else 0.5
                scale = 1.0 / (R * ((1.0 - rho) ** 2))
            elif rep_design.method == "SDR":
                scale = 4.0 / R
            elif rep_design.method == "bootstrap":
                scale = 1.0 / R
            else:  # JKn
                scale = 1.0

            rscales = (
                rep_design.rscales
                if rep_design.rscales is not None
                else ((1.0,) * R)
            )
            if rep_design.method == "JKn" and rep_design.strata is not None:
                H = frame_work.select(
                    pl.col(rep_design.strata).cast(pl.String)
                ).n_unique()
            else:
                H = 1
            rep_design_active = ReplicateDesign(
                weights=rep_design.weights,
                household_size=rep_design.household_size,
                replicate_weights=repw_cols,
                method=rep_design.method,
                strata=rep_design.strata,
                psu=rep_design.psu,
                fay=rep_design.fay,
                scale=scale,
                rscales=rscales,
                combined_weights=rep_design.combined_weights,
                mse=rep_design.mse,
                degf=rep_design.degf,
            )

        R = len(rep_design_active.replicate_weights)
        df_strata = (
            H
            if (
                rep_design.method == "JKn"
                and (
                    rep_design.strata is not None
                    or rep_design.replicate_weights is None
                )
            )
            else 1
        )
        degrees = DesignDegrees(
            psus=R, strata=df_strata, lonely_strata=0, override_df=rep_design.degf
        )

        rep_weight_exprs = replicate_weight_expressions(rep_design_active, frame_work)

        for cutoff in cutoffs:
            estimands = estimands_module.build(spec, cutoff)
            keys = tuple(item.key for item in estimands)

            national_point = linearization.totals(frame_work, estimands, weight=base_weight)
            pop = float(frame_work.select(base_weight.sum()).item() or 0.0)
            obs = int(frame_work.filter(base_weight > 0).height)

            national_reps = replicate_totals(
                frame_work, estimands, rep_weight_exprs, batch_size=64
            )
            national_vars = replicate_variance(
                national_point,
                national_reps,
                keys,
                scale=rep_design_active.scale,
                rscales=rep_design_active.rscales,
                mse=rep_design_active.mse,
            )
            national_report = VarianceReport(
                values=national_vars, degrees=degrees, population=pop, observations=obs
            )
            national_rows = _context_rows(
                national_point, national_report, cutoff, None, None, ci_method, level
            )
            rows.extend(national_rows)

            national_population = pop
            national_m0 = _pick(national_rows, "M0")

            for variable in variables:
                subgroup_reps_dict = replicate_totals(
                    frame_work,
                    estimands,
                    rep_weight_exprs,
                    group_column=variable,
                    batch_size=64,
                )
                subgroups_list = domain_module.levels(frame_work, variable)
                share_total = 0.0
                weighted_m0 = 0.0

                for subgroup in subgroups_list:
                    sub_frame = frame_work.filter(
                        pl.col(variable).cast(pl.String) == subgroup
                    )
                    sub_point = linearization.totals(
                        sub_frame, estimands, weight=base_weight
                    )
                    sub_pop = float(sub_frame.select(base_weight.sum()).item() or 0.0)
                    sub_obs = int(sub_frame.filter(base_weight > 0).height)

                    sub_reps = subgroup_reps_dict.get(subgroup, [])
                    sub_vars = replicate_variance(
                        sub_point,
                        sub_reps,
                        keys,
                        scale=rep_design_active.scale,
                        rscales=rep_design_active.rscales,
                        mse=rep_design_active.mse,
                    )
                    sub_report = VarianceReport(
                        values=sub_vars,
                        degrees=degrees,
                        population=sub_pop,
                        observations=sub_obs,
                    )
                    sub_rows = _context_rows(
                        sub_point, sub_report, cutoff, variable, subgroup, ci_method, level
                    )
                    rows.extend(sub_rows)

                    if national_population:
                        share = sub_pop / national_population
                        share_total += share
                        subgroup_m0 = _pick(sub_rows, "M0")
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
    else:
        raise ValueError(f"unknown variance path: {design.variance_path!r}")

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


def _taylor_report(
    sums: pl.DataFrame,
    estimands: tuple[estimands_module.RatioEstimand, ...],
    keys: tuple[str, ...],
    design: SurveyDesign,
) -> tuple[tuple[linearization.RatioTotals, ...], VarianceReport]:
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

    report = VarianceReport(
        values=variances,
        degrees=degrees,
        population=population,
        observations=observations,
    )
    return ratios, report


def _context_rows(
    ratios: tuple[linearization.RatioTotals, ...],
    report: VarianceReport,
    cutoff: float,
    over: str | None,
    subgroup: str | None,
    ci_method: str,
    level: float,
) -> list[dict[str, object]]:
    """Point estimates, variance and intervals for one (k, domain) context."""

    rows: list[dict[str, object]] = []
    for ratio in ratios:
        estimand = ratio.estimand
        value = ratio.value
        se = standard_error(report.values[estimand.key])
        lower, upper = confidence_interval(
            value, se, report.degrees.df, method=ci_method, level=level
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
                "df": report.degrees.df,
                "psus": report.degrees.psus,
                "strata": report.degrees.strata,
                "obs": report.observations,
                "population": report.population,
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


__all__ = ["DECOMPOSITION_TOLERANCE", "VarianceReport", "estimate"]
