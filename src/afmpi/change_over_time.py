"""Evolution over time: change between independent waves (PLAN.md §14.6a).

Implementation choice for design-based variance of change:
The influence value of the difference is the difference of influence values:
    u_i^Δ = u_i^(t1) - u_i^(t0)
and the variance of Δ is computed by applying the standard design variance
estimator to u^Δ.

Two fundamental reasons for this implementation choice:
1. Exactness: The covariance term Cov(θ1, θ0) arises automatically with the
   correct sign and magnitude because any clusters shared across waves
   naturally accumulate their influence contributions.
2. Phase 6b readiness: For independent waves, supports of u^(t1) and u^(t0)
   are disjoint, so Cov(θ1, θ0) = 0 automatically. When waves overlap (panel
   data), the exact same formula yields the correct covariance without requiring
   any additional variance formulas.

For replication designs (ReplicateDesign):
    Δ^(r) = θ̂1^(r) - θ̂0^(r)
and the replicate variance formula of §14.5a is applied to Δ^(r).

Confidence intervals for change estimates:
    `bounded=False` is enforced (changes can be negative).
    When `ci_method="logit"` is specified, it is silently replaced by `"t"`
    for change rows because logit transformation is undefined for differences
    that can span negative values or exceed 1.
"""

from __future__ import annotations

from collections.abc import Sequence
from math import isfinite, nan
from typing import TYPE_CHECKING
import warnings

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
from .survey_design import SurveyDesign
from .variance import (
    DesignDegrees,
    confidence_interval,
    design_degrees,
    design_variance,
    standard_error,
)

if TYPE_CHECKING:
    from .estimation import _stage_group_columns

_CHANGES_SCHEMA = {
    "measure": pl.String,
    "indicator": pl.String,
    "dimension": pl.String,
    "weight": pl.Float64,
    "k": pl.Float64,
    "over": pl.String,
    "subgroup": pl.String,
    "t0": pl.String,
    "t1": pl.String,
    "years": pl.Float64,
    "type": pl.String,
    "est": pl.Float64,
    "se": pl.Float64,
    "lci": pl.Float64,
    "uci": pl.Float64,
    "df": pl.Int64,
}


def validate_time_variables(
    frame: pl.DataFrame,
    tvar: str | None,
    cot_year: str | None,
) -> None:
    """Validate tvar and cot_year arguments according to PLAN.md §14.6a."""

    if tvar is None:
        if cot_year is not None:
            raise ValueError("cot_year specified without tvar")
        return

    if tvar not in frame.columns:
        raise ValueError(f"tvar column {tvar!r} is absent from df")

    if frame.select(pl.col(tvar).is_null().any()).item():
        raise ValueError(f"tvar column {tvar!r} contains missing values")

    waves = (
        frame.select(pl.col(tvar).unique().cast(pl.String).alias("wave"))
        .to_series()
        .to_list()
    )
    if len(waves) < 2:
        raise ValueError(f"tvar must contain at least 2 distinct values; got {len(waves)}")

    if cot_year is not None:
        if cot_year not in frame.columns:
            raise ValueError(f"cot_year column {cot_year!r} is absent from df")

        non_const = frame.group_by(tvar).agg(
            pl.col(cot_year).n_unique().alias("n_years"),
            pl.col(cot_year).is_null().any().alias("has_null"),
        ).filter((pl.col("n_years") > 1) | pl.col("has_null"))

        if non_const.height > 0:
            raise ValueError(
                f"cot_year {cot_year!r} is not constant within each wave of {tvar!r}"
            )


def get_wave_pairs(waves: Sequence[object]) -> list[tuple[str, str]]:
    """Return consecutive wave pairs plus (first, last) if >2 waves."""

    sorted_waves = [str(w) for w in sorted(waves)]
    pairs: list[tuple[str, str]] = []
    for i in range(len(sorted_waves) - 1):
        pairs.append((sorted_waves[i], sorted_waves[i + 1]))

    if len(sorted_waves) > 2:
        first_last = (sorted_waves[0], sorted_waves[-1])
        if first_last not in pairs:
            pairs.append(first_last)

    return pairs


