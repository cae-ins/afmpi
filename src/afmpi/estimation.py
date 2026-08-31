"""Alkire-Foster estimation with design-based Taylor or replication variance.

The pipeline follows PLAN.md §5: the deprivation engine turns raw indicators
into ``c_i``, the estimand compiler turns ``c_i`` into ratios, and then either
the Taylor path (linearization), Replication path, or Census path is called.
"""

from __future__ import annotations

import os
import warnings
from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite, sqrt
from numbers import Real

import pandas as pd
import polars as pl
from scipy import stats

from . import backend, change_over_time, deprivation, linearization, missing
from . import domain as domain_module
from . import estimands as estimands_module
from .census_design import CensusDesign
from .deprivation import DeprivationMatrix
from .design_base import Design
from .execution_config import ExecutionConfig
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


@dataclass(frozen=True, slots=True)
class LazyEstimation:
    """Lazy evaluation context for Alkire-Foster estimation (PLAN.md §14.9)."""

    df: object
    spec: Specification
    design: Design | None
    k: float | Sequence[float]
    over: str | Sequence[str] | None
    tvar: str | None
    cot_year: str | None
    domain: str | pl.Expr | None
    ci_method: str
    level: float
    check_decomposability: bool
    overlap: str
    panel_id: str | None
    resources: ExecutionConfig | None = None
    streaming: bool = False
    projected_columns: list[str] | None = None

    def collect(self) -> EstimationResult:
        """Materialise the lazy estimation plan and return the EstimationResult."""

        return _execute_estimation(
            df=self.df,
            spec=self.spec,
            design=self.design,
            k=self.k,
            over=self.over,
            tvar=self.tvar,
            cot_year=self.cot_year,
            domain=self.domain,
            ci_method=self.ci_method,
            level=self.level,
            check_decomposability=self.check_decomposability,
            overlap=self.overlap,
            panel_id=self.panel_id,
            resources=self.resources,
            streaming=self.streaming,
            projected_columns=self.projected_columns,
            is_lazy_collect=True,
        )


def estimate(
    df: pd.DataFrame | pl.DataFrame | pl.LazyFrame | object,
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
    lazy: bool = False,
    resources: ExecutionConfig | None = None,
    streaming: bool = False,
    projected_columns: list[str] | None = None,
) -> EstimationResult | LazyEstimation:
    """Estimate Alkire-Foster measures with design-based standard errors.

    Note on CensusDesign: when ``design=CensusDesign(...)``, sampling variance is
    identically zero (se=0.0, lci=uci=est), and ``ci_method`` is ignored.
    """

    if lazy:
        return LazyEstimation(
            df=df,
            spec=spec,
            design=design,
            k=k,
            over=over,
            tvar=tvar,
            cot_year=cot_year,
            domain=domain,
            ci_method=ci_method,
            level=level,
            check_decomposability=check_decomposability,
            overlap=overlap,
            panel_id=panel_id,
            resources=resources,
            streaming=streaming,
            projected_columns=projected_columns,
        )

    return _execute_estimation(
        df=df,
        spec=spec,
        design=design,
        k=k,
        over=over,
        tvar=tvar,
        cot_year=cot_year,
        domain=domain,
        ci_method=ci_method,
        level=level,
        check_decomposability=check_decomposability,
        overlap=overlap,
        panel_id=panel_id,
        resources=resources,
        streaming=streaming,
        projected_columns=projected_columns,
    )


def _run_in_subprocess(kwargs: dict) -> EstimationResult:
    import pickle
    import subprocess
    import sys

    resources = kwargs.get("resources")
    if resources is not None:
        kwargs["resources"] = ExecutionConfig(
            max_threads=resources.max_threads,
            isolated_process=False,
            memory_limit=resources.memory_limit,
            spill_dir=resources.spill_dir,
            batch_size=resources.batch_size,
        )

    code = (
        "import os, pickle, sys\n"
        f"sys.path = {sys.path!r}\n"
        "payload = pickle.loads(sys.stdin.buffer.read())\n"
        "mt = payload.pop('max_threads', None)\n"
        "if mt is not None:\n"
        "    os.environ['POLARS_MAX_THREADS'] = str(mt)\n"
        "from afmpi.estimation import _execute_estimation\n"
        "try:\n"
        "    res = _execute_estimation(**payload)\n"
        "    sys.stdout.buffer.write(pickle.dumps((True, res)))\n"
        "except Exception as e:\n"
        "    sys.stdout.buffer.write(pickle.dumps((False, e)))\n"
    )

    proc = subprocess.run(
        [sys.executable, "-c", code],
        input=pickle.dumps(kwargs),
        capture_output=True,
        check=True,
    )
    success, val = pickle.loads(proc.stdout)
    if not success:
        raise val
    return val


