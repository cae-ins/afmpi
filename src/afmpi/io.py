"""Parquet and Stata I/O utilities with projection pushdown (PLAN.md §14.9)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import TYPE_CHECKING, Sequence

import pandas as pd
import polars as pl

if TYPE_CHECKING:
    from .design_base import Design
    from .execution_config import ExecutionConfig
    from .results import EstimationResult
    from .specification import Specification


def from_parquet(
    path: str | Path,
    *,
    streaming: bool = True,
    columns: list[str] | Sequence[str] | None = None,
) -> ParquetSource:
    """Create a ParquetSource for lazy, projected ingestion."""

    cols = list(columns) if columns is not None else None
    return ParquetSource(path=Path(path), streaming=streaming, columns=cols)


def to_parquet(
    frame: object,
    path: str | Path,
    *,
    compression: str = "zstd",
) -> None:
    """Export estimation results or data frames to Parquet format."""

    dest = Path(path)
    if hasattr(frame, "estimates") and callable(getattr(frame, "estimates")):
        frame = frame.estimates()

    if isinstance(frame, pl.LazyFrame):
        frame.collect().write_parquet(dest, compression=compression)
    elif isinstance(frame, pl.DataFrame):
        frame.write_parquet(dest, compression=compression)
    elif isinstance(frame, pd.DataFrame):
        pl.from_pandas(frame).write_parquet(dest, compression=compression)
    else:
        raise TypeError("frame must be a EstimationResult, Polars DataFrame/LazyFrame, or Pandas DataFrame")


def to_stata(frame: object, path: str | Path) -> None:
    """Export estimation results or data frames to Stata .dta format via Pandas."""

    dest = Path(path)
    if hasattr(frame, "estimates") and callable(getattr(frame, "estimates")):
        frame = frame.estimates()

    if isinstance(frame, pl.LazyFrame):
        df_pd = frame.collect().to_pandas()
    elif isinstance(frame, pl.DataFrame):
        df_pd = frame.to_pandas()
    elif isinstance(frame, pd.DataFrame):
        df_pd = frame
    else:
        raise TypeError("frame must be a EstimationResult, Polars DataFrame/LazyFrame, or Pandas DataFrame")

    df_pd.to_stata(dest, write_index=False)


@dataclass(frozen=True, slots=True)
class ParquetSource:
    """Lazy Parquet source supporting column projection pushdown."""

    path: Path
    streaming: bool = True
    columns: list[str] | None = None

    def to_lazyframe(self) -> pl.LazyFrame:
        lf = pl.scan_parquet(self.path)
        if self.columns is not None:
            return lf.select(self.columns)
        return lf

    def estimate(
        self,
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
        lazy: bool = True,
        resources: ExecutionConfig | None = None,
    ) -> EstimationResult | object:
        from .estimation import estimate as afmpi_estimate

        projected = _determine_projection(
            path=self.path,
            spec=spec,
            design=design,
            over=over,
            tvar=tvar,
            cot_year=cot_year,
            domain=domain,
            panel_id=panel_id,
            user_columns=self.columns,
        )

        lf = pl.scan_parquet(self.path).select(projected)
        return afmpi_estimate(
            lf,
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
            lazy=lazy,
            resources=resources,
            streaming=self.streaming,
            projected_columns=projected,
        )


def _determine_projection(
    path: Path,
    spec: Specification,
    design: Design | None,
    over: str | Sequence[str] | None,
    tvar: str | None,
    cot_year: str | None,
    domain: str | pl.Expr | None,
    panel_id: str | None,
    user_columns: list[str] | None,
) -> list[str]:
    schema = pl.scan_parquet(path).collect_schema()
    available = set(schema.keys())

    needed: set[str] = set()

    # 1. Spec indicators
    needed.update(spec.indicators)

    # 2. Design columns
    if design is not None:
        needed.update(design.required_columns)
        needed.update(design.design_columns)

    # 3. Over variables
    if over is not None:
        if isinstance(over, str):
            needed.add(over)
        else:
            needed.update(over)

    # 4. Time & panel variables
    if tvar is not None:
        needed.add(tvar)
    if cot_year is not None:
        needed.add(cot_year)
    if panel_id is not None:
        needed.add(panel_id)

    # 5. Domain expression/string
    if domain is not None:
        if isinstance(domain, str):
            words = set(re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", domain))
            needed.update(words & available)
        elif isinstance(domain, pl.Expr):
            # Best-effort match of available column names
            for col_name in available:
                if col_name in str(domain):
                    needed.add(col_name)

    # 6. User explicit columns override/union if requested
    if user_columns is not None:
        needed.update(user_columns)

    projected = [col for col in schema.keys() if col in needed]
    return projected
