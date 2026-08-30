"""Missing-value policies for Alkire-Foster indicators (PLAN.md §14.8)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import polars as pl

from .specification import Specification


def deprived_column(index: int) -> str:
    """Column holding ``g_ij`` as a float, with missing values read as zero."""
    return f"__afmpi_g{index}"


def observed_column(index: int) -> str:
    """Column holding ``1`` when indicator ``j`` is observed for the row."""
    return f"__afmpi_obs{index}"


def contribution_column(index: int) -> str:
    """Column holding the weighted deprivation ``w_j * g_ij`` used by ``c_i``."""
    return f"__afmpi_wc{index}"


SCORE = "__afmpi_c"


@dataclass(frozen=True, slots=True)
class MissingReport:
    """Audit report for missing-value policy application (PLAN.md §14.8)."""

    policy: str
    rows_in: int
    rows_out: int
    dropped: int
    per_indicator: pl.DataFrame  # indicator, missing, missing_share


def apply(frame: pl.DataFrame, spec: Specification) -> tuple[pl.DataFrame, MissingReport]:
    """Add ``g_ij``, observation flags, ``w_j * g_ij`` and ``c_i`` per policy.

    ``listwise_deletion`` drops rows with any missing indicator. ``reweighting``
    keeps them and redistributes the weight of missing indicators over observed ones.
    ``treat_as_nondeprived`` treats missing values as non-deprived (g_ij=0, observed=1).
    A custom callable receives ``(frame, spec)`` and returns a DataFrame.
    """
    weights = spec.indicator_weights
    indicators = spec.indicators
    rows_in = frame.height

    per_indicator_rows: list[dict[str, object]] = []
    for indicator in indicators:
        missing_count = frame.select(pl.col(indicator).is_null().sum()).item()
        missing_share = float(missing_count) / float(rows_in) if rows_in > 0 else 0.0
        per_indicator_rows.append(
            {
                "indicator": indicator,
                "missing": int(missing_count),
                "missing_share": float(missing_share),
            }
        )
    per_indicator_schema = {
        "indicator": pl.String,
        "missing": pl.Int64,
        "missing_share": pl.Float64,
    }
    per_indicator_df = pl.DataFrame(per_indicator_rows, schema=per_indicator_schema)

    policy = spec.missing_policy
    policy_name = policy if isinstance(policy, str) else getattr(policy, "__name__", str(policy))

    if isinstance(policy, str):
        if policy == "listwise_deletion":
            complete = pl.all_horizontal([pl.col(item).is_not_null() for item in indicators])
            out_frame = frame.filter(complete)
            contributions = [
                (pl.col(item).cast(pl.Float64) * weights[item]).alias(contribution_column(index))
                for index, item in enumerate(indicators)
            ]
            g_cols = [
                pl.col(item).cast(pl.Float64).fill_null(0.0).alias(deprived_column(index))
                for index, item in enumerate(indicators)
            ]
            obs_cols = [
                pl.col(item).is_not_null().cast(pl.Float64).alias(observed_column(index))
                for index, item in enumerate(indicators)
            ]
            if out_frame.height > 0:
                out_frame = out_frame.with_columns(*contributions, *g_cols, *obs_cols)
                out_frame = out_frame.with_columns(
                    pl.sum_horizontal(
                        [pl.col(contribution_column(index)) for index in range(len(indicators))]
                    ).alias(SCORE)
                )

        elif policy == "reweighting":
            observed_weight = pl.sum_horizontal(
                [
                    pl.when(pl.col(item).is_not_null()).then(weights[item]).otherwise(0.0)
                    for item in indicators
                ]
            )
            out_frame = frame.filter(observed_weight > 0)
            contributions = [
                pl.when(pl.col(item).is_not_null())
                .then(pl.col(item).cast(pl.Float64) * weights[item] / observed_weight)
                .otherwise(0.0)
                .alias(contribution_column(index))
                for index, item in enumerate(indicators)
            ]
            g_cols = [
                pl.col(item).cast(pl.Float64).fill_null(0.0).alias(deprived_column(index))
                for index, item in enumerate(indicators)
            ]
            obs_cols = [
                pl.col(item).is_not_null().cast(pl.Float64).alias(observed_column(index))
                for index, item in enumerate(indicators)
            ]
            if out_frame.height > 0:
                out_frame = out_frame.with_columns(*contributions, *g_cols, *obs_cols)
                out_frame = out_frame.with_columns(
                    pl.sum_horizontal(
                        [pl.col(contribution_column(index)) for index in range(len(indicators))]
                    ).alias(SCORE)
                )

        elif policy == "treat_as_nondeprived":
            out_frame = frame
            g_cols = [
                pl.col(item).cast(pl.Float64).fill_null(0.0).alias(deprived_column(index))
                for index, item in enumerate(indicators)
            ]
            contributions = [
                (pl.col(deprived_column(index)) * weights[item]).alias(contribution_column(index))
                for index, item in enumerate(indicators)
            ]
            obs_cols = [
                pl.lit(1.0, dtype=pl.Float64).alias(observed_column(index))
                for index, item in enumerate(indicators)
            ]
            if out_frame.height > 0:
                out_frame = out_frame.with_columns(*g_cols, *obs_cols)
                out_frame = out_frame.with_columns(*contributions)
                out_frame = out_frame.with_columns(
                    pl.sum_horizontal(
                        [pl.col(contribution_column(index)) for index in range(len(indicators))]
                    ).alias(SCORE)
                )
        else:
            raise ValueError(f"unknown string missing_policy: {policy!r}")

    elif callable(policy):
        res = policy(frame, spec)
        if not isinstance(res, pl.DataFrame):
            raise TypeError(
                f"custom missing_policy must return a polars.DataFrame, got {type(res)}"
            )

        _validate_custom_policy_output(res, spec, indicators)
        out_frame = res.with_columns(
            pl.sum_horizontal(
                [pl.col(contribution_column(index)) for index in range(len(indicators))]
            ).alias(SCORE)
        )
    else:
        raise TypeError(f"missing_policy must be string or callable, got {type(policy)}")

    rows_out = out_frame.height
    dropped = rows_in - rows_out
    report = MissingReport(
        policy=policy_name,
        rows_in=rows_in,
        rows_out=rows_out,
        dropped=dropped,
        per_indicator=per_indicator_df,
    )
    return out_frame, report


def _validate_custom_policy_output(
    frame: pl.DataFrame,
    spec: Specification,
    indicators: tuple[str, ...],
) -> None:
    for index, indicator in enumerate(indicators):
        dep_col = deprived_column(index)
        obs_col = observed_column(index)
        contrib_col = contribution_column(index)

        for col_name, label in [
            (dep_col, "deprived_column"),
            (obs_col, "observed_column"),
            (contrib_col, "contribution_column"),
        ]:
            if col_name not in frame.columns:
                raise ValueError(
                    f"custom missing_policy output is missing required column {col_name!r} "
                    f"({label} for indicator {indicator!r}, index {index})"
                )

        dep_invalid = frame.select(
            (
                pl.col(dep_col).is_null()
                | pl.col(dep_col).is_nan()
                | ~pl.col(dep_col).is_in([0, 1])
            ).any()
        ).item()
        if dep_invalid:
            invalid_vals = (
                frame.select(
                    pl.col(dep_col).filter(
                        pl.col(dep_col).is_null()
                        | pl.col(dep_col).is_nan()
                        | ~pl.col(dep_col).is_in([0, 1])
                    ).unique()
                )
                .to_series()
                .to_list()
            )
            raise ValueError(
                f"custom missing_policy column {dep_col!r} (g_ij for indicator {indicator!r}) "
                f"must contain values in {{0, 1}}; found invalid values: {invalid_vals[:5]}"
            )

        obs_invalid = frame.select(
            (
                pl.col(obs_col).is_null()
                | pl.col(obs_col).is_nan()
                | ~pl.col(obs_col).is_in([0, 1])
            ).any()
        ).item()
        if obs_invalid:
            invalid_vals = (
                frame.select(
                    pl.col(obs_col).filter(
                        pl.col(obs_col).is_null()
                        | pl.col(obs_col).is_nan()
                        | ~pl.col(obs_col).is_in([0, 1])
                    ).unique()
                )
                .to_series()
                .to_list()
            )
            raise ValueError(
                f"custom missing_policy column {obs_col!r} (observed_ij for indicator {indicator!r}) "
                f"must contain values in {{0, 1}}; found invalid values: {invalid_vals[:5]}"
            )

    c_series = frame.select(
        pl.sum_horizontal([pl.col(contribution_column(idx)) for idx in range(len(indicators))]).alias(
            "c"
        )
    ).to_series()
    c_invalid = (
        c_series.is_null().any()
        or c_series.is_nan().any()
        or (c_series < 0.0 - 1e-9).any()
        or (c_series > 1.0 + 1e-9).any()
    )
    if c_invalid:
        min_val = float(c_series.min()) if len(c_series) > 0 else float("nan")
        max_val = float(c_series.max()) if len(c_series) > 0 else float("nan")
        raise ValueError(
            f"custom missing_policy produces calculated score c_i outside [0, 1]: "
            f"min={min_val}, max={max_val}"
        )
