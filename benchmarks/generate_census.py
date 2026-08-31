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
    rng = np.random.default_rng(seed)

    n_indicators = 30
    n_psus = 500
    n_regions = 33
    n_depts = 108
    n_subprefs = 442

    chunk_size = min(n_rows, 1_000_000)
    n_chunks = (n_rows + chunk_size - 1) // chunk_size

    # Prepare schema & data chunks
    data_dict = {}

    # Indicators (binary 0/1 float64)
    for i in range(1, n_indicators + 1):
        data_dict[f"ind{i}"] = rng.integers(0, 2, size=n_rows, dtype=np.int8)

    # Design/Geographic columns
    data_dict["psu"] = (rng.integers(1, n_psus + 1, size=n_rows)).astype(np.int32)
    data_dict["region"] = [f"Reg_{r}" for r in rng.integers(1, n_regions + 1, size=n_rows)]
    data_dict["department"] = [f"Dept_{d}" for d in rng.integers(1, n_depts + 1, size=n_rows)]
    data_dict["subprefecture"] = [f"SubPref_{s}" for s in rng.integers(1, n_subprefs + 1, size=n_rows)]
    data_dict["weight"] = rng.uniform(0.8, 1.2, size=n_rows).astype(np.float64)

    df = pl.DataFrame(data_dict)
    dest.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(dest, compression="zstd")

    return dest


if __name__ == "__main__":
    import sys

    output_path = sys.argv[1] if len(sys.argv) > 1 else "benchmarks/census_10m.parquet"
    print(f"Generating 10M synthetic census at {output_path}...")
    generate_census_parquet(output_path, n_rows=10_000_000)
    print("Done!")
