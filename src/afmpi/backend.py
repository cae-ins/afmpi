"""Ingestion backend: convert input frames to Polars DataFrame or LazyFrame (PLAN.md §14.9)."""

from __future__ import annotations

from typing import Literal

import pandas as pd
import polars as pl

InputKind = Literal["pandas", "polars", "polars-lazy", "parquet"]


def to_frame(df: object) -> tuple[pl.DataFrame | pl.LazyFrame, InputKind]:
    """Convert input dataset to Polars DataFrame or LazyFrame and identify input family.

    Output conversion rule: pandas in -> pandas out; everything else (polars,
    polars-lazy, parquet) -> polars out. A LazyFrame input changes execution timing
    (lazy) without changing output family.
    """

    if hasattr(df, "to_lazyframe"):
        return df.to_lazyframe(), "parquet"
    if isinstance(df, pl.LazyFrame):
        return df, "polars-lazy"
    if isinstance(df, pl.DataFrame):
        return df, "polars"
    if isinstance(df, pd.DataFrame):
        return pl.from_pandas(df, include_index=False, rechunk=False), "pandas"

    raise TypeError(
        "df must be a pandas.DataFrame, polars.DataFrame, polars.LazyFrame, or ParquetSource"
    )