def _align_simple(
    cells: pl.DataFrame,
    universe: pl.DataFrame,
    group_columns: tuple[str, ...],
) -> pl.DataFrame:
    """Align cluster sums to design universe, filling 0 for missing clusters."""

    value_columns = [col for col in cells.columns if col not in group_columns]
    aligned = universe.join(cells, on=list(group_columns), how="left")
    return aligned.with_columns(
        [pl.col(col).fill_null(0.0).alias(col) for col in value_columns]
    )


def compute_changes(
    matrix: DeprivationMatrix,
    *,
    cutoffs: tuple[float, ...],
    variables: tuple[str, ...],
    tvar: str,
    cot_year: str | None,
    ci_method: str,
    level: float,
    overlap: str = "auto",
    panel_id: str | None = None,
) -> tuple[pl.DataFrame, list[dict[str, str]]]:
    """Compute absolute, relative and annualised changes between waves."""

    if overlap not in {"auto", "independent", "panel"}:
        raise ValueError(f"overlap must be one of {{'auto', 'independent', 'panel'}}; got {overlap!r}")

    frame = matrix.frame
    spec = matrix.spec
    design = matrix.design

    base = domain_module.POPULATION
    base_weight = base.weight()

    ci_method_change = "t" if ci_method == "logit" else ci_method

    # Sort wave values
    raw_waves = (
        frame.select(pl.col(tvar).unique().sort().cast(pl.String).alias("wave"))
        .to_series()
        .to_list()
    )
    pairs = get_wave_pairs(raw_waves)

    # Overlap detection logic
    psu_col = deprivation.psu_column(1) if deprivation.psu_column(1) in frame.columns else (deprivation.PSU if deprivation.PSU in frame.columns else None)
    has_psu_overlap = False
    n_shared_psus = 0
    if psu_col:
        psu_waves = (
            frame.group_by(psu_col)
            .agg(pl.col(tvar).n_unique().alias("_nw"))
            .filter(pl.col("_nw") > 1)
        )
        n_shared_psus = psu_waves.height
        has_psu_overlap = n_shared_psus > 0

    has_panel_overlap = False
    n_shared_units = 0
    total_units = 0
    if panel_id is not None and panel_id in frame.columns:
        total_units = frame.select(pl.col(panel_id).n_unique()).item() if frame.height else 0
        panel_waves = (
            frame.group_by(panel_id)
            .agg(pl.col(tvar).n_unique().alias("_nw"))
            .filter(pl.col("_nw") > 1)
        )
        n_shared_units = panel_waves.height
        has_panel_overlap = n_shared_units > 0

    overlap_detected = has_psu_overlap or has_panel_overlap

    if overlap == "panel" and not overlap_detected:
        raise ValueError("overlap='panel' was requested but no unit is shared between waves")

    if overlap == "auto":
        active_regime = "panel" if overlap_detected else "independent"
    elif overlap == "independent":
        active_regime = "independent"
    elif overlap == "panel":
        active_regime = "panel"

    if panel_id is not None and has_panel_overlap and not has_psu_overlap:
        warnings.warn(
            "panel_id was provided and contains units shared across waves, but no PSU key is shared between waves. Cluster identifiers are not comparable between waves and covariance will be underestimated.",
            category=UserWarning,
            stacklevel=2,
        )

    if design.variance_path == "replication":
        rep_design_chk: ReplicateDesign = design  # type: ignore[assignment]
        if rep_design_chk.replicate_weights is not None:
            repw_cols_check = rep_design_chk.replicate_weights
            for w_c in raw_waves:
                w_fr = frame.filter(pl.col(tvar).cast(pl.String) == w_c)
                for rw_c in repw_cols_check:
                    if (
                        rw_c not in w_fr.columns
                        or w_fr.select(pl.col(rw_c).null_count()).item() == w_fr.height
                        or w_fr.select(pl.col(rw_c).is_null().any()).item()
                        or w_fr.select((pl.col(rw_c) == 0.0).all()).item()
                    ):
                        raise ValueError("Replicate design weights or configuration diverge between waves")

    time_diag_rows: list[dict[str, str]] = []
    if active_regime == "panel":
        details_parts = []
        if has_psu_overlap:
            details_parts.append(f"{n_shared_psus} shared PSUs")
        if has_panel_overlap:
            rate = (n_shared_units / total_units * 100.0) if total_units > 0 else 0.0
            details_parts.append(f"{n_shared_units} shared units on panel_id (matching rate: {rate:.1f}%)")
        detail_str = f"overlap detected ({', '.join(details_parts)}); panel regime retained"
        time_diag_rows.append({
            "topic": "time",
            "context": f"tvar='{tvar}'",
            "decision": "panel",
            "detail": detail_str,
        })
    elif overlap == "independent" and overlap_detected:
        details_parts = []
        if has_psu_overlap:
            details_parts.append(f"{n_shared_psus} shared PSUs")
        if has_panel_overlap:
            details_parts.append(f"{n_shared_units} shared units on panel_id")
        detail_str = f"overlap detected ({', '.join(details_parts)}) but deliberately ignored (overlap='independent'); forced independent regime"
        time_diag_rows.append({
            "topic": "time",
            "context": f"tvar='{tvar}'",
            "decision": "independent",
            "detail": detail_str,
        })
    else:
        time_diag_rows.append({
            "topic": "time",
            "context": f"tvar='{tvar}'",
            "decision": "independent",
            "detail": "no unit shared between waves; independent regime retained",
        })

    if overlap == "independent" and overlap_detected:
        prefix_cols = list(dict.fromkeys(c for c in (psu_col, deprivation.PSU) if c and c in frame.columns))
        prefix_exprs = [
            (pl.col(tvar).cast(pl.String) + pl.lit("__") + pl.col(c).cast(pl.String)).alias(c)
            for c in prefix_cols
        ]
        frame_work = frame.with_columns(prefix_exprs)
    else:
        frame_work = frame

    if cot_year is not None:
        year_rows = (
            frame.select(
                pl.col(tvar).cast(pl.String).alias("wave"),
                pl.col(cot_year).cast(pl.Float64).alias("year"),
            )
            .unique()
            .to_dicts()
        )
        wave_years = {r["wave"]: float(r["year"]) for r in year_rows}

        def get_d(t0: str, t1: str) -> float:
            return wave_years[t1] - wave_years[t0]

    else:

        def get_d(t0: str, t1: str) -> float:
            return 1.0

    rows: list[dict[str, object]] = []

    if design.variance_path == "taylor":
        from .estimation import _stage_group_columns

        group_cols = _stage_group_columns(frame_work, design)  # type: ignore[arg-type]
        dummy_estimands = estimands_module.build(spec, cutoffs[0])
        full_sums = linearization.cluster_sums(
            frame_work, dummy_estimands, base_weight, group_columns=group_cols
        )
        full_degrees = design_degrees(full_sums)
        universe = full_sums.select(list(group_cols)).unique(maintain_order=True)

        subgroups_dict = {
            variable: domain_module.levels(frame_work, variable) for variable in variables
        }

        for cutoff in cutoffs:
            estimands = estimands_module.build(spec, cutoff)
            keys = tuple(item.key for item in estimands)

            # 1. National level cluster sums & influence per wave
            national_ratios: dict[str, tuple[linearization.RatioTotals, ...]] = {}
            national_u: dict[str, pl.DataFrame] = {}

            for w in raw_waves:
                w_frame = frame_work.filter(pl.col(tvar).cast(pl.String) == w)
                cells_w = linearization.cluster_sums(
                    w_frame, estimands, base_weight, group_columns=group_cols
                )
                sums_w = _align_simple(cells_w, universe, group_cols)
                ratios_w = linearization.totals_from_clusters(sums_w, estimands)
                u_w = linearization.cluster_influence(sums_w, ratios_w)
                national_ratios[w] = ratios_w
                national_u[w] = u_w

            for t0, t1 in pairs:
                d = get_d(t0, t1)
                ratios0 = national_ratios[t0]
                ratios1 = national_ratios[t1]
                u0 = national_u[t0]
                u1 = national_u[t1]

                # Form u_Delta
                u_delta_exprs: list[pl.Expr] = []
                for key in keys:
                    r0_pt = next(r for r in ratios0 if r.key == key)
                    r1_pt = next(r for r in ratios1 if r.key == key)
                    if r0_pt.value is None or r1_pt.value is None:
                        u_delta_exprs.append(pl.lit(None, dtype=pl.Float64).alias(key))
                    else:
                        u_delta_exprs.append((pl.col(key) - u0[key]).alias(key))
                u_delta_df = u1.select(
                    *[col for col in u1.columns if col not in keys],
                    *u_delta_exprs,
                )

                vars_delta, _ = design_variance(
                    u_delta_df, keys, full_degrees, design  # type: ignore[arg-type]
                )
                vars0, _ = design_variance(u0, keys, full_degrees, design)  # type: ignore[arg-type]
                vars1, _ = design_variance(u1, keys, full_degrees, design)  # type: ignore[arg-type]

                for ratio0, ratio1 in zip(ratios0, ratios1):
                    key = ratio0.key
                    _append_change_rows(
                        rows,
                        estimand=ratio0.estimand,
                        cutoff=cutoff,
                        over=None,
                        subgroup=None,
                        t0=t0,
                        t1=t1,
                        d=d,
                        theta0=ratio0.value,
                        theta1=ratio1.value,
                        v0=vars0[key],
                        v1=vars1[key],
                        var_delta=vars_delta[key],
                        df=full_degrees.df,
                        ci_method=ci_method_change,
                        level=level,
                    )

            # 2. Subgroup levels
            for variable in variables:
                subgroups = subgroups_dict[variable]

                sub_ratios: dict[
                    tuple[str, str], tuple[linearization.RatioTotals, ...]
                ] = {}
                sub_u: dict[tuple[str, str], pl.DataFrame] = {}

                for w in raw_waves:
                    for subgroup in subgroups:
                        w_sub_frame = frame_work.filter(
                            (pl.col(tvar).cast(pl.String) == w)
                            & (pl.col(variable).cast(pl.String) == subgroup)
                        )
                        cells_w_sub = linearization.cluster_sums(
                            w_sub_frame, estimands, base_weight, group_columns=group_cols
                        )
                        sums_w_sub = _align_simple(cells_w_sub, universe, group_cols)
                        ratios_w_sub = linearization.totals_from_clusters(
                            sums_w_sub, estimands
                        )
                        u_w_sub = linearization.cluster_influence(
                            sums_w_sub, ratios_w_sub
                        )
                        sub_ratios[(w, subgroup)] = ratios_w_sub
                        sub_u[(w, subgroup)] = u_w_sub

                for t0, t1 in pairs:
                    d = get_d(t0, t1)
                    for subgroup in subgroups:
                        ratios0 = sub_ratios[(t0, subgroup)]
                        ratios1 = sub_ratios[(t1, subgroup)]
                        u0 = sub_u[(t0, subgroup)]
                        u1 = sub_u[(t1, subgroup)]

                        u_delta_exprs = []
                        for key in keys:
                            r0_pt = next(r for r in ratios0 if r.key == key)
                            r1_pt = next(r for r in ratios1 if r.key == key)
                            if r0_pt.value is None or r1_pt.value is None:
                                u_delta_exprs.append(
                                    pl.lit(None, dtype=pl.Float64).alias(key)
                                )
                            else:
                                u_delta_exprs.append((pl.col(key) - u0[key]).alias(key))
                        u_delta_df = u1.select(
                            *[col for col in u1.columns if col not in keys],
                            *u_delta_exprs,
                        )

                        vars_delta, _ = design_variance(
                            u_delta_df, keys, full_degrees, design  # type: ignore[arg-type]
                        )
                        vars0, _ = design_variance(u0, keys, full_degrees, design)  # type: ignore[arg-type]
                        vars1, _ = design_variance(u1, keys, full_degrees, design)  # type: ignore[arg-type]

                        for ratio0, ratio1 in zip(ratios0, ratios1):
                            key = ratio0.key
                            _append_change_rows(
                                rows,
                                estimand=ratio0.estimand,
                                cutoff=cutoff,
                                over=variable,
                                subgroup=subgroup,
                                t0=t0,
                                t1=t1,
                                d=d,
                                theta0=ratio0.value,
                                theta1=ratio1.value,
                                v0=vars0[key],
                                v1=vars1[key],
                                var_delta=vars_delta[key],
                                df=full_degrees.df,
                                ci_method=ci_method_change,
                                level=level,
                            )

    elif design.variance_path == "replication":
        rep_design: ReplicateDesign = design  # type: ignore[assignment]

        if rep_design.replicate_weights is None:
            frame_work_rep, repw_cols, scale, rscales = generate_replicate_weights(
                frame_work, rep_design
            )
            if rep_design.method == "JKn" and rep_design.strata is not None:
                H = frame_work_rep.select(
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
            frame_work = frame_work_rep
        else:
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
        full_degrees = DesignDegrees(
            psus=R, strata=df_strata, lonely_strata=0, override_df=rep_design.degf
        )
        rep_weight_exprs = replicate_weight_expressions(rep_design_active, frame_work)

        for cutoff in cutoffs:
            estimands = estimands_module.build(spec, cutoff)
            keys = tuple(item.key for item in estimands)

            # 1. National level
            nat_pt: dict[str, tuple[linearization.RatioTotals, ...]] = {}
            nat_reps: dict[str, list[tuple[linearization.RatioTotals, ...]]] = {}

            for w in raw_waves:
                w_frame = frame_work.filter(pl.col(tvar).cast(pl.String) == w)
                pt_w = linearization.totals(w_frame, estimands, weight=base_weight)
                reps_w = replicate_totals(
                    w_frame, estimands, rep_weight_exprs, batch_size=64
                )
                nat_pt[w] = pt_w
                nat_reps[w] = reps_w  # type: ignore[assignment]

            for t0, t1 in pairs:
                d = get_d(t0, t1)
                pt0, pt1 = nat_pt[t0], nat_pt[t1]
                reps0, reps1 = nat_reps[t0], nat_reps[t1]

                v0 = replicate_variance(
                    pt0,
                    reps0,
                    keys,
                    scale=rep_design_active.scale,
                    rscales=rep_design_active.rscales,
                    mse=rep_design_active.mse,
                )
                v1 = replicate_variance(
                    pt1,
                    reps1,
                    keys,
                    scale=rep_design_active.scale,
                    rscales=rep_design_active.rscales,
                    mse=rep_design_active.mse,
                )

                vars_delta: dict[str, float] = {}
                for key in keys:
                    r0_pt = next(r for r in pt0 if r.key == key)
                    r1_pt = next(r for r in pt1 if r.key == key)
                    if r0_pt.value is None or r1_pt.value is None:
                        vars_delta[key] = nan
                    else:
                        theta_hat_delta = r1_pt.value - r0_pt.value
                        delta_reps: list[float] = []
                        has_nan = False
                        for r in range(R):
                            v0_r = next(item for item in reps0[r] if item.key == key).value
                            v1_r = next(item for item in reps1[r] if item.key == key).value
                            if (
                                v0_r is None
                                or v1_r is None
                                or not isfinite(v0_r)
                                or not isfinite(v1_r)
                            ):
                                has_nan = True
                                break
                            delta_reps.append(v1_r - v0_r)

                        if overlap == "independent" and overlap_detected:
                            vars_delta[key] = v1[key] + v0[key]
                        elif has_nan:
                            vars_delta[key] = nan
                        else:
                            theta_c = (
                                theta_hat_delta
                                if rep_design_active.mse
                                else sum(delta_reps) / R
                            )
                            vars_delta[key] = float(
                                rep_design_active.scale
                                * sum(
                                    rep_design_active.rscales[r]
                                    * ((delta_reps[r] - theta_c) ** 2)
                                    for r in range(R)
                                )
                            )

                for ratio0, ratio1 in zip(pt0, pt1):
                    key = ratio0.key
                    _append_change_rows(
                        rows,
                        estimand=ratio0.estimand,
                        cutoff=cutoff,
                        over=None,
                        subgroup=None,
                        t0=t0,
                        t1=t1,
                        d=d,
                        theta0=ratio0.value,
                        theta1=ratio1.value,
                        v0=v0[key],
                        v1=v1[key],
                        var_delta=vars_delta[key],
                        df=full_degrees.df,
                        ci_method=ci_method_change,
                        level=level,
                    )

            # 2. Subgroup levels
            subgroups_dict = {
                variable: domain_module.levels(frame_work, variable)
                for variable in variables
            }

            for variable in variables:
                subgroups = subgroups_dict[variable]
                sub_pt: dict[
                    tuple[str, str], tuple[linearization.RatioTotals, ...]
                ] = {}
                sub_reps: dict[
                    tuple[str, str], list[tuple[linearization.RatioTotals, ...]]
                ] = {}

                for w in raw_waves:
                    for subgroup in subgroups:
                        w_sub_frame = frame_work.filter(
                            (pl.col(tvar).cast(pl.String) == w)
                            & (pl.col(variable).cast(pl.String) == subgroup)
                        )
                        pt_w_sub = linearization.totals(
                            w_sub_frame, estimands, weight=base_weight
                        )
                        reps_w_sub = replicate_totals(
                            w_sub_frame, estimands, rep_weight_exprs, batch_size=64
                        )
                        sub_pt[(w, subgroup)] = pt_w_sub
                        sub_reps[(w, subgroup)] = reps_w_sub  # type: ignore[assignment]

                for t0, t1 in pairs:
                    d = get_d(t0, t1)
                    for subgroup in subgroups:
                        pt0, pt1 = sub_pt[(t0, subgroup)], sub_pt[(t1, subgroup)]
                        reps0, reps1 = sub_reps[(t0, subgroup)], sub_reps[(t1, subgroup)]

                        v0 = replicate_variance(
                            pt0,
                            reps0,
                            keys,
                            scale=rep_design_active.scale,
                            rscales=rep_design_active.rscales,
                            mse=rep_design_active.mse,
                        )
                        v1 = replicate_variance(
                            pt1,
                            reps1,
                            keys,
                            scale=rep_design_active.scale,
                            rscales=rep_design_active.rscales,
                            mse=rep_design_active.mse,
                        )

                        vars_delta = {}
                        for key in keys:
                            r0_pt = next(r for r in pt0 if r.key == key)
                            r1_pt = next(r for r in pt1 if r.key == key)
                            if r0_pt.value is None or r1_pt.value is None:
                                vars_delta[key] = nan
                            else:
                                theta_hat_delta = r1_pt.value - r0_pt.value
                                delta_reps = []
                                has_nan = False
                                for r in range(R):
                                    v0_r = next(
                                        item for item in reps0[r] if item.key == key
                                    ).value
                                    v1_r = next(
                                        item for item in reps1[r] if item.key == key
                                    ).value
                                    if (
                                        v0_r is None
                                        or v1_r is None
                                        or not isfinite(v0_r)
                                        or not isfinite(v1_r)
                                    ):
                                        has_nan = True
                                        break
                                    delta_reps.append(v1_r - v0_r)

                                if overlap == "independent" and overlap_detected:
                                    vars_delta[key] = v1[key] + v0[key]
                                elif has_nan:
                                    vars_delta[key] = nan
                                else:
                                    theta_c = (
                                        theta_hat_delta
                                        if rep_design_active.mse
                                        else sum(delta_reps) / R
                                    )
                                    vars_delta[key] = float(
                                        rep_design_active.scale
                                        * sum(
                                            rep_design_active.rscales[r]
                                            * ((delta_reps[r] - theta_c) ** 2)
                                            for r in range(R)
                                        )
                                    )

                        for ratio0, ratio1 in zip(pt0, pt1):
                            key = ratio0.key
                            _append_change_rows(
                                rows,
                                estimand=ratio0.estimand,
                                cutoff=cutoff,
                                over=variable,
                                subgroup=subgroup,
                                t0=t0,
                                t1=t1,
                                d=d,
                                theta0=ratio0.value,
                                theta1=ratio1.value,
                                v0=v0[key],
                                v1=v1[key],
                                var_delta=vars_delta[key],
                                df=full_degrees.df,
                                ci_method=ci_method_change,
                                level=level,
                            )

    else:
        raise ValueError(f"unknown variance path: {design.variance_path!r}")

    return pl.DataFrame(rows, schema=_CHANGES_SCHEMA), time_diag_rows


def _append_change_rows(
    rows: list[dict[str, object]],
    *,
    estimand: estimands_module.RatioEstimand,
    cutoff: float,
    over: str | None,
    subgroup: str | None,
    t0: str,
    t1: str,
    d: float,
    theta0: float | None,
    theta1: float | None,
    v0: float,
    v1: float,
    var_delta: float,
    df: int,
    ci_method: str,
    level: float,
) -> None:
    """Helper to compute absolute, relative, annualised abs/rel changes and CIs."""

    base_row = {
        "measure": estimand.measure,
        "indicator": estimand.indicator,
        "dimension": estimand.dimension,
        "weight": estimand.weight,
        "k": cutoff,
        "over": over,
        "subgroup": subgroup,
        "t0": t0,
        "t1": t1,
        "years": d,
        "df": df,
    }

    # 1. abs: theta1 - theta0
    if theta0 is not None and theta1 is not None:
        est_abs = theta1 - theta0
        se_abs = standard_error(var_delta)
        lci_abs, uci_abs = confidence_interval(
            est_abs, se_abs, df, method=ci_method, level=level, bounded=False
        )
    else:
        est_abs = None
        se_abs = nan
        lci_abs, uci_abs = nan, nan

    rows.append(
        {
            **base_row,
            "type": "abs",
            "est": est_abs,
            "se": se_abs,
            "lci": lci_abs,
            "uci": uci_abs,
        }
    )

    # Covariance C = (V1 + V0 - Var(Delta)) / 2
    if isfinite(v0) and isfinite(v1) and isfinite(var_delta):
        cov = (v1 + v0 - var_delta) / 2.0
    else:
        cov = nan

    # 2. rel: (theta1 - theta0) / theta0
    if (
        theta0 is not None
        and theta1 is not None
        and isfinite(theta0)
        and isfinite(theta1)
        and theta0 != 0
    ):
        est_rel = (theta1 - theta0) / theta0
        if isfinite(cov):
            var_rel = (
                v1 / (theta0**2)
                + (theta1**2) * v0 / (theta0**4)
                - 2.0 * theta1 * cov / (theta0**3)
            )
            se_rel = standard_error(var_rel)
            lci_rel, uci_rel = confidence_interval(
                est_rel, se_rel, df, method=ci_method, level=level, bounded=False
            )
        else:
            se_rel = nan
            lci_rel, uci_rel = nan, nan
    else:
        est_rel = None
        se_rel = nan
        lci_rel, uci_rel = nan, nan

    rows.append(
        {
            **base_row,
            "type": "rel",
            "est": est_rel,
            "se": se_rel,
            "lci": lci_rel,
            "uci": uci_rel,
        }
    )

    # 3. ann_abs: (theta1 - theta0) / d
    if theta0 is not None and theta1 is not None:
        est_ann_abs = (theta1 - theta0) / d
        var_ann_abs = var_delta / (d**2)
        se_ann_abs = standard_error(var_ann_abs)
        lci_ann_abs, uci_ann_abs = confidence_interval(
            est_ann_abs, se_ann_abs, df, method=ci_method, level=level, bounded=False
        )
    else:
        est_ann_abs = None
        se_ann_abs = nan
        lci_ann_abs, uci_ann_abs = nan, nan

    rows.append(
        {
            **base_row,
            "type": "ann_abs",
            "est": est_ann_abs,
            "se": se_ann_abs,
            "lci": lci_ann_abs,
            "uci": uci_ann_abs,
        }
    )

    # 4. ann_rel: (theta1 / theta0)^(1/d) - 1
    if (
        theta0 is not None
        and theta1 is not None
        and isfinite(theta0)
        and isfinite(theta1)
        and theta0 > 0
        and theta1 >= 0
    ):
        est_ann_rel = (theta1 / theta0) ** (1.0 / d) - 1.0
        if isfinite(cov) and theta1 > 0:
            term_factor = ((1.0 / d) * (theta1 / theta0) ** (1.0 / d)) ** 2
            var_ann_rel = term_factor * (
                v1 / (theta1**2) + v0 / (theta0**2) - 2.0 * cov / (theta1 * theta0)
            )
            se_ann_rel = standard_error(var_ann_rel)
            lci_ann_rel, uci_ann_rel = confidence_interval(
                est_ann_rel, se_ann_rel, df, method=ci_method, level=level, bounded=False
            )
        else:
            se_ann_rel = nan
            lci_ann_rel, uci_ann_rel = nan, nan
    else:
        est_ann_rel = None
        se_ann_rel = nan
        lci_ann_rel, uci_ann_rel = nan, nan

    rows.append(
        {
            **base_row,
            "type": "ann_rel",
            "est": est_ann_rel,
            "se": se_ann_rel,
            "lci": lci_ann_rel,
            "uci": uci_ann_rel,
        }
    )


__all__ = [
    "compute_changes",
    "get_wave_pairs",
    "validate_time_variables",
]
