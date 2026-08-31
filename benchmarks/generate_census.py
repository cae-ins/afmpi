"""Generate synthetic census dataset for benchmarks (PLAN.md §14.9)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl


def generate_census_parquet(
    path: str | Path,
    n_rows: int = 10_000_000,
    seed: int = 20260830,
) -> Path:
    """Generate synthetic census dataset with fixed dimensions for benchmark reproducibility."""

    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)

    n_indicators = 30
    n_psus = 500
    n_regions = 33
    n_depts = 108
    n_subprefs = 442

    region_labels = [f"Reg_{r}" for r in range(1, n_regions + 1)]
    dept_labels = [f"Dept_{d}" for d in range(1, n_depts + 1)]
    subpref_labels = [f"SubPref_{s}" for s in range(1, n_subprefs + 1)]

    chunk_size = 5_000_000
    n_chunks = (n_rows + chunk_size - 1) // chunk_size

    import pyarrow.parquet as pq

    writer = None
    for chunk_idx in range(n_chunks):
        rows_in_chunk = min(chunk_size, n_rows - chunk_idx * chunk_size)
        data_dict = {}
        for i in range(1, n_indicators + 1):
            data_dict[f"ind{i}"] = rng.integers(0, 2, size=rows_in_chunk, dtype=np.int8)

        data_dict["psu"] = rng.integers(1, n_psus + 1, size=rows_in_chunk, dtype=np.int32)
        reg_idx = rng.integers(0, n_regions, size=rows_in_chunk)
        dept_idx = rng.integers(0, n_depts, size=rows_in_chunk)
        subpref_idx = rng.integers(0, n_subprefs, size=rows_in_chunk)

        data_dict["region"] = np.array(region_labels, dtype=object)[reg_idx]
        data_dict["department"] = np.array(dept_labels, dtype=object)[dept_idx]
        data_dict["subprefecture"] = np.array(subpref_labels, dtype=object)[subpref_idx]
        data_dict["weight"] = rng.uniform(0.8, 1.2, size=rows_in_chunk).astype(np.float64)

        chunk_df = pl.DataFrame(data_dict)
        arrow_table = chunk_df.to_arrow()
        if writer is None:
            writer = pq.ParquetWriter(dest, arrow_table.schema, compression="zstd")
        writer.write_table(arrow_table)

    if writer is not None:
        writer.close()

    return dest


if __name__ == "__main__":
    import sys

    output_path = sys.argv[1] if len(sys.argv) > 1 else "benchmarks/census_10m.parquet"
    print(f"Generating 10M synthetic census at {output_path}...")
    generate_census_parquet(output_path, n_rows=10_000_000)
    print("Done!")
