"""PPS (unequal probability sampling) design configuration (PLAN.md §14.4b)."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd
import polars as pl


@dataclass(frozen=True, slots=True)
class PPSDesign:
    """Unequal-probability sampling at the first stage (PLAN.md §6, §14.4b)."""

    method: str = "with_replacement"  # "with_replacement" | "without_replacement"
    inclusion_probability: str | None = None
    joint_probability: pl.DataFrame | pd.DataFrame | None = field(default=None, compare=False)
    variance: str = "auto"  # "auto" | "hajek" | "sen_yates_grundy"

    def __post_init__(self) -> None:
        if self.method not in ("with_replacement", "without_replacement"):
            raise ValueError(
                f"method must be 'with_replacement' or 'without_replacement'; "
                f"got {self.method!r}"
            )
        if self.variance not in ("auto", "hajek", "sen_yates_grundy"):
            raise ValueError(
                f"variance must be 'auto', 'hajek', or 'sen_yates_grundy'; "
                f"got {self.variance!r}"
            )
        if self.method == "without_replacement" and self.inclusion_probability is None:
            raise ValueError(
                "inclusion_probability must be provided when method='without_replacement'"
            )
        if self.variance == "sen_yates_grundy" and self.joint_probability is None:
            raise ValueError(
                "joint_probability must be provided when variance='sen_yates_grundy'"
            )

    @property
    def resolved_variance(self) -> str:
        if self.variance == "auto":
            return "sen_yates_grundy" if self.joint_probability is not None else "hajek"
        return self.variance


def normalize_joint_probability(
    joint_prob: pl.DataFrame | pd.DataFrame,
) -> pl.DataFrame:
    """Normalize and validate joint inclusion probabilities table.

    Supports optional 'stratum' column for stratum-specific PSU pair lookup.
    """

    if isinstance(joint_prob, pd.DataFrame):
        jp = pl.from_pandas(joint_prob)
    elif isinstance(joint_prob, pl.DataFrame):
        jp = joint_prob
    else:
        raise TypeError("joint_probability must be a pandas or polars DataFrame")

    required = {"psu_a", "psu_b", "pi_ab"}
    missing = sorted(required - set(jp.columns))
    if missing:
        raise ValueError(f"joint_probability missing required columns: {missing}")

    has_stratum = "stratum" in jp.columns

    select_cols = [
        pl.col("psu_a").cast(pl.String),
        pl.col("psu_b").cast(pl.String),
        pl.col("pi_ab").cast(pl.Float64),
    ]
    if has_stratum:
        select_cols.insert(0, pl.col("stratum").cast(pl.String))

    jp = jp.select(select_cols)

    invalid = jp.filter(
        pl.col("pi_ab").is_null()
        | pl.col("pi_ab").is_nan()
        | (pl.col("pi_ab") <= 0)
        | (pl.col("pi_ab") > 1)
    )
    if invalid.height > 0:
        raise ValueError("joint_probability pi_ab values must be in (0, 1]")

    canonical = jp.with_columns(
        pl.when(pl.col("psu_a") <= pl.col("psu_b"))
        .then(pl.col("psu_a"))
        .otherwise(pl.col("psu_b"))
        .alias("__a"),
        pl.when(pl.col("psu_a") <= pl.col("psu_b"))
        .then(pl.col("psu_b"))
        .otherwise(pl.col("psu_a"))
        .alias("__b"),
    )

    group_keys = ["stratum", "__a", "__b"] if has_stratum else ["__a", "__b"]
    grouped = canonical.group_by(group_keys).agg(
        pl.col("pi_ab").n_unique().alias("n_uniq"),
    )
    conflicts = grouped.filter(pl.col("n_uniq") > 1)
    if conflicts.height > 0:
        row = conflicts.row(0, named=True)
        strat_info = f" in stratum {row['stratum']!r}" if has_stratum else ""
        raise ValueError(
            f"conflicting joint inclusion probabilities for pair "
            f"({row['__a']!r}, {row['__b']!r}){strat_info}"
        )

    out_cols = (
        [
            pl.col("stratum"),
            pl.col("__a").alias("psu_a"),
            pl.col("__b").alias("psu_b"),
            pl.col("pi_ab"),
        ]
        if has_stratum
        else [pl.col("__a").alias("psu_a"), pl.col("__b").alias("psu_b"), pl.col("pi_ab")]
    )
    return canonical.select(out_cols).unique()
