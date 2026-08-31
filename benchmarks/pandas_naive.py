"""Pure Pandas naive implementation of Alkire-Foster estimation (PLAN.md §14.9).

Used for comparative performance benchmarks against afmpi streaming/lazy engine.
"""

from __future__ import annotations

import time

import numpy as np
import pandas as pd


def run_pandas_naive(
    df: pd.DataFrame,
    indicators: list[str],
    weights: str = "weight",
    cutoffs: list[float] | None = None,
    over_vars: list[str] | None = None,
) -> dict[str, float]:
    """Run steps (b)-(e) in pure pandas without Polars optimization."""
    if cutoffs is None:
        cutoffs = [0.2, 0.25, 0.3, 0.33, 0.4, 0.5, 0.6, 0.7]
    if over_vars is None:
        over_vars = ["region", "department", "subprefecture"]

    t0 = time.perf_counter()

    # Step (b) & (e): National H, A, M0 for 8 cutoffs
    w = df[weights].values
    total_w = w.sum()
    d = len(indicators)

    # Calculate c_i scores
    c_i = df[indicators].values.sum(axis=1) / float(d)

    results = {}

    for k in cutoffs:
        poor = c_i >= k
        c_k = np.where(poor, c_i, 0.0)

        H = np.sum(w * poor) / total_w
        M0 = np.sum(w * c_k) / total_w
        _A = M0 / H if H > 0 else 0.0

        results[f"nat_k_{k}_M0"] = M0

        # Step (d): Indicator contributions
        for ind in indicators:
            g_ij_k = np.where(poor[:, None], df[[ind]].values, 0)
            ch_j = np.sum(w[:, None] * g_ij_k) / total_w
            actb_j = ch_j / float(d)
            pctb_j = actb_j / M0 if M0 > 0 else 0.0
            results[f"k_{k}_{ind}_pctb"] = pctb_j

        # Step (c): 3 disaggregations
        for var in over_vars:
            groups = df.groupby(var, observed=True)
            for grp, group_df in groups:
                grp_w = group_df[weights].values
                grp_total_w = grp_w.sum()
                grp_c_i = group_df[indicators].values.sum(axis=1) / float(d)
                grp_poor = grp_c_i >= k
                grp_c_k = np.where(grp_poor, grp_c_i, 0.0)
                grp_M0 = np.sum(grp_w * grp_c_k) / grp_total_w if grp_total_w > 0 else 0.0
                results[f"{var}_{grp}_k_{k}_M0"] = grp_M0

    elapsed = time.perf_counter() - t0
    return {"elapsed_sec": elapsed, "num_estimates": len(results)}


if __name__ == "__main__":
    import sys

    parquet_path = sys.argv[1] if len(sys.argv) > 1 else "benchmarks/census_100k.parquet"
    print(f"Loading {parquet_path} into pandas...")
    df = pd.read_parquet(parquet_path)
    indicators = [c for c in df.columns if c.startswith("ind")]
    print(f"Running naive pandas benchmark on {len(df)} rows...")
    res = run_pandas_naive(df, indicators)
    print(
        f"Pandas naive execution time: {res['elapsed_sec']:.2f}s "
        f"({res['num_estimates']} estimates)"
    )