def _execute_estimation(
    df: object,
    spec: Specification,
    design: Design | None,
    k: float | Sequence[float],
    over: str | Sequence[str] | None,
    tvar: str | None,
    cot_year: str | None,
    domain: str | pl.Expr | None,
    ci_method: str,
    level: float,
    check_decomposability: bool,
    overlap: str,
    panel_id: str | None,
    resources: ExecutionConfig | None = None,
    streaming: bool = False,
    projected_columns: list[str] | None = None,
    is_lazy_collect: bool = False,
) -> EstimationResult:
    if design is None:
        design = SurveyDesign()

    if resources is not None and resources.isolated_process:
        kwargs = {
            "df": df,
            "spec": spec,
            "design": design,
            "k": k,
            "over": over,
            "tvar": tvar,
            "cot_year": cot_year,
            "domain": domain,
            "ci_method": ci_method,
            "level": level,
            "check_decomposability": check_decomposability,
            "overlap": overlap,
            "panel_id": panel_id,
            "resources": resources,
            "streaming": streaming,
            "projected_columns": projected_columns,
            "is_lazy_collect": is_lazy_collect,
            "max_threads": resources.max_threads,
        }
        return _run_in_subprocess(kwargs)

    if resources is not None and resources.max_threads is not None:
        requested = str(resources.max_threads)
        existing = os.environ.get("POLARS_MAX_THREADS")
        # Polars reads POLARS_MAX_THREADS once, at the first Polars operation of the
        # process -- there is no per-call thread pool. `setdefault` avoids clobbering
        # a value another `estimate()` call (or the user) already set; either way, if
        # this is not the first Polars operation in this process, the setting below
        # is silently ignored by Polars, hence the warning rather than a false promise.
        os.environ.setdefault("POLARS_MAX_THREADS", requested)
        if existing not in (None, requested):
            warnings.warn(
                f"ExecutionConfig(max_threads={resources.max_threads}) has no effect: "
                f"POLARS_MAX_THREADS is already set to {existing!r} for this process. "
                "Polars' thread pool is global to the process and read once, at the "
                "first Polars operation -- it cannot be reconfigured per call.",
                stacklevel=2,
            )

    cutoffs = _validate_cutoffs(k)
    variables = _validate_over(over)
    if ci_method not in CI_METHODS:
        raise ValueError(f"ci_method must be one of {CI_METHODS}; got {ci_method!r}")

    frame_obj, input_kind = backend.to_frame(df)

    is_lazy_path = (
        isinstance(frame_obj, pl.LazyFrame)
        or input_kind in ("parquet", "polars-lazy")
        or streaming
        or is_lazy_collect
    )

    if not is_lazy_path:
        temp_frame = frame_obj if isinstance(frame_obj, pl.DataFrame) else pl.from_pandas(df)
        change_over_time.validate_time_variables(temp_frame, tvar, cot_year)

        required_vars = list(variables)
        if tvar is not None:
            required_vars.append(tvar)
        if cot_year is not None:
            required_vars.append(cot_year)
        if panel_id is not None and panel_id not in required_vars:
            required_vars.append(panel_id)

        batch_size_override = resources.batch_size if resources is not None else None
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
            batch_size=batch_size_override,
            projected_columns=projected_columns,
            input_kind=input_kind,
        )

    return _estimate_lazy(
        frame_obj=frame_obj,
        input_kind=input_kind,
        spec=spec,
        design=design,
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
        resources=resources,
        streaming=streaming,
        projected_columns=projected_columns,
    )


