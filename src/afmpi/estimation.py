"""Alkire-Foster estimation with design-based Taylor or replication variance.

The pipeline follows PLAN.md §5: the deprivation engine turns raw indicators
into ``c_i``, the estimand compiler turns ``c_i`` into ratios, and then either
the Taylor path (linearization) or the Replication path (re-estimation per
replicate) is called.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite, sqrt
from numbers import Real

import pandas as pd
import polars as pl
from scipy import stats

from . import change_over_time, deprivation, domain as domain_module, estimands as estimands_module
from . import linearization
from .deprivation import DeprivationMatrix
from .design_base import Design
from .replicate_design import ReplicateDesign
from .replicate_estimation import (
    generate_replicate_weights,
    replicate_totals,
    replicate_variance,
    replicate_vcov,
    replicate_weight_expressions,
)
from .results import EstimationResult
from .specification import Specification
from .survey_design import SurveyDesign
from .testing import HypothesisTest
from .variance import (
    CI_METHODS,
    DesignDegrees,
    coefficient_of_variation,
    confidence_interval,
    design_degrees,
    design_variance,
    design_vcov,
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
    tvar: str | None = None,
    cot_year: str | None = None,
    domain: str | pl.Expr | None = None,
    ci_method: str = "logit",
    level: float = 0.95,
    check_decomposability: bool = True,
    overlap: str = "auto",
    panel_id: str | None = None,
) -> EstimationResult:
    """Estimate Alkire-Foster measures with design-based standard errors."""

    if design is None:
        design = SurveyDesign()
    cutoffs = _validate_cutoffs(k)
    variables = _validate_over(over)
    if ci_method not in CI_METHODS:
        raise ValueError(f"ci_method must be one of {CI_METHODS}; got {ci_method!r}")

    temp_frame = df if isinstance(df, pl.DataFrame) else pl.from_pandas(df)
    change_over_time.validate_time_variables(temp_frame, tvar, cot_year)

    required_vars = list(variables)
    if tvar is not None:
        required_vars.append(tvar)
    if cot_year is not None:
        required_vars.append(cot_year)
    if panel_id is not None and panel_id not in required_vars:
        required_vars.append(panel_id)

    matrix = deprivation.build(
        df,
        spec,
        design,
        required_columns=tuple(required_vars) + design.design_columns,
    )
    return _estimate_from_matrix(
        matrix,
        cutoffs=cutoffs,
        variables=variables,
        tvar=tvar,
        cot_year=cot_year,
        domain=domain,
        ci_method=ci_method,
        level=level,
        check_decomposability=check_decomposability,
        overlap=overlap,
        panel_id=panel_id,
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


def _check_report_diags(
    report: VarianceReport,
    over_name: str | None,
    subgroup_name: str | None,
    cutoff_val: float,
    ratios_tuple: tuple[linearization.RatioTotals, ...],
    design: Design,
    ci_method: str,
    diag_rows: list[dict[str, str]],
) -> None:
    if report.degrees.lonely_strata_keys:
        strata_str = ", ".join(repr(s) for s in report.degrees.lonely_strata_keys)
        ctx_parts = [f"k={cutoff_val}"]
        if over_name:
            ctx_parts.extend([f"over='{over_name}'", f"subgroup='{subgroup_name}'"])
        ctx_str = ", ".join(ctx_parts)
        diag_rows.append({
            "topic": "lonely_psu",
            "context": ctx_str,
            "decision": getattr(design, "lonely_psu", "fail"),
            "detail": f"Stratum/strata [{strata_str}] contain(s) a single PSU",
        })

    if ci_method == "logit":
        for ratio in ratios_tuple:
            val = ratio.value
            if val is not None and (val <= 0.0 or val >= 1.0):
                ctx_parts = [f"measure='{ratio.estimand.measure}'", f"k={cutoff_val}"]
                if over_name:
                    ctx_parts.extend([f"over='{over_name}'", f"subgroup='{subgroup_name}'"])
                ctx_str = ", ".join(ctx_parts)
                diag_rows.append({
                    "topic": "ci_logit",
                    "context": ctx_str,
                    "decision": "fallback_to_linear",
                    "detail": f"estimate {val:.6g} on boundary [0, 1], fallback to linear CI",
                })


def _estimate_from_matrix(
    matrix: DeprivationMatrix,
    *,
    cutoffs: tuple[float, ...],
    variables: tuple[str, ...],
    tvar: str | None = None,
    cot_year: str | None = None,
    domain: str | pl.Expr | None,
    ci_method: str,
    level: float,
    check_decomposability: bool,
    overlap: str = "auto",
    panel_id: str | None = None,
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
    diag_rows: list[dict[str, str]] = []

    if matrix.excluded_observations > 0:
        diag_rows.append({
            "topic": "missing",
            "context": "deprivation_matrix",
            "decision": matrix.missing_report.policy,
            "detail": f"{matrix.excluded_observations} observation(s) excluded by missing-value policy",
        })

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
            _check_report_diags(report, None, None, cutoff, ratios, design, ci_method, diag_rows)
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
                    _check_report_diags(sub_report, variable, subgroup, cutoff, sub_ratios, design, ci_method, diag_rows)
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
            _check_report_diags(national_report, None, None, cutoff, national_point, design, ci_method, diag_rows)
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
                    _check_report_diags(sub_report, variable, subgroup, cutoff, sub_point, design, ci_method, diag_rows)
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
    elif design.variance_path == "census":
        degrees = DesignDegrees(psus=0, strata=0, lonely_strata=0, override_df=0)
        pop = float(frame.select(base_weight.sum()).item() or 0.0)
        obs = int(frame.filter(base_weight > 0).height)
        for cutoff in cutoffs:
            estimands = estimands_module.build(spec, cutoff)
            keys = tuple(item.key for item in estimands)
            ratios = linearization.totals(frame, estimands, weight=base_weight)
            report = VarianceReport(
                values={k: 0.0 for k in keys},
                degrees=degrees,
                population=pop,
                observations=obs,
            )
            national_rows = _context_rows(
                ratios, report, cutoff, None, None, ci_method, level
            )
            rows.extend(national_rows)
            national_population = pop
            national_m0 = _pick(national_rows, "M0")

            for variable in variables:
                subgroups_list = domain_module.levels(frame, variable)
                share_total = 0.0
                weighted_m0 = 0.0
                for subgroup in subgroups_list:
                    sub_frame = frame.filter(pl.col(variable).cast(pl.String) == subgroup)
                    sub_ratios = linearization.totals(sub_frame, estimands, weight=base_weight)
                    sub_pop = float(sub_frame.select(base_weight.sum()).item() or 0.0)
                    sub_obs = int(sub_frame.filter(base_weight > 0).height)
                    sub_report = VarianceReport(
                        values={k: 0.0 for k in keys},
                        degrees=degrees,
                        population=sub_pop,
                        observations=sub_obs,
                    )
                    sub_rows = _context_rows(
                        sub_ratios, sub_report, cutoff, variable, subgroup, ci_method, level
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

    changes_frame = None
    if tvar is not None:
        if ci_method == "logit":
            diag_rows.append({
                "topic": "ci_logit",
                "context": "changes",
                "decision": "fallback_to_t",
                "detail": "logit CI method replaced by 't' for change estimates",
            })
        changes_frame, time_diag_rows = change_over_time.compute_changes(
            matrix,
            cutoffs=cutoffs,
            variables=variables,
            tvar=tvar,
            cot_year=cot_year,
            ci_method=ci_method,
            level=level,
            overlap=overlap,
            panel_id=panel_id,
        )
        diag_rows.extend(time_diag_rows)

    _DIAGNOSTICS_SCHEMA = {
        "topic": pl.String,
        "context": pl.String,
        "decision": pl.String,
        "detail": pl.String,
    }
    diagnostics_frame = pl.DataFrame(diag_rows, schema=_DIAGNOSTICS_SCHEMA).unique(maintain_order=True)

    return EstimationResult(
        _estimates=estimates,
        _decomposition=decomposition_frame,
        _matrix=matrix,
        _cutoffs=cutoffs,
        _over=variables,
        _domain=(base.over, base.subgroup) if not base.is_population else None,
        _ci_method=ci_method,
        _level=level,
        _tvar=tvar,
        _cot_year=cot_year,
        _changes=changes_frame,
        _overlap=overlap,
        _panel_id=panel_id,
        _diagnostics=diagnostics_frame,
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


def _compute_vcov(
    matrix: DeprivationMatrix,
    *,
    cutoffs: tuple[float, ...],
    over_vars: tuple[str, ...],
    k: float | None = None,
    over: str | None = None,
    subgroup: str | None = None,
    measures: Sequence[str] | None = None,
    convert_fn=None,
) -> pl.DataFrame:
    if k is None:
        if len(cutoffs) == 1:
            k = cutoffs[0]
        else:
            raise ValueError(f"multiple cutoffs estimated {cutoffs}; specify k=...")
    if k not in cutoffs:
        raise ValueError(f"cutoff {k} was not estimated; available cutoffs are {cutoffs}")

    if measures is None:
        measures_tuple = ("H", "A", "M0")
    else:
        measures_tuple = tuple(measures)

    if over is not None:
        if over not in over_vars and over not in matrix.frame.columns:
            raise ValueError(f"variable {over!r} not found in estimation over={over_vars!r}")
        if subgroup is None:
            raise ValueError(f"subgroup must be specified when over={over!r}")

    spec = matrix.spec
    design = matrix.design
    frame = matrix.frame
    estimands = estimands_module.build(spec, k)
    estimand_map = {item.key: item for item in estimands}

    for m in measures_tuple:
        if m not in estimand_map:
            raise ValueError(f"unknown measure key: {m!r}")

    if design.variance_path == "taylor":
        group_cols = _stage_group_columns(frame, design)  # type: ignore[arg-type]
        universe = frame.select(list(group_cols)).unique(maintain_order=True)

        if over is None and subgroup is None:
            sums = linearization.cluster_sums(frame, estimands, group_columns=group_cols)
        else:
            cells = linearization.cluster_sums(frame, estimands, group_columns=group_cols + (over,))
            sums = _align(cells, universe, over, subgroup, group_cols)

        ratios = linearization.totals_from_clusters(sums, estimands)
        inf = linearization.cluster_influence(sums, ratios)
        deg = design_degrees(inf)
        vcov_dict, _ = design_vcov(inf, measures_tuple, deg, design)  # type: ignore[arg-type]

    elif design.variance_path == "replication":
        rep_design: ReplicateDesign = design  # type: ignore[assignment]
        if rep_design.replicate_weights is None:
            frame_work, repw_cols, scale, rscales = generate_replicate_weights(frame, rep_design)
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
            scale = rep_design.scale if rep_design.scale is not None else 1.0
            rscales = rep_design.rscales if rep_design.rscales is not None else ((1.0,) * len(rep_design.replicate_weights))
            rep_design_active = rep_design

        rep_weight_exprs = replicate_weight_expressions(rep_design_active, frame_work)

        if over is None and subgroup is None:
            point = linearization.totals(frame_work, estimands)
            replicates_list = replicate_totals(frame_work, estimands, rep_weight_exprs, batch_size=64)  # type: ignore[assignment]
        else:
            sub_frame = frame_work.filter(pl.col(over).cast(pl.String) == subgroup)
            point = linearization.totals(sub_frame, estimands)
            sub_dict = replicate_totals(frame_work, estimands, rep_weight_exprs, group_column=over, batch_size=64)
            replicates_list = sub_dict.get(subgroup, [])  # type: ignore[assignment]

        vcov_dict = replicate_vcov(point, replicates_list, measures_tuple, scale=scale, rscales=rscales, mse=rep_design_active.mse)

    else:  # Census
        vcov_dict = {(k1, k2): 0.0 for k1 in measures_tuple for k2 in measures_tuple}

    matrix_rows = []
    for m1 in measures_tuple:
        row_dict = {"term": m1}
        for m2 in measures_tuple:
            val1 = vcov_dict.get((m1, m2), float("nan"))
            val2 = vcov_dict.get((m2, m1), float("nan"))
            sym_val = (val1 + val2) / 2.0
            row_dict[m2] = sym_val
        matrix_rows.append(row_dict)

    res_df = pl.DataFrame(matrix_rows)
    if convert_fn:
        return convert_fn(res_df)
    return res_df


def _compute_test(
    matrix: DeprivationMatrix,
    *,
    cutoffs: tuple[float, ...],
    a: object,
    b: object = None,
    measure: str = "M0",
    k: float | None = None,
    dist: str = "F",
) -> HypothesisTest:
    if k is None:
        if len(cutoffs) == 1:
            k = cutoffs[0]
        else:
            raise ValueError(f"multiple cutoffs estimated {cutoffs}; specify k=...")
    if k not in cutoffs:
        raise ValueError(f"cutoff {k} was not estimated; available cutoffs are {cutoffs}")

    if dist not in ("F", "chisq"):
        raise ValueError(f"dist must be 'F' or 'chisq'; got {dist!r}")

    spec = matrix.spec
    design = matrix.design
    frame = matrix.frame

    estimands = estimands_module.build(spec, k)
    estimand_map = {item.key: item for item in estimands}
    if measure not in estimand_map:
        raise ValueError(f"unknown measure: {measure!r}")

    def _parse_arg(arg: object) -> tuple[domain_module.Domain, str]:
        if isinstance(arg, tuple):
            ov, sg = arg
            dom = domain_module.of_level(ov, str(sg))
            return dom, f"{ov}={sg}"
        elif isinstance(arg, str):
            dom = domain_module.from_expression(arg)
            return dom, arg
        elif isinstance(arg, domain_module.Domain):
            return arg, arg.label
        else:
            raise TypeError(f"domain argument must be a string expression or (over, subgroup) tuple; got {arg!r}")

    dom_a, label_a = _parse_arg(a)

    if b is not None:
        dom_b, label_b = _parse_arg(b)
        terms = (label_a, label_b)
    else:
        dom_b = None
        terms = (label_a,)

    target_item = estimand_map[measure]

    if design.variance_path == "taylor":
        group_cols = _stage_group_columns(frame, design)  # type: ignore[arg-type]

        w_a = dom_a.weight()
        sums_a = frame.group_by(list(group_cols)).agg(
            (w_a * target_item.y).sum().alias(linearization._NUMERATOR_PREFIX + target_item.key),
            (w_a * target_item.x).sum().alias(linearization._DENOMINATOR_PREFIX + target_item.key),
            pl.col(deprivation.WEIGHT).sum().alias("__afmpi_cluster_weight"),
            pl.len().alias("__afmpi_cluster_rows"),
        )
        ratios_a = linearization.totals_from_clusters(sums_a, (target_item,))
        inf_a = linearization.cluster_influence(sums_a, ratios_a).rename({target_item.key: "inf_a"})
        r_a = ratios_a[0].value

        if dom_b is not None:
            w_b = dom_b.weight()
            sums_b = frame.group_by(list(group_cols)).agg(
                (w_b * target_item.y).sum().alias(linearization._NUMERATOR_PREFIX + target_item.key),
                (w_b * target_item.x).sum().alias(linearization._DENOMINATOR_PREFIX + target_item.key),
                pl.col(deprivation.WEIGHT).sum().alias("__afmpi_cluster_weight"),
                pl.len().alias("__afmpi_cluster_rows"),
            )
            ratios_b = linearization.totals_from_clusters(sums_b, (target_item,))
            inf_b = linearization.cluster_influence(sums_b, ratios_b).rename({target_item.key: "inf_b"})
            r_b = ratios_b[0].value

            join_cols = list(group_cols)
            cluster_inf = inf_a.join(inf_b.select(*group_cols, "inf_b"), on=join_cols, how="left")
            keys_test = ("inf_a", "inf_b")
        else:
            r_b = None
            cluster_inf = inf_a
            keys_test = ("inf_a",)
        full_degrees = design_degrees(cluster_inf)

        vcov_dict, _ = design_vcov(cluster_inf, keys_test, full_degrees, design)  # type: ignore[arg-type]

        v_aa = vcov_dict.get(("inf_a", "inf_a"), float("nan"))
        if dom_b is not None:
            v_bb = vcov_dict.get(("inf_b", "inf_b"), float("nan"))
            v_ab = vcov_dict.get(("inf_a", "inf_b"), float("nan"))
        else:
            v_bb = 0.0
            v_ab = 0.0

        theta_a = r_a
        theta_b = r_b

    elif design.variance_path == "replication":
        rep_design: ReplicateDesign = design  # type: ignore[assignment]
        if rep_design.replicate_weights is None:
            frame_work, repw_cols, scale, rscales = generate_replicate_weights(frame, rep_design)
            if rep_design.method == "JKn" and rep_design.strata is not None:
                H = frame_work.select(pl.col(rep_design.strata).cast(pl.String)).n_unique()
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
            scale = rep_design.scale if rep_design.scale is not None else 1.0
            rscales = rep_design.rscales if rep_design.rscales is not None else ((1.0,) * len(rep_design.replicate_weights))
            if rep_design.method == "JKn" and rep_design.strata is not None:
                H = frame_work.select(pl.col(rep_design.strata).cast(pl.String)).n_unique()
            else:
                H = 1
            rep_design_active = rep_design

        rep_weight_exprs = replicate_weight_expressions(rep_design_active, frame_work)
        R = len(rep_weight_exprs)
        df_strata = H if (rep_design.method == "JKn" and (rep_design.strata is not None or rep_design.replicate_weights is None)) else 1
        full_degrees = DesignDegrees(psus=R, strata=df_strata, lonely_strata=0, override_df=rep_design.degf)

        w_a = dom_a.weight()
        pt_a = linearization.totals(frame_work, (target_item,), weight=w_a)[0]
        theta_a = pt_a.value
        reps_a = replicate_totals(frame_work, (target_item,), [w * (w_a > 0).cast(pl.Float64) for w in rep_weight_exprs], batch_size=64)

        if dom_b is not None:
            w_b = dom_b.weight()
            pt_b = linearization.totals(frame_work, (target_item,), weight=w_b)[0]
            theta_b = pt_b.value
            reps_b = replicate_totals(frame_work, (target_item,), [w * (w_b > 0).cast(pl.Float64) for w in rep_weight_exprs], batch_size=64)
        else:
            theta_b = None
            reps_b = None

        theta_c_a = theta_a if rep_design_active.mse else sum(r[0].value for r in reps_a if r[0].value is not None) / R
        v_aa = scale * sum(rscales[r] * ((reps_a[r][0].value - theta_c_a) ** 2) for r in range(R))

        if dom_b is not None:
            theta_c_b = theta_b if rep_design_active.mse else sum(r[0].value for r in reps_b if r[0].value is not None) / R
            v_bb = scale * sum(rscales[r] * ((reps_b[r][0].value - theta_c_b) ** 2) for r in range(R))
            v_ab = scale * sum(rscales[r] * (reps_a[r][0].value - theta_c_a) * (reps_b[r][0].value - theta_c_b) for r in range(R))
        else:
            v_bb = 0.0
            v_ab = 0.0

    else:  # Census
        w_a = dom_a.weight()
        pt_a = linearization.totals(frame, (target_item,), weight=w_a)[0]
        theta_a = pt_a.value
        if dom_b is not None:
            w_b = dom_b.weight()
            pt_b = linearization.totals(frame, (target_item,), weight=w_b)[0]
            theta_b = pt_b.value
        else:
            theta_b = None
        v_aa = 0.0
        v_bb = 0.0
        v_ab = 0.0
        full_degrees = DesignDegrees(psus=0, strata=0, lonely_strata=0, override_df=0)

    df2 = full_degrees.df
    q = 1

    if dom_b is not None:
        diff = theta_a - theta_b
        var_contrast = v_aa + v_bb - 2.0 * v_ab
    else:
        diff = theta_a
        var_contrast = v_aa

    if (dom_b is not None and label_a == label_b) or (diff == 0.0 and var_contrast == 0.0):
        estimate = 0.0 if dom_b is not None else theta_a
        se = 0.0
        statistic = 0.0
        p_value = 1.0
    else:
        estimate = float(diff)
        if var_contrast < 0 or not isfinite(var_contrast):
            se = float("nan")
            statistic = float("nan")
            p_value = float("nan")
        else:
            se = sqrt(var_contrast)
            if df2 < 1 or se == 0.0:
                statistic = float("nan")
                p_value = float("nan")
            else:
                W = (estimate ** 2) / var_contrast
                if dist == "F":
                    statistic = float(W / q)
                    p_value = float(stats.f.sf(statistic, q, df2))
                else:
                    statistic = float(W)
                    p_value = float(stats.chi2.sf(statistic, q))

    return HypothesisTest(
        terms=terms,
        estimate=estimate,
        se=se,
        statistic=statistic,
        df1=q,
        df2=df2,
        p_value=p_value,
        method="Wald",
        dist=dist,
    )


__all__ = ["DECOMPOSITION_TOLERANCE", "VarianceReport", "_compute_test", "_compute_vcov", "estimate"]

