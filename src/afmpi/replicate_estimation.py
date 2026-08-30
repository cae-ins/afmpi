"""Replicate weight generation and variance calculation (PLAN.md §14.5a).

This module implements the replication path for variance estimation (JK1 and JKn).
Replicate weights are evaluated in batches without linearizing estimands.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from math import isfinite

import polars as pl

from .deprivation import WEIGHT
from .estimands import RatioEstimand
from .hadamard import sylvester
from .linearization import RatioTotals
from .replicate_design import ReplicateDesign

_REPWGT_PREFIX = "__afmpi_repwgt_"


def replicate_weight_expressions(
    design: ReplicateDesign,
    frame: pl.DataFrame | None = None,
) -> list[pl.Expr]:
    """One n_i^(r) expression per replicate, in replicate order."""

    has_n = frame is not None and WEIGHT in frame.columns
    base_w = pl.col(WEIGHT) if has_n else (
        pl.col(design.weights) if design.weights is not None else pl.lit(1.0)
    )
    if design.household_size is not None and not has_n:
        base_w = base_w * pl.col(design.household_size)

    rep_cols = design.replicate_weights
    if rep_cols is None and frame is not None:
        found = [c for c in frame.columns if c.startswith(_REPWGT_PREFIX)]
        if found:
            rep_cols = tuple(found)

    if rep_cols is None:
        raise ValueError("replicate_weights is None; generate replicate weights first")

    exprs: list[pl.Expr] = []
    for col in rep_cols:
        if design.combined_weights:
            w_r = pl.col(col)
            if design.household_size is not None and not has_n:
                w_r = w_r * pl.col(design.household_size)
        else:
            w_r = base_w * pl.col(col)
        exprs.append(w_r)
    return exprs


def generate_replicate_weights(
    frame: pl.DataFrame,
    design: ReplicateDesign,
) -> tuple[pl.DataFrame, tuple[str, ...], float, tuple[float, ...]]:
    """Materialise the replicate weight columns, and their scale/rscales."""

    if design.method not in ("JK1", "JKn", "BRR", "Fay_BRR", "bootstrap", "SDR"):
        raise NotImplementedError(f"weight generation for {design.method!r} is not implemented")

    base_w = pl.col(design.weights) if design.weights is not None else pl.lit(1.0)

    if design.method == "bootstrap":
        if design.psu is None:
            raise ValueError(
                "psu column must be specified for bootstrap replicate weight generation"
            )

        psu_col = design.psu
        strata_col = design.strata

        if strata_col is not None:
            strata_df = frame.select(
                pl.col(strata_col).cast(pl.String).alias("strata_str")
            ).unique().sort("strata_str")
            strata_list = strata_df["strata_str"].to_list()
        else:
            strata_list = ["__afmpi_all__"]

        psu_map: dict[str, list[str]] = {}
        for h_key in strata_list:
            if strata_col is not None:
                sub_frame = frame.filter(pl.col(strata_col).cast(pl.String) == h_key)
            else:
                sub_frame = frame
            psu_in_h = (
                sub_frame.select(pl.col(psu_col).cast(pl.String).alias("psu_str"))
                .unique()
                .sort("psu_str")["psu_str"]
                .to_list()
            )
            m_h = len(psu_in_h)
            if m_h < 2:
                raise ValueError(
                    f"stratum {h_key!r} contains only {m_h} PSU; "
                    "bootstrap requires at least 2 PSUs per stratum"
                )
            psu_map[h_key] = psu_in_h

        R = design.replicates if design.replicates is not None else 200
        if R < 2:
            raise ValueError(f"bootstrap requires at least 2 replicates; got {R}")

        if design.rscales is not None and len(design.rscales) != R:
            raise ValueError(
                f"rscales length ({len(design.rscales)}) must match number of replicates ({R})"
            )

        import numpy as np

        rng = np.random.default_rng(design.seed)

        col_names: list[str] = []
        exprs_to_add: list[pl.Expr] = []

        for r in range(R):
            col_name = f"{_REPWGT_PREFIX}{r + 1}"
            col_names.append(col_name)

            expr_builder = None
            for h_key in strata_list:
                psus = psu_map[h_key]
                m_h = len(psus)
                drawn = rng.choice(m_h, size=m_h - 1, replace=True)
                counts: dict[str, int] = {}
                for idx in drawn:
                    p_name = psus[idx]
                    counts[p_name] = counts.get(p_name, 0) + 1

                for p_name in psus:
                    cnt = counts.get(p_name, 0)
                    if cnt > 0:
                        factor = (m_h / (m_h - 1.0)) * cnt
                        if strata_col is not None:
                            cond = (pl.col(strata_col).cast(pl.String) == h_key) & (
                                pl.col(psu_col).cast(pl.String) == p_name
                            )
                        else:
                            cond = pl.col(psu_col).cast(pl.String) == p_name

                        if expr_builder is None:
                            expr_builder = pl.when(cond).then(base_w * factor)
                        else:
                            expr_builder = expr_builder.when(cond).then(base_w * factor)

            if expr_builder is None:
                expr = pl.lit(0.0).alias(col_name)
            else:
                expr = expr_builder.otherwise(0.0).alias(col_name)

            exprs_to_add.append(expr)

        scale = 1.0 / R if design.scale is None else design.scale
        rscales = (1.0,) * R if design.rscales is None else design.rscales
        new_frame = frame.with_columns(exprs_to_add)
        return new_frame, tuple(col_names), scale, rscales

    if design.method == "SDR":
        if design.psu is None:
            raise ValueError(
                "psu column must be specified for SDR replicate weight generation"
            )

        psu_col = design.psu
        strata_col = design.strata

        if strata_col is not None:
            strata_df = frame.select(
                pl.col(strata_col).cast(pl.String).alias("strata_str")
            ).unique().sort("strata_str")
            strata_list = strata_df["strata_str"].to_list()
        else:
            strata_list = ["__afmpi_all__"]

        all_psus: list[tuple[str, str]] = []
        for h_key in strata_list:
            if strata_col is not None:
                sub_frame = frame.filter(pl.col(strata_col).cast(pl.String) == h_key)
            else:
                sub_frame = frame
            psu_in_h = (
                sub_frame.select(pl.col(psu_col).cast(pl.String).alias("psu_str"))
                .unique()
                .sort("psu_str")["psu_str"]
                .to_list()
            )
            for p_key in psu_in_h:
                all_psus.append((h_key, p_key))

        m = len(all_psus)
        if m < 1:
            raise ValueError("SDR requires at least 1 PSU")

        k = math.ceil(math.log2(m + 1))
        R = 2**k
        if R < 4:
            R = 4

        if design.rscales is not None and len(design.rscales) != R:
            raise ValueError(
                f"rscales length ({len(design.rscales)}) must match number of replicates ({R})"
            )

        H_df = sylvester(R)
        H_mat = H_df.to_numpy()

        col_names: list[str] = []
        exprs_to_add: list[pl.Expr] = []

        two_pow_minus_1_5 = 2.0**-1.5

        for r in range(R):
            col_name = f"{_REPWGT_PREFIX}{r + 1}"
            col_names.append(col_name)

            expr_builder = None
            for j_idx, (h_key, p_name) in enumerate(all_psus):
                j = j_idx + 1
                c1 = ((j - 1) % (R - 1)) + 1
                c2 = (j % (R - 1)) + 1
                diff = int(H_mat[r, c1]) - int(H_mat[r, c2])
                factor = 1.0 + two_pow_minus_1_5 * diff

                if strata_col is not None:
                    cond = (pl.col(strata_col).cast(pl.String) == h_key) & (
                        pl.col(psu_col).cast(pl.String) == p_name
                    )
                else:
                    cond = pl.col(psu_col).cast(pl.String) == p_name

                if expr_builder is None:
                    expr_builder = pl.when(cond).then(base_w * factor)
                else:
                    expr_builder = expr_builder.when(cond).then(base_w * factor)

            if expr_builder is None:
                expr = pl.lit(0.0).alias(col_name)
            else:
                expr = expr_builder.otherwise(0.0).alias(col_name)

            exprs_to_add.append(expr)

        scale = 4.0 / R if design.scale is None else design.scale
        rscales = (1.0,) * R if design.rscales is None else design.rscales
        new_frame = frame.with_columns(exprs_to_add)
        return new_frame, tuple(col_names), scale, rscales

    if design.method in ("BRR", "Fay_BRR"):
        if design.psu is None:
            raise ValueError(
                f"psu column must be specified for {design.method} replicate weight generation"
            )

        psu_col = design.psu
        strata_col = design.strata

        if strata_col is not None:
            strata_df = (
                frame.select(pl.col(strata_col).cast(pl.String).alias("strata_str"))
                .unique()
                .sort("strata_str")
            )
            strata_list = strata_df["strata_str"].to_list()
        else:
            strata_list = ["__afmpi_all__"]

        H = len(strata_list)

        psu_map: dict[str, list[str]] = {}
        for h_key in strata_list:
            if strata_col is not None:
                sub_frame = frame.filter(pl.col(strata_col).cast(pl.String) == h_key)
            else:
                sub_frame = frame
            psu_in_h = (
                sub_frame.select(pl.col(psu_col).cast(pl.String).alias("psu_str"))
                .unique()
                .sort("psu_str")["psu_str"]
                .to_list()
            )
            m_h = len(psu_in_h)
            if m_h != 2:
                raise ValueError(
                    f"stratum {h_key!r} contains {m_h} PSU; "
                    f"{design.method} requires exactly 2 PSUs per stratum"
                )
            psu_map[h_key] = psu_in_h

        k = math.ceil(math.log2(H + 1))
        R = 2**k
        if R < 4:
            R = 4

        if design.rscales is not None and len(design.rscales) != R:
            raise ValueError(
                f"rscales length ({len(design.rscales)}) must match number of replicates ({R})"
            )

        H_df = sylvester(R)
        H_mat = H_df.to_numpy()

        rho = (
            design.fay
            if (design.method == "Fay_BRR" and design.fay is not None)
            else 0.0
        )
        if design.method == "Fay_BRR" and design.fay is None:
            rho = 0.5

        sel_factor = 2.0 - rho
        nonsel_factor = rho

        col_names: list[str] = []
        exprs_to_add: list[pl.Expr] = []

        for r in range(R):
            col_name = f"{_REPWGT_PREFIX}{r + 1}"
            col_names.append(col_name)

            sel_conds: list[pl.Expr] = []
            for h_idx, h_key in enumerate(strata_list):
                psus = psu_map[h_key]
                delta_rh = int(H_mat[r, h_idx + 1])
                sel_psu = psus[0] if delta_rh == 1 else psus[1]

                if strata_col is not None:
                    cond = (pl.col(strata_col).cast(pl.String) == h_key) & (
                        pl.col(psu_col).cast(pl.String) == sel_psu
                    )
                else:
                    cond = pl.col(psu_col).cast(pl.String) == sel_psu
                sel_conds.append(cond)

            combined_sel = sel_conds[0]
            for c in sel_conds[1:]:
                combined_sel = combined_sel | c

            if design.method == "BRR":
                expr = (
                    pl.when(combined_sel)
                    .then(base_w * 2.0)
                    .otherwise(0.0)
                    .alias(col_name)
                )
            else:
                expr = (
                    pl.when(combined_sel)
                    .then(base_w * sel_factor)
                    .otherwise(base_w * nonsel_factor)
                    .alias(col_name)
                )
            exprs_to_add.append(expr)

        if design.scale is not None:
            scale = design.scale
        else:
            if design.method == "BRR":
                scale = 1.0 / R
            else:
                scale = 1.0 / (R * ((1.0 - rho) ** 2))

        rscales = (1.0,) * R if design.rscales is None else design.rscales
        new_frame = frame.with_columns(exprs_to_add)
        return new_frame, tuple(col_names), scale, rscales

    base_w = pl.col(design.weights) if design.weights is not None else pl.lit(1.0)

    if design.method == "JK1":
        if design.psu is None:
            raise ValueError("psu column must be specified for JK1 replicate weight generation")

        psu_col = design.psu
        psu_df = frame.select(
            pl.col(psu_col).cast(pl.String).alias("psu_str")
        ).unique().sort("psu_str")
        psu_list = psu_df["psu_str"].to_list()
        m = len(psu_list)
        if m < 2:
            raise ValueError("JK1 requires at least 2 PSUs")

        col_names: list[str] = []
        exprs_to_add: list[pl.Expr] = []
        for r in range(m):
            col_name = f"{_REPWGT_PREFIX}{r + 1}"
            col_names.append(col_name)
            target_psu = psu_list[r]
            expr = (
                pl.when(pl.col(psu_col).cast(pl.String) == target_psu)
                .then(0.0)
                .otherwise(base_w * (m / (m - 1)))
                .alias(col_name)
            )
            exprs_to_add.append(expr)

        if design.rscales is not None and len(design.rscales) != m:
            raise ValueError(
                f"rscales length ({len(design.rscales)}) must match number of replicates ({m})"
            )

        scale = (m - 1) / m if design.scale is None else design.scale
        rscales = (1.0,) * m if design.rscales is None else design.rscales
        new_frame = frame.with_columns(exprs_to_add)
        return new_frame, tuple(col_names), scale, rscales

    # JKn method
    if design.psu is None:
        raise ValueError("psu column must be specified for JKn replicate weight generation")

    psu_col = design.psu
    strata_col = design.strata

    if strata_col is not None:
        strata_df = frame.select(
            pl.col(strata_col).cast(pl.String).alias("strata_str")
        ).unique().sort("strata_str")
        strata_list = strata_df["strata_str"].to_list()
    else:
        strata_list = ["__afmpi_all__"]

    col_names = []
    rscales_list: list[float] = []
    exprs_to_add = []
    replicate_index = 0

    for h_key in strata_list:
        if strata_col is not None:
            sub_frame = frame.filter(pl.col(strata_col).cast(pl.String) == h_key)
        else:
            sub_frame = frame
        psu_in_h = (
            sub_frame.select(pl.col(psu_col).cast(pl.String).alias("psu_str"))
            .unique()
            .sort("psu_str")["psu_str"]
            .to_list()
        )
        m_h = len(psu_in_h)
        if m_h < 2:
            raise ValueError(
                f"stratum {h_key!r} contains only {m_h} PSU; "
                "JKn requires at least 2 PSUs per stratum"
            )

        for c_psu in psu_in_h:
            replicate_index += 1
            col_name = f"{_REPWGT_PREFIX}{replicate_index}"
            col_names.append(col_name)
            rscales_list.append((m_h - 1) / m_h)

            if strata_col is not None:
                cond_same_psu = (pl.col(strata_col).cast(pl.String) == h_key) & (
                    pl.col(psu_col).cast(pl.String) == c_psu
                )
                cond_same_stratum = pl.col(strata_col).cast(pl.String) == h_key
                expr = (
                    pl.when(cond_same_psu)
                    .then(0.0)
                    .when(cond_same_stratum)
                    .then(base_w * (m_h / (m_h - 1)))
                    .otherwise(base_w)
                    .alias(col_name)
                )
            else:
                cond_same_psu = pl.col(psu_col).cast(pl.String) == c_psu
                expr = (
                    pl.when(cond_same_psu)
                    .then(0.0)
                    .otherwise(base_w * (m_h / (m_h - 1)))
                    .alias(col_name)
                )
            exprs_to_add.append(expr)

    if design.rscales is not None and len(design.rscales) != len(col_names):
        raise ValueError(
            f"rscales length ({len(design.rscales)}) must match number of replicates ({len(col_names)})"
        )

    scale = 1.0 if design.scale is None else design.scale
    rscales = tuple(rscales_list) if design.rscales is None else design.rscales
    new_frame = frame.with_columns(exprs_to_add)
    return new_frame, tuple(col_names), scale, rscales


def replicate_totals(
    frame: pl.DataFrame,
    estimands: tuple[RatioEstimand, ...],
    weights: Sequence[pl.Expr],
    *,
    group_column: str | None = None,
    batch_size: int = 64,
) -> list[tuple[RatioTotals, ...]] | dict[str, list[tuple[RatioTotals, ...]]]:
    """Re-evaluate T(.) once per replicate, in batches (PLAN.md §7)."""

    if batch_size < 1:
        raise ValueError(f"batch_size must be positive; got {batch_size}")

    R = len(weights)
    if group_column is None:
        result_list: list[tuple[RatioTotals, ...]] = []
        for batch_start in range(0, R, batch_size):
            batch_weights = weights[batch_start : batch_start + batch_size]
            K = len(batch_weights)
            select_exprs: list[pl.Expr] = []
            for b, w in enumerate(batch_weights):
                for item in estimands:
                    select_exprs.append((w * item.y).sum().alias(f"y_{b}_{item.key}"))
                    select_exprs.append((w * item.x).sum().alias(f"x_{b}_{item.key}"))

            agg_row = frame.select(select_exprs).row(0, named=True)
            for b in range(K):
                totals_b = tuple(
                    RatioTotals(
                        estimand=item,
                        numerator=float(agg_row[f"y_{b}_{item.key}"] or 0.0),
                        denominator=float(agg_row[f"x_{b}_{item.key}"] or 0.0),
                    )
                    for item in estimands
                )
                result_list.append(totals_b)
        return result_list

    subgroups_result: dict[str, list[tuple[RatioTotals, ...]]] = {}
    for batch_start in range(0, R, batch_size):
        batch_weights = weights[batch_start : batch_start + batch_size]
        K = len(batch_weights)
        agg_exprs: list[pl.Expr] = []
        for b, w in enumerate(batch_weights):
            for item in estimands:
                agg_exprs.append((w * item.y).sum().alias(f"y_{b}_{item.key}"))
                agg_exprs.append((w * item.x).sum().alias(f"x_{b}_{item.key}"))

        grouped = frame.group_by(group_column).agg(agg_exprs)
        for row_dict in grouped.iter_rows(named=True):
            subgroup_val = str(row_dict[group_column])
            if subgroup_val not in subgroups_result:
                subgroups_result[subgroup_val] = []
            for b in range(K):
                totals_b = tuple(
                    RatioTotals(
                        estimand=item,
                        numerator=float(row_dict[f"y_{b}_{item.key}"] or 0.0),
                        denominator=float(row_dict[f"x_{b}_{item.key}"] or 0.0),
                    )
                    for item in estimands
                )
                subgroups_result[subgroup_val].append(totals_b)
    return subgroups_result


def replicate_variance(
    point: tuple[RatioTotals, ...],
    replicates: Sequence[tuple[RatioTotals, ...]],
    keys: tuple[str, ...],
    *,
    scale: float,
    rscales: Sequence[float],
    mse: bool,
) -> dict[str, float]:
    """Calculate replicate variance for each estimand key."""

    if len(rscales) != len(replicates):
        raise ValueError(
            f"rscales length ({len(rscales)}) must match "
            f"number of replicates ({len(replicates)})"
        )

    R = len(replicates)
    if R == 0:
        return {key: float("nan") for key in keys}

    variances: dict[str, float] = {}
    for key in keys:
        pt_ratio = next((r for r in point if r.key == key), None)
        theta_hat = pt_ratio.value if pt_ratio is not None else None

        theta_r_list: list[float] = []
        has_nan_rep = False
        for rep in replicates:
            r_ratio = next((r for r in rep if r.key == key), None)
            val = r_ratio.value if r_ratio is not None else None
            if val is None or not isfinite(val):
                has_nan_rep = True
                break
            theta_r_list.append(val)

        if has_nan_rep or theta_hat is None or not isfinite(theta_hat):
            variances[key] = float("nan")
            continue

        if mse:
            theta_c = theta_hat
        else:
            theta_c = sum(theta_r_list) / R

        var_val = scale * sum(
            rscales[r] * ((theta_r_list[r] - theta_c) ** 2) for r in range(R)
        )
        variances[key] = float(var_val)

    return variances


def replicate_vcov(
    point: tuple[RatioTotals, ...],
    replicates: Sequence[tuple[RatioTotals, ...]],
    keys: tuple[str, ...],
    *,
    scale: float,
    rscales: Sequence[float],
    mse: bool,
) -> dict[tuple[str, str], float]:
    """Calculate replicate variance-covariance matrix for estimand keys."""

    if len(rscales) != len(replicates):
        raise ValueError(
            f"rscales length ({len(rscales)}) must match "
            f"number of replicates ({len(replicates)})"
        )

    R = len(replicates)
    if R == 0:
        return {(k1, k2): float("nan") for k1 in keys for k2 in keys}

    theta_hat_map: dict[str, float | None] = {}
    theta_r_map: dict[str, list[float]] = {}
    has_nan_map: dict[str, bool] = {}

    for key in keys:
        pt_ratio = next((r for r in point if r.key == key), None)
        hat = pt_ratio.value if pt_ratio is not None else None
        theta_hat_map[key] = hat

        r_list: list[float] = []
        has_nan = False
        if hat is None or not isfinite(hat):
            has_nan = True
        else:
            for rep in replicates:
                r_ratio = next((r for r in rep if r.key == key), None)
                val = r_ratio.value if r_ratio is not None else None
                if val is None or not isfinite(val):
                    has_nan = True
                    break
                r_list.append(val)

        has_nan_map[key] = has_nan
        theta_r_map[key] = r_list

    theta_c_map: dict[str, float] = {}
    for key in keys:
        if not has_nan_map[key]:
            if mse:
                theta_c_map[key] = theta_hat_map[key]  # type: ignore[assignment]
            else:
                theta_c_map[key] = sum(theta_r_map[key]) / R

    vcov: dict[tuple[str, str], float] = {}
    for k1 in keys:
        for k2 in keys:
            if has_nan_map[k1] or has_nan_map[k2]:
                vcov[(k1, k2)] = float("nan")
            else:
                val = scale * sum(
                    rscales[r]
                    * (theta_r_map[k1][r] - theta_c_map[k1])
                    * (theta_r_map[k2][r] - theta_c_map[k2])
                    for r in range(R)
                )
                vcov[(k1, k2)] = float(val)

    return vcov