def _estimate_lazy(
    frame_obj: pl.DataFrame | pl.LazyFrame,
    input_kind: str,
    spec: Specification,
    design: Design,
    cutoffs: tuple[float, ...],
    variables: tuple[str, ...],
    tvar: str | None,
    cot_year: str | None,
    domain: str | pl.Expr | None,
    ci_method: str,
    level: float,
    check_decomposability: bool,
    overlap: str,
    panel_id: str | None,
    resources: ExecutionConfig | None = None,
    streaming: bool = False,
    projected_columns: list[str] | None = None,
) -> EstimationResult:
    lf = frame_obj.lazy() if isinstance(frame_obj, pl.DataFrame) else frame_obj

    w_col = design.weights
    h_col = design.household_size
    if w_col is not None and h_col is not None:
        weight_expr = pl.col(w_col).cast(pl.Float64) * pl.col(h_col).cast(pl.Float64)
    elif w_col is not None:
        weight_expr = pl.col(w_col).cast(pl.Float64)
    elif h_col is not None:
        weight_expr = pl.col(h_col).cast(pl.Float64)
    else:
        weight_expr = pl.lit(1.0, dtype=pl.Float64)

    lf = lf.with_columns(weight_expr.alias(deprivation.WEIGHT))

    lf_scored = missing.apply_transform(lf, spec)
    lf_scored = _add_design_identifiers_lazy(lf_scored, design)

    if domain is not None:
        if isinstance(domain, str):
            domain_expr = pl.sql_expr(domain)
        elif isinstance(domain, pl.Expr):
            domain_expr = domain
        else:
            raise TypeError("domain must be a string expression or a polars expression")
        domain_cond = domain_expr
        domain_weight = pl.col(deprivation.WEIGHT) * pl.when(domain_cond).then(1.0).otherwise(
            0.0
        )
    else:
        domain_cond = None
        domain_weight = pl.col(deprivation.WEIGHT)

    all_k_estimands: list[estimands_module.RatioEstimand] = []
    k_estimand_map: dict[float, tuple[estimands_module.RatioEstimand, ...]] = {}

    for cutoff in cutoffs:
        raw_estimands = estimands_module.build(spec, cutoff)
        k_estimand_map[cutoff] = raw_estimands
        for item in raw_estimands:
            prefixed_key = f"k_{cutoff}__" + item.key
            prefixed_estimand = estimands_module.RatioEstimand(
                key=prefixed_key,
                y=item.y,
                x=item.x,
                measure=item.measure,
                indicator=item.indicator,
                dimension=item.dimension,
                weight=item.weight,
            )
            all_k_estimands.append(prefixed_estimand)

    if design.variance_path == "census":
        plan_nat = lf_scored.select(
            *linearization._totals_exprs(all_k_estimands, domain_weight),
            domain_weight.sum().alias("__afmpi_cluster_weight"),
            (domain_weight > 0).sum().alias("__afmpi_cluster_rows"),
        )
        over_plans = [
            lf_scored.group_by(var).agg(
                *linearization._totals_exprs(all_k_estimands, domain_weight),
                domain_weight.sum().alias("__afmpi_cluster_weight"),
                (domain_weight > 0).sum().alias("__afmpi_cluster_rows"),
            )
            for var in variables
        ]
    elif design.variance_path == "taylor":
        survey_design: SurveyDesign = design  # type: ignore[assignment]
        group_cols = _stage_group_columns_lazy(lf_scored, survey_design)
        plan_nat = linearization.cluster_sums_lazy(
            lf_scored, all_k_estimands, weight=domain_weight, group_columns=group_cols
        )
        over_plans = [
            linearization.cluster_sums_lazy(
                lf_scored,
                all_k_estimands,
                weight=domain_weight,
                group_columns=tuple(group_cols) + (var,),
            )
            for var in variables
        ]
    elif design.variance_path == "replication":
        rep_design: ReplicateDesign = design  # type: ignore[assignment]
        if rep_design.replicate_weights is None:
            lf_scored, repw_cols, scale, rscales = generate_replicate_weights(
                lf_scored, rep_design
            )
            if rep_design.method == "JKn" and rep_design.strata is not None:
                H = (
                    lf_scored.select(pl.col(rep_design.strata).cast(pl.String))
                    .collect()
                    .n_unique()
                )
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
            scale = rep_design.scale if rep_design.scale is not None else 1.0
            rscales = (
                rep_design.rscales
                if rep_design.rscales is not None
                else ((1.0,) * len(rep_design.replicate_weights))
            )
            if rep_design.method == "JKn" and rep_design.strata is not None:
                H = (
                    lf_scored.select(pl.col(rep_design.strata).cast(pl.String))
                    .collect()
                    .n_unique()
                )
            else:
                H = 1
            rep_design_active = rep_design

        rep_weight_exprs = replicate_weight_expressions(rep_design_active, lf_scored)
        R = len(rep_weight_exprs)
        df_strata = (
            H
            if (
                rep_design.method == "JKn"
                and (rep_design.strata is not None or rep_design.replicate_weights is None)
            )
            else 1
        )
        degrees = DesignDegrees(
            psus=R,
            strata=df_strata,
            lonely_strata=0,
            override_df=rep_design.degf,
        )

        select_exprs = [
            *linearization._totals_exprs(all_k_estimands, domain_weight),
            domain_weight.sum().alias("__afmpi_cluster_weight"),
            (domain_weight > 0).sum().alias("__afmpi_cluster_rows"),
        ]
        for r, w_r in enumerate(rep_weight_exprs):
            w_r_active = w_r * domain_cond.cast(pl.Float64) if domain_cond is not None else w_r
            for item in all_k_estimands:
                select_exprs.append((w_r_active * item.y).sum().alias(f"y_rep_{r}_{item.key}"))
                select_exprs.append((w_r_active * item.x).sum().alias(f"x_rep_{r}_{item.key}"))

        plan_nat = lf_scored.select(select_exprs)
        over_plans = [lf_scored.group_by(var).agg(select_exprs) for var in variables]
    else:
        raise ValueError(f"unknown variance path: {design.variance_path!r}")

    all_plans = [plan_nat, *over_plans]
    engine = "streaming" if streaming else "auto"
    collected_frames = pl.collect_all(all_plans, engine=engine)

    nat_res = collected_frames[0]
    over_res = collected_frames[1:]

    rows: list[dict[str, object]] = []
    decomposition: list[dict[str, object]] = []
    diag_rows: list[dict[str, str]] = []

    if projected_columns is not None:
        diag_rows.append(
            {
                "topic": "projection_pushdown",
                "context": "from_parquet",
                "decision": "selected_columns",
                "detail": ", ".join(sorted(projected_columns)),
            }
        )

    if domain is not None:
        pop_active = float(nat_res.row(0, named=True).get("__afmpi_cluster_rows") or 0)
        diag_rows.append(
            {
                "topic": "domain",
                "context": str(domain),
                "decision": "subpopulation_filter",
                "detail": f"active rows: {int(pop_active)}",
            }
        )

    nat_rows: list[dict[str, object]] = []

    for cutoff in cutoffs:
        raw_estimands = k_estimand_map[cutoff]
        prefix = f"k_{cutoff}__"

        if design.variance_path == "census":
            nat_dict = nat_res.row(0, named=True)
            pop = float(nat_dict.get("__afmpi_cluster_weight") or 0.0)
            obs = int(nat_dict.get("__afmpi_cluster_rows") or 0)
            ratios = tuple(
                linearization.RatioTotals(
                    estimand=item,
                    numerator=float(
                        nat_dict.get(linearization._NUMERATOR_PREFIX + prefix + item.key) or 0.0
                    ),
                    denominator=float(
                        nat_dict.get(linearization._DENOMINATOR_PREFIX + prefix + item.key)
                        or 0.0
                    ),
                )
                for item in raw_estimands
            )
            if not pop and ratios:
                pop = ratios[0].denominator
            degrees = DesignDegrees(psus=0, strata=0, lonely_strata=0, override_df=0)
            keys = tuple(item.key for item in raw_estimands)
            report = VarianceReport(
                values={k: 0.0 for k in keys}, degrees=degrees, population=pop, observations=obs
            )
            nat_rows = _context_rows(ratios, report, cutoff, None, None, ci_method, level)
            rows.extend(nat_rows)
            national_population = pop
            national_m0 = _pick(nat_rows, "M0")

            for idx, variable in enumerate(variables):
                over_df = over_res[idx]
                over_dicts = over_df.to_dicts()
                over_dicts.sort(
                    key=lambda r: str(r[variable]) if r[variable] is not None else ""
                )
                share_total = 0.0
                weighted_m0 = 0.0
                for row_dict in over_dicts:
                    val = row_dict[variable]
                    if val is None:
                        continue
                    subgroup = str(val)
                    sub_pop = float(row_dict.get("__afmpi_cluster_weight") or 0.0)
                    sub_obs = int(row_dict.get("__afmpi_cluster_rows") or 0)
                    sub_ratios = tuple(
                        linearization.RatioTotals(
                            estimand=item,
                            numerator=float(
                                row_dict.get(
                                    linearization._NUMERATOR_PREFIX + prefix + item.key
                                )
                                or 0.0
                            ),
                            denominator=float(
                                row_dict.get(
                                    linearization._DENOMINATOR_PREFIX + prefix + item.key
                                )
                                or 0.0
                            ),
                        )
                        for item in raw_estimands
                    )
                    if not sub_pop and sub_ratios:
                        sub_pop = sub_ratios[0].denominator
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
        elif design.variance_path == "taylor":
            survey_design_taylor: SurveyDesign = design  # type: ignore[assignment]
            group_cols = _stage_group_columns_lazy(lf_scored, survey_design_taylor)
            universe = nat_res.select(list(group_cols)).unique(maintain_order=True)

            nat_sub = _extract_cutoff_sums(nat_res, raw_estimands, prefix)
            ratios, report = _taylor_report(
                nat_sub,
                raw_estimands,
                tuple(item.key for item in raw_estimands),
                survey_design_taylor,
            )
            _check_report_diags(
                report, None, None, cutoff, ratios, design, ci_method, diag_rows
            )
            nat_rows = _context_rows(ratios, report, cutoff, None, None, ci_method, level)
            rows.extend(nat_rows)
            national_population = report.population
            national_m0 = _pick(nat_rows, "M0")

            for idx, variable in enumerate(variables):
                over_df = over_res[idx]
                subgroups_list = sorted(
                    [
                        str(v)
                        for v in over_df.select(variable).unique().to_series().to_list()
                        if v is not None
                    ]
                )
                share_total = 0.0
                weighted_m0 = 0.0
                for subgroup in subgroups_list:
                    sub_sums = _align(over_df, universe, variable, subgroup, group_cols)
                    sub_sub = _extract_cutoff_sums(sub_sums, raw_estimands, prefix)
                    sub_ratios, sub_report = _taylor_report(
                        sub_sub,
                        raw_estimands,
                        tuple(item.key for item in raw_estimands),
                        survey_design_taylor,
                    )
                    _check_report_diags(
                        sub_report,
                        variable,
                        subgroup,
                        cutoff,
                        sub_ratios,
                        design,
                        ci_method,
                        diag_rows,
                    )
                    sub_rows = _context_rows(
                        sub_ratios, sub_report, cutoff, variable, subgroup, ci_method, level
                    )
                    rows.extend(sub_rows)

                    if national_population:
                        share = sub_report.population / national_population
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
        elif design.variance_path == "replication":
            keys = tuple(item.key for item in raw_estimands)
            nat_dict = nat_res.row(0, named=True)
            pop = float(nat_dict.get("__afmpi_cluster_weight") or 0.0)
            obs = int(nat_dict.get("__afmpi_cluster_rows") or 0)
            nat_point = tuple(
                linearization.RatioTotals(
                    estimand=item,
                    numerator=float(
                        nat_dict.get(linearization._NUMERATOR_PREFIX + prefix + item.key) or 0.0
                    ),
                    denominator=float(
                        nat_dict.get(linearization._DENOMINATOR_PREFIX + prefix + item.key)
                        or 0.0
                    ),
                )
                for item in raw_estimands
            )
            nat_reps = [
                tuple(
                    linearization.RatioTotals(
                        estimand=item,
                        numerator=float(nat_dict.get(f"y_rep_{r}_{prefix}{item.key}") or 0.0),
                        denominator=float(nat_dict.get(f"x_rep_{r}_{prefix}{item.key}") or 0.0),
                    )
                    for item in raw_estimands
                )
                for r in range(R)
            ]
            nat_vars = replicate_variance(
                nat_point,
                nat_reps,
                keys,
                scale=scale,
                rscales=rscales,
                mse=rep_design_active.mse,
            )
            nat_report = VarianceReport(
                values=nat_vars,
                degrees=degrees,
                population=pop,
                observations=obs,
            )
            _check_report_diags(
                nat_report, None, None, cutoff, nat_point, design, ci_method, diag_rows
            )
            nat_rows = _context_rows(
                nat_point, nat_report, cutoff, None, None, ci_method, level
            )
            rows.extend(nat_rows)
            national_population = pop
            national_m0 = _pick(nat_rows, "M0")

            for idx, variable in enumerate(variables):
                over_df = over_res[idx]
                over_dicts = over_df.to_dicts()
                over_dicts.sort(
                    key=lambda r: str(r[variable]) if r[variable] is not None else ""
                )
                share_total = 0.0
                weighted_m0 = 0.0
                for row_dict in over_dicts:
                    val = row_dict[variable]
                    if val is None:
                        continue
                    subgroup = str(val)
                    sub_pop = float(row_dict.get("__afmpi_cluster_weight") or 0.0)
                    sub_obs = int(row_dict.get("__afmpi_cluster_rows") or 0)
                    sub_point = tuple(
                        linearization.RatioTotals(
                            estimand=item,
                            numerator=float(
                                row_dict.get(
                                    linearization._NUMERATOR_PREFIX + prefix + item.key
                                )
                                or 0.0
                            ),
                            denominator=float(
                                row_dict.get(
                                    linearization._DENOMINATOR_PREFIX + prefix + item.key
                                )
                                or 0.0
                            ),
                        )
                        for item in raw_estimands
                    )
                    sub_reps = [
                        tuple(
                            linearization.RatioTotals(
                                estimand=item,
                                numerator=float(
                                    row_dict.get(f"y_rep_{r}_{prefix}{item.key}") or 0.0
                                ),
                                denominator=float(
                                    row_dict.get(f"x_rep_{r}_{prefix}{item.key}") or 0.0
                                ),
                            )
                            for item in raw_estimands
                        )
                        for r in range(R)
                    ]
                    sub_vars = replicate_variance(
                        sub_point,
                        sub_reps,
                        keys,
                        scale=scale,
                        rscales=rscales,
                        mse=rep_design_active.mse,
                    )
                    sub_report = VarianceReport(
                        values=sub_vars,
                        degrees=degrees,
                        population=sub_pop,
                        observations=sub_obs,
                    )
                    _check_report_diags(
                        sub_report,
                        variable,
                        subgroup,
                        cutoff,
                        sub_point,
                        design,
                        ci_method,
                        diag_rows,
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

    _DIAGNOSTICS_SCHEMA = {
        "topic": pl.String,
        "context": pl.String,
        "decision": pl.String,
        "detail": pl.String,
    }
    diagnostics_frame = pl.DataFrame(diag_rows, schema=_DIAGNOSTICS_SCHEMA).unique(
        maintain_order=True
    )

    out_kind = "pandas" if input_kind == "pandas" else "polars"

    return EstimationResult(
        _estimates=estimates,
        _decomposition=decomposition_frame,
        _matrix=None,
        _cutoffs=cutoffs,
        _over=variables,
        _domain=(None, domain if isinstance(domain, str) else "domain")
        if domain is not None
        else None,
        _ci_method=ci_method,
        _level=level,
        _tvar=tvar,
        _cot_year=cot_year,
        _changes=None,
        _overlap=overlap,
        _panel_id=panel_id,
        _diagnostics=diagnostics_frame,
        observations=nat_rows[0]["obs"] if nat_rows else 0,
        excluded_observations=0,
        _input_kind=out_kind,
        _design=design,
    )


def _extract_cutoff_sums(
    sums: pl.DataFrame,
    raw_estimands: tuple[estimands_module.RatioEstimand, ...],
    prefix: str,
) -> pl.DataFrame:
    rename_map = {}
    for item in raw_estimands:
        old_num = linearization._NUMERATOR_PREFIX + prefix + item.key
        new_num = linearization._NUMERATOR_PREFIX + item.key
        old_den = linearization._DENOMINATOR_PREFIX + prefix + item.key
        new_den = linearization._DENOMINATOR_PREFIX + item.key
        if old_num in sums.columns:
            rename_map[old_num] = new_num
        if old_den in sums.columns:
            rename_map[old_den] = new_den
    return sums.rename(rename_map)


def _add_design_identifiers_lazy(lf: pl.LazyFrame, design: Design) -> pl.LazyFrame:
    if isinstance(design, (CensusDesign, ReplicateDesign)):
        return lf
    if isinstance(design, SurveyDesign):
        stages = design.resolved_stages
        depth = max(1, len(stages))
        if depth == 1 and not stages:
            s_name = design.strata
            p_name = design.psu
            s_expr = (
                pl.col(s_name).cast(pl.String).fill_null("__afmpi_null__")
                if s_name
                else pl.lit("__afmpi_all__")
            )
            p_expr = (
                (
                    s_expr
                    + pl.lit("|")
                    + pl.col(p_name).cast(pl.String).fill_null("__afmpi_null__")
                )
                if p_name
                else (
                    s_expr
                    + pl.lit("|")
                    + pl.int_range(0, pl.len(), dtype=pl.Int64).cast(pl.String)
                )
            )
            lf = lf.with_columns(
                [
                    s_expr.alias(deprivation.STRATUM),
                    p_expr.alias(deprivation.PSU),
                    pl.lit(0.0).alias(deprivation.fraction_column(1)),
                ]
            )
        else:
            for idx, stage in enumerate(stages, start=1):
                s_col = deprivation.stratum_column(idx)
                p_col = deprivation.psu_column(idx)
                f_col = deprivation.fraction_column(idx)
                if idx == 1:
                    stratum_expr = (
                        pl.col(stage.strata).cast(pl.String).fill_null("__afmpi_null__")
                        if stage.strata
                        else pl.lit("__afmpi_all__")
                    )
                else:
                    prev_psu = pl.col(deprivation.psu_column(idx - 1))
                    stratum_expr = (
                        prev_psu
                        + pl.lit("|")
                        + (
                            pl.col(stage.strata).cast(pl.String).fill_null("__afmpi_null__")
                            if stage.strata
                            else pl.lit("")
                        )
                    )

                psu_expr = (
                    stratum_expr
                    + pl.lit("|")
                    + pl.col(stage.id).cast(pl.String).fill_null("__afmpi_null__")
                )
                stage_exprs = [
                    stratum_expr.alias(s_col),
                    psu_expr.alias(p_col),
                ]
                if stage.fpc is not None:
                    fpc_col = pl.col(stage.fpc).cast(pl.Float64)
                    m_expr = psu_expr.n_unique().over(stratum_expr)
                    f_expr = (
                        pl.when(fpc_col <= 1.0)
                        .then(fpc_col)
                        .otherwise(m_expr.cast(pl.Float64) / fpc_col)
                        .fill_null(0.0)
                    )
                    stage_exprs.append(f_expr.alias(f_col))
                else:
                    stage_exprs.append(pl.lit(0.0).alias(f_col))

                lf = lf.with_columns(stage_exprs)

        if design.pps is not None and design.pps.inclusion_probability is not None:
            lf = lf.with_columns(
                pl.col(design.pps.inclusion_probability).cast(pl.Float64).alias(deprivation.PI)
            )

        return lf
    return lf


def _stage_group_columns_lazy(lf: pl.LazyFrame, design: Design) -> tuple[str, ...]:
    if isinstance(design, CensusDesign):
        return ()
    if isinstance(design, SurveyDesign):
        stages = design.resolved_stages
        depth = max(1, len(stages))
        cols: list[str] = []
        for level in range(1, depth + 1):
            cols.append(deprivation.stratum_column(level))
            cols.append(deprivation.psu_column(level))
            cols.append(deprivation.fraction_column(level))
        if design.pps is not None and design.pps.inclusion_probability is not None:
            cols.append(deprivation.PI)
        return tuple(cols)
    return ()


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
    deg = report.degrees
    ctx = f"k={cutoff_val}"
    if over_name:
        ctx += f", {over_name}={subgroup_name}"

    if deg.lonely_strata > 0:
        policy = getattr(design, "lonely_psu", "fail")
        diag_rows.append(
            {
                "topic": "lonely_psu",
                "context": ctx,
                "decision": policy,
                "detail": (
                    f"{deg.lonely_strata} lonely strata (keys: {deg.lonely_strata_keys}) "
                    f"handled by policy '{policy}'"
                ),
            }
        )

    if deg.df < 1:
        diag_rows.append(
            {
                "topic": "degrees_of_freedom",
                "context": ctx,
                "decision": "unestimated",
                "detail": f"df={deg.df} < 1; standard errors are NaN",
            }
        )

    for ratio in ratios_tuple:
        if ratio.value is None:
            diag_rows.append(
                {
                    "topic": "undefined_ratio",
                    "context": ctx,
                    "decision": "nan_estimate",
                    "detail": (
                        f"estimand '{ratio.key}' has non-positive denominator "
                        f"({ratio.denominator})"
                    ),
                }
            )


def _estimate_from_matrix(
    matrix: DeprivationMatrix,
    *,
    cutoffs: tuple[float, ...],
    variables: tuple[str, ...],
    tvar: str | None,
    cot_year: str | None,
    domain: str | pl.Expr | None,
    ci_method: str,
    level: float,
    check_decomposability: bool,
    overlap: str,
    panel_id: str | None,
    batch_size: int | None = None,
    projected_columns: list[str] | None = None,
    input_kind: str = "polars",
) -> EstimationResult:
    spec = matrix.spec
    design = matrix.design
    frame = matrix.frame

    diag_rows: list[dict[str, str]] = []

    if projected_columns is not None:
        diag_rows.append(
            {
                "topic": "projection_pushdown",
                "context": "from_parquet",
                "decision": "selected_columns",
                "detail": ", ".join(sorted(projected_columns)),
            }
        )

    base = domain_module.POPULATION
    if domain is not None:
        base = domain_module.from_expression(domain)
        domain_module.validate(frame, base)
        diag_rows.append(
            {
                "topic": "domain",
                "context": str(domain),
                "decision": "subpopulation_filter",
                "detail": (
                    f"active rows: {frame.filter(base.weight() > 0).height}/{frame.height}"
                ),
            }
        )

    base_weight = base.weight()

    rows: list[dict[str, object]] = []
    decomposition: list[dict[str, object]] = []

    if design.variance_path == "taylor":
        survey_design: SurveyDesign = design  # type: ignore[assignment]
        group_cols = _stage_group_columns(frame, survey_design)

        for cutoff in cutoffs:
            estimands = estimands_module.build(spec, cutoff)
            keys = tuple(item.key for item in estimands)

            if base.is_population:
                national_sums = linearization.cluster_sums(
                    frame, estimands, weight=base_weight, group_columns=group_cols
                )
            else:
                w_dom = base_weight
                national_sums = linearization.cluster_sums(
                    frame, estimands, weight=w_dom, group_columns=group_cols
                )

            national_point, national_report = _taylor_report(
                national_sums, estimands, keys, survey_design
            )
            _check_report_diags(
                national_report,
                None,
                None,
                cutoff,
                national_point,
                design,
                ci_method,
                diag_rows,
            )
            national_rows = _context_rows(
                national_point, national_report, cutoff, None, None, ci_method, level
            )
            rows.extend(national_rows)

            national_population = national_report.population
            national_m0 = _pick(national_rows, "M0")

            for variable in variables:
                subgroups_list = domain_module.levels(frame, variable)
                share_total = 0.0
                weighted_m0 = 0.0

                for subgroup in subgroups_list:
                    sub_weight = base_weight * (
                        pl.col(variable).cast(pl.String) == subgroup
                    ).cast(pl.Float64)
                    sub_sums = linearization.cluster_sums(
                        frame,
                        estimands,
                        weight=sub_weight,
                        group_columns=group_cols,
                    )
                    sub_point, sub_report = _taylor_report(
                        sub_sums, estimands, keys, survey_design
                    )
                    _check_report_diags(
                        sub_report,
                        variable,
                        subgroup,
                        cutoff,
                        sub_point,
                        design,
                        ci_method,
                        diag_rows,
                    )
                    sub_rows = _context_rows(
                        sub_point, sub_report, cutoff, variable, subgroup, ci_method, level
                    )
                    rows.extend(sub_rows)

                    if national_population:
                        share = sub_report.population / national_population
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

    elif design.variance_path == "replication":
        rep_design: ReplicateDesign = design  # type: ignore[assignment]
        effective_batch_size = batch_size if batch_size is not None else 64
        if rep_design.replicate_weights is None:
            frame_work, repw_cols, scale, rscales = generate_replicate_weights(
                frame, rep_design
            )
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
            rscales = (
                rep_design.rscales
                if rep_design.rscales is not None
                else ((1.0,) * len(rep_design.replicate_weights))
            )
            if rep_design.method == "JKn" and rep_design.strata is not None:
                H = frame_work.select(pl.col(rep_design.strata).cast(pl.String)).n_unique()
            else:
                H = 1
            rep_design_active = rep_design

        rep_weight_exprs = replicate_weight_expressions(rep_design_active, frame_work)
        R = len(rep_weight_exprs)
        df_strata = (
            H
            if (
                rep_design.method == "JKn"
                and (rep_design.strata is not None or rep_design.replicate_weights is None)
            )
            else 1
        )
        degrees = DesignDegrees(
            psus=R,
            strata=df_strata,
            lonely_strata=0,
            override_df=rep_design.degf,
        )

        for cutoff in cutoffs:
            estimands = estimands_module.build(spec, cutoff)
            keys = tuple(item.key for item in estimands)

            national_point = linearization.totals(frame_work, estimands, weight=base_weight)
            national_reps = replicate_totals(
                frame_work,
                estimands,
                [w * (base_weight > 0).cast(pl.Float64) for w in rep_weight_exprs],
                batch_size=effective_batch_size,
            )
            national_vars = replicate_variance(
                national_point,
                national_reps,
                keys,
                scale=scale,
                rscales=rscales,
                mse=rep_design_active.mse,
            )
            pop = float(frame_work.select(base_weight.sum()).item() or 0.0)
            obs = int(frame_work.filter(base_weight > 0).height)
            national_report = VarianceReport(
                values=national_vars,
                degrees=degrees,
                population=pop,
                observations=obs,
            )
            _check_report_diags(
                national_report,
                None,
                None,
                cutoff,
                national_point,
                design,
                ci_method,
                diag_rows,
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
                    batch_size=effective_batch_size,
                )
                subgroups_list = domain_module.levels(frame_work, variable)
                share_total = 0.0
                weighted_m0 = 0.0

                for subgroup in subgroups_list:
                    sub_frame = frame_work.filter(pl.col(variable).cast(pl.String) == subgroup)
                    sub_point = linearization.totals(sub_frame, estimands, weight=base_weight)
                    sub_pop = float(sub_frame.select(base_weight.sum()).item() or 0.0)
                    sub_obs = int(sub_frame.filter(base_weight > 0).height)

                    sub_reps = subgroup_reps_dict.get(subgroup, [])
                    sub_vars = replicate_variance(
                        sub_point,
                        sub_reps,
                        keys,
                        scale=scale,
                        rscales=rscales,
                        mse=rep_design_active.mse,
                    )
                    sub_report = VarianceReport(
                        values=sub_vars,
                        degrees=degrees,
                        population=sub_pop,
                        observations=sub_obs,
                    )
                    _check_report_diags(
                        sub_report,
                        variable,
                        subgroup,
                        cutoff,
                        sub_point,
                        design,
                        ci_method,
                        diag_rows,
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
            national_rows = _context_rows(ratios, report, cutoff, None, None, ci_method, level)
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
            diag_rows.append(
                {
                    "topic": "ci_logit",
                    "context": "changes",
                    "decision": "fallback_to_t",
                    "detail": "logit CI method replaced by 't' for change estimates",
                }
            )
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
    diagnostics_frame = pl.DataFrame(diag_rows, schema=_DIAGNOSTICS_SCHEMA).unique(
        maintain_order=True
    )

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
        _input_kind=matrix.input_kind,
        _design=design,
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
    over: str | None,
    subgroup: str | None,
    group_cols: tuple[str, ...],
) -> pl.DataFrame:
    if over is not None and subgroup is not None:
        sub_cells = cells.filter(pl.col(over).cast(pl.String) == subgroup)
    else:
        sub_cells = cells
    joined = universe.join(sub_cells, on=list(group_cols), how="left")
    value_cols = [c for c in joined.columns if c not in group_cols and c != over]
    return joined.select(
        *group_cols,
        *[pl.col(c).fill_null(0.0).alias(c) for c in value_cols],
    )


def _filter_subgroup_sums(
    cells: pl.DataFrame,
    over: str,
    subgroup: str,
    group_cols: tuple[str, ...],
) -> pl.DataFrame:
    sub = cells.filter(pl.col(over).cast(pl.String) == subgroup)
    keep = [c for c in sub.columns if c != over]
    return sub.select(*keep)


def _validate_cutoffs(k: float | Sequence[float]) -> tuple[float, ...]:
    if isinstance(k, Real):
        k_list = [float(k)]
    elif isinstance(k, (list, tuple)):
        k_list = [float(val) for val in k]
        if not k_list:
            raise ValueError("at least one cutoff must be specified")
        if len(k_list) != len(set(k_list)):
            raise ValueError(f"duplicate cutoffs: {k_list}")
    else:
        raise TypeError("k must be a float or sequence of floats")
    for val in k_list:
        if not (0 <= val <= 1):
            raise ValueError("k values must be between 0 and 1, inclusive")
    return tuple(sorted(set(k_list)))


def _validate_over(over: str | Sequence[str] | None) -> tuple[str, ...]:
    if over is None:
        return ()
    if isinstance(over, str):
        return (over,)
    if isinstance(over, (list, tuple)):
        if len(over) != len(set(over)):
            raise ValueError(f"duplicate variables in over: {over}")
        return tuple(over)
    raise TypeError("over must be a column name or sequence of column names")


def _pick(rows: list[dict[str, object]], measure: str) -> float | None:
    for row in rows:
        if row["measure"] == measure:
            val = row["est"]
            return float(val) if val is not None else None
    return None


def _assert_decomposable(decomposition: pl.DataFrame) -> None:
    for row in decomposition.iter_rows(named=True):
        if abs(row["shares"] - 1.0) > 1e-4:
            raise ValueError(f"subgroup population shares sum to {row['shares']}, not 1")
        if row["error"] > DECOMPOSITION_TOLERANCE:
            raise ValueError(
                f"decomposability broken for over={row['over']!r}: M0={row['M0']}, "
                f"sum_l(phi_l * M0_l)={row['decomposed_M0']} (diff={row['error']})"
            )


def _compute_vcov(
    matrix: DeprivationMatrix | None,
    *,
    cutoffs: tuple[float, ...],
    over_vars: tuple[str, ...],
    k: float | None = None,
    over: str | None = None,
    subgroup: str | None = None,
    measures: Sequence[str] | None = None,
    convert_fn=None,
    design: Design | None = None,
) -> pl.DataFrame:
    resolved_design = (
        design if design is not None else (matrix.design if matrix is not None else None)
    )
    if (
        resolved_design is not None
        and getattr(resolved_design, "variance_path", None) == "census"
    ):
        measures_tuple = ("H", "A", "M0") if measures is None else tuple(measures)
        matrix_rows = [
            {"term": m1, **{m2: 0.0 for m2 in measures_tuple}} for m1 in measures_tuple
        ]
        res_df = pl.DataFrame(matrix_rows)
        return convert_fn(res_df) if convert_fn else res_df

    if matrix is None:
        raise ValueError(
            "vcov() requires an in-memory result; re-run estimate() without "
            "lazy=True/CensusDesign streaming"
        )

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
    design_to_use = matrix.design
    frame = matrix.frame
    estimands = estimands_module.build(spec, k)
    estimand_map = {item.key: item for item in estimands}

    for m in measures_tuple:
        if m not in estimand_map:
            raise ValueError(f"unknown measure key: {m!r}")

    if design_to_use.variance_path == "taylor":
        survey_design_use: SurveyDesign = design_to_use  # type: ignore[assignment]
        group_cols = _stage_group_columns(frame, survey_design_use)
        universe = frame.select(list(group_cols)).unique(maintain_order=True)

        if over is None and subgroup is None:
            sums = linearization.cluster_sums(frame, estimands, group_columns=group_cols)
        else:
            cells = linearization.cluster_sums(
                frame, estimands, group_columns=group_cols + (over,)
            )
            sums = _align(cells, universe, over, subgroup, group_cols)

        ratios = linearization.totals_from_clusters(sums, estimands)
        inf = linearization.cluster_influence(sums, ratios)
        deg = design_degrees(inf)
        vcov_dict, _ = design_vcov(inf, measures_tuple, deg, design_to_use)  # type: ignore[arg-type]

    elif design_to_use.variance_path == "replication":
        rep_design: ReplicateDesign = design_to_use  # type: ignore[assignment]
        if rep_design.replicate_weights is None:
            frame_work, repw_cols, scale, rscales = generate_replicate_weights(
                frame, rep_design
            )
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
            rscales = (
                rep_design.rscales
                if rep_design.rscales is not None
                else ((1.0,) * len(rep_design.replicate_weights))
            )
            rep_design_active = rep_design

        rep_weight_exprs = replicate_weight_expressions(rep_design_active, frame_work)

        if over is None and subgroup is None:
            point = linearization.totals(frame_work, estimands)
            replicates_list = replicate_totals(
                frame_work, estimands, rep_weight_exprs, batch_size=64
            )  # type: ignore[assignment]
        else:
            sub_frame = frame_work.filter(pl.col(over).cast(pl.String) == subgroup)
            point = linearization.totals(sub_frame, estimands)
            sub_dict = replicate_totals(
                frame_work, estimands, rep_weight_exprs, group_column=over, batch_size=64
            )
            replicates_list = sub_dict.get(subgroup, [])  # type: ignore[assignment]

        vcov_dict = replicate_vcov(
            point,
            replicates_list,
            measures_tuple,
            scale=scale,
            rscales=rscales,
            mse=rep_design_active.mse,
        )

    else:
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
    matrix: DeprivationMatrix | None,
    *,
    cutoffs: tuple[float, ...],
    a: object,
    b: object = None,
    measure: str = "M0",
    k: float | None = None,
    dist: str = "F",
) -> HypothesisTest:
    if matrix is not None and getattr(matrix.design, "variance_path", None) == "census":
        raise ValueError("a census has no sampling variance; a Wald test is not defined")
    if matrix is None:
        raise ValueError(
            "test() requires an in-memory result; re-run estimate() without "
            "lazy=True/CensusDesign streaming"
        )

    if k is None:
        if len(cutoffs) == 1:
            k = cutoffs[0]
        else:
            raise ValueError(f"multiple cutoffs estimated {cutoffs}; specify k=...")
    if k not in cutoffs:
        raise ValueError(f"cutoff {k} was not estimated; available cutoffs are {cutoffs}")

    spec = matrix.spec
    design = matrix.design
    frame = matrix.frame

    if getattr(design, "variance_path", None) == "census":
        raise ValueError("a census has no sampling variance; a Wald test is not defined")

    if dist not in ("F", "chisq"):
        raise ValueError(f"dist must be 'F' or 'chisq'; got {dist!r}")

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
            raise TypeError(
                f"domain argument must be a string expression or (over, subgroup) tuple; "
                f"got {arg!r}"
            )

    dom_a, label_a = _parse_arg(a)
    if b is not None:
        dom_b, label_b = _parse_arg(b)
        terms = (label_a, label_b)
    else:
        dom_b = None
        terms = (label_a,)

    estimands = estimands_module.build(spec, k)
    estimand_map = {item.key: item for item in estimands}
    if measure not in estimand_map:
        raise ValueError(f"unknown measure: {measure!r}")

    target_item = estimand_map[measure]

    if design.variance_path == "taylor":
        group_cols = _stage_group_columns(frame, design)  # type: ignore[arg-type]

        w_a = dom_a.weight()
        sums_a = frame.group_by(list(group_cols)).agg(
            (w_a * target_item.y)
            .sum()
            .alias(linearization._NUMERATOR_PREFIX + target_item.key),
            (w_a * target_item.x)
            .sum()
            .alias(linearization._DENOMINATOR_PREFIX + target_item.key),
            pl.col(deprivation.WEIGHT).sum().alias("__afmpi_cluster_weight"),
            pl.len().alias("__afmpi_cluster_rows"),
        )
        ratios_a = linearization.totals_from_clusters(sums_a, (target_item,))
        inf_a = linearization.cluster_influence(sums_a, ratios_a).rename(
            {target_item.key: "inf_a"}
        )
        r_a = ratios_a[0].value

        if dom_b is not None:
            w_b = dom_b.weight()
            sums_b = frame.group_by(list(group_cols)).agg(
                (w_b * target_item.y)
                .sum()
                .alias(linearization._NUMERATOR_PREFIX + target_item.key),
                (w_b * target_item.x)
                .sum()
                .alias(linearization._DENOMINATOR_PREFIX + target_item.key),
                pl.col(deprivation.WEIGHT).sum().alias("__afmpi_cluster_weight"),
                pl.len().alias("__afmpi_cluster_rows"),
            )
            ratios_b = linearization.totals_from_clusters(sums_b, (target_item,))
            inf_b = linearization.cluster_influence(sums_b, ratios_b).rename(
                {target_item.key: "inf_b"}
            )
            r_b = ratios_b[0].value

            join_cols = list(group_cols)
            cluster_inf = inf_a.join(
                inf_b.select(*group_cols, "inf_b"), on=join_cols, how="left"
            )
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
            frame_work, repw_cols, scale, rscales = generate_replicate_weights(
                frame, rep_design
            )
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
            rscales = (
                rep_design.rscales
                if rep_design.rscales is not None
                else ((1.0,) * len(rep_design.replicate_weights))
            )
            if rep_design.method == "JKn" and rep_design.strata is not None:
                H = frame_work.select(pl.col(rep_design.strata).cast(pl.String)).n_unique()
            else:
                H = 1
            rep_design_active = rep_design

        rep_weight_exprs = replicate_weight_expressions(rep_design_active, frame_work)
        R = len(rep_weight_exprs)
        df_strata = (
            H
            if (
                rep_design.method == "JKn"
                and (rep_design.strata is not None or rep_design.replicate_weights is None)
            )
            else 1
        )
        full_degrees = DesignDegrees(
            psus=R, strata=df_strata, lonely_strata=0, override_df=rep_design.degf
        )

        w_a = dom_a.weight()
        pt_a = linearization.totals(frame_work, (target_item,), weight=w_a)[0]
        theta_a = pt_a.value
        reps_a = replicate_totals(
            frame_work,
            (target_item,),
            [w * (w_a > 0).cast(pl.Float64) for w in rep_weight_exprs],
            batch_size=64,
        )

        if dom_b is not None:
            w_b = dom_b.weight()
            pt_b = linearization.totals(frame_work, (target_item,), weight=w_b)[0]
            theta_b = pt_b.value
            reps_b = replicate_totals(
                frame_work,
                (target_item,),
                [w * (w_b > 0).cast(pl.Float64) for w in rep_weight_exprs],
                batch_size=64,
            )
        else:
            theta_b = None
            reps_b = None

        theta_c_a = (
            theta_a
            if rep_design_active.mse
            else sum(r[0].value for r in reps_a if r[0].value is not None) / R
        )
        v_aa = scale * sum(
            rscales[r] * ((reps_a[r][0].value - theta_c_a) ** 2) for r in range(R)
        )

        if dom_b is not None:
            theta_c_b = (
                theta_b
                if rep_design_active.mse
                else sum(r[0].value for r in reps_b if r[0].value is not None) / R
            )
            v_bb = scale * sum(
                rscales[r] * ((reps_b[r][0].value - theta_c_b) ** 2) for r in range(R)
            )
            v_ab = scale * sum(
                rscales[r] * (reps_a[r][0].value - theta_c_a) * (reps_b[r][0].value - theta_c_b)
                for r in range(R)
            )
        else:
            v_bb = 0.0
            v_ab = 0.0

    else:
        raise ValueError("a census has no sampling variance; a Wald test is not defined")

    df2 = full_degrees.df
    q = 1

    if dom_b is not None:
        diff = theta_a - theta_b
        var_contrast = v_aa + v_bb - 2.0 * v_ab
    else:
        diff = theta_a
        var_contrast = v_aa

    if (dom_b is not None and label_a == label_b) or (diff == 0.0 and var_contrast == 0.0):
        estimate_val = 0.0 if dom_b is not None else theta_a
        se = 0.0
        statistic = 0.0
        p_value = 1.0
    else:
        estimate_val = float(diff)
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
                W = (estimate_val**2) / var_contrast
                if dist == "F":
                    statistic = float(W / q)
                    p_value = float(stats.f.sf(statistic, q, df2))
                else:
                    statistic = float(W)
                    p_value = float(stats.chi2.sf(statistic, q))

    return HypothesisTest(
        terms=terms,
        estimate=estimate_val,
        se=se,
        statistic=statistic,
        df1=q,
        df2=df2,
        p_value=p_value,
        method="Wald",
        dist=dist,
    )


__all__ = [
    "DECOMPOSITION_TOLERANCE",
    "LazyEstimation",
    "VarianceReport",
    "_compute_test",
    "_compute_vcov",
    "estimate",
]
