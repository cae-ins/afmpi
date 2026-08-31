"""Deterministic synthetic data generators for afmpi conformity test suite (PLAN.md §14.10).

Each function produces a reproducible polars DataFrame from a fixed random seed.
The same datasets can be exported to CSV for R reference scripts.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl

DEFAULT_SEED = 20260830


def generate_srs(seed: int = DEFAULT_SEED, n: int = 100) -> pl.DataFrame:
    """Generate Simple Random Sample (unstratified, unclustered)."""
    rng = np.random.default_rng(seed)
    w = rng.uniform(0.5, 2.5, size=n).round(4)
    size = rng.integers(1, 6, size=n)
    i0 = rng.binomial(1, 0.4, size=n)
    i1 = rng.binomial(1, 0.5, size=n)
    i2 = rng.binomial(1, 0.3, size=n)
    i3 = rng.binomial(1, 0.6, size=n)
    return pl.DataFrame(
        {
            "id": list(range(1, n + 1)),
            "w": w,
            "size": size,
            "i0": i0,
            "i1": i1,
            "i2": i2,
            "i3": i3,
        }
    )


def generate_stratified_srs(seed: int = DEFAULT_SEED, n_per_stratum: int = 40) -> pl.DataFrame:
    """Generate Stratified SRS (3 strata, unequal sampling weights)."""
    rng = np.random.default_rng(seed)
    strata = ["S1", "S2", "S3"]
    rows = []
    uid = 1
    for s_idx, s in enumerate(strata):
        base_rate = 0.25 + 0.15 * s_idx
        for _ in range(n_per_stratum):
            rows.append(
                {
                    "id": uid,
                    "stratum": s,
                    "w": round(float(rng.uniform(0.8 + 0.3 * s_idx, 1.5 + 0.5 * s_idx)), 4),
                    "size": int(rng.integers(1, 6)),
                    "i0": int(rng.binomial(1, min(0.9, base_rate))),
                    "i1": int(rng.binomial(1, min(0.9, base_rate + 0.1))),
                    "i2": int(rng.binomial(1, min(0.9, base_rate - 0.05))),
                    "i3": int(rng.binomial(1, min(0.9, base_rate + 0.2))),
                }
            )
            uid += 1
    return pl.DataFrame(rows)


def generate_cluster_1stage(
    seed: int = DEFAULT_SEED, n_clusters: int = 8, cluster_size: int = 15
) -> pl.DataFrame:
    """Generate 1-stage Cluster sample (unstratified, 8 PSUs)."""
    rng = np.random.default_rng(seed)
    rows = []
    uid = 1
    for c_idx in range(1, n_clusters + 1):
        cluster_name = f"C{c_idx}"
        c_rate = 0.2 + 0.08 * (c_idx % 5)
        for _ in range(cluster_size):
            rows.append(
                {
                    "id": uid,
                    "psu": cluster_name,
                    "w": round(float(rng.uniform(0.7, 2.0)), 4),
                    "size": int(rng.integers(1, 6)),
                    "i0": int(rng.binomial(1, c_rate)),
                    "i1": int(rng.binomial(1, min(0.9, c_rate + 0.1))),
                    "i2": int(rng.binomial(1, min(0.9, c_rate + 0.05))),
                    "i3": int(rng.binomial(1, min(0.9, c_rate + 0.15))),
                }
            )
            uid += 1
    return pl.DataFrame(rows)


def generate_stratified_cluster(
    seed: int = DEFAULT_SEED,
    n_strata: int = 3,
    psu_per_stratum: int = 3,
    obs_per_psu: int = 12,
) -> pl.DataFrame:
    """Generate Stratified Cluster sample (3 strata, 3 PSUs each = 9 PSUs)."""
    rng = np.random.default_rng(seed)
    rows = []
    uid = 1
    for s_idx in range(1, n_strata + 1):
        s_name = f"S{s_idx}"
        for p_idx in range(1, psu_per_stratum + 1):
            p_name = f"P{s_idx}_{p_idx}"
            p_rate = 0.2 + 0.1 * s_idx + 0.05 * p_idx
            for _ in range(obs_per_psu):
                rows.append(
                    {
                        "id": uid,
                        "stratum": s_name,
                        "psu": p_name,
                        "w": round(float(rng.uniform(0.6 + 0.2 * s_idx, 1.8 + 0.3 * s_idx)), 4),
                        "size": int(rng.integers(1, 6)),
                        "i0": int(rng.binomial(1, min(0.9, p_rate))),
                        "i1": int(rng.binomial(1, min(0.9, p_rate + 0.05))),
                        "i2": int(rng.binomial(1, min(0.9, p_rate - 0.05))),
                        "i3": int(rng.binomial(1, min(0.9, p_rate + 0.1))),
                    }
                )
                uid += 1
    return pl.DataFrame(rows)


def generate_multistage(seed: int = DEFAULT_SEED) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Generate 2-stage designs with FPC at each stage.

    Returns:
        (df_fpc, df_census_stage1)
    """
    # 2 strata, 2 PSUs sampled per stratum out of 4 (f1 = 0.5)
    # 2 SSUs sampled per PSU out of 8 (f2 = 0.25)
    # 2 obs per SSU -> 16 obs total
    rows_fpc = []
    uid = 1
    for s_idx, s in enumerate(["H1", "H2"]):
        for p_idx in [1, 2]:
            psu = f"P{s_idx + 1}_{p_idx}"
            for ssu_idx in [1, 2]:
                ssu = f"S{s_idx + 1}_{p_idx}_{ssu_idx}"
                for h_idx in [1, 2]:
                    # Deterministic deprivation pattern
                    i0 = 1 if (s_idx + p_idx + ssu_idx + h_idx) % 2 == 0 else 0
                    i1 = 1 if h_idx == 1 else 0
                    i2 = 1 if (s_idx + ssu_idx) % 2 == 0 else 0
                    i3 = 1 if p_idx == 1 else 0
                    rows_fpc.append(
                        {
                            "id": uid,
                            "stratum": s,
                            "psu": psu,
                            "ssu": ssu,
                            "f1": 0.5,
                            "f2": 0.25,
                            "w": 1.0,
                            "i0": i0,
                            "i1": i1,
                            "i2": i2,
                            "i3": i3,
                        }
                    )
                    uid += 1

    # Stage 1 Census variant (f1 = 1.0, f2 = 0.5)
    rows_census = []
    uid = 1
    for s in ["H1"]:
        for p_idx in [1, 2]:
            psu = f"P1_{p_idx}"
            for ssu_idx in [1, 2]:
                ssu = f"S1_{p_idx}_{ssu_idx}"
                for h_idx in [1, 2]:
                    i0 = 1 if (p_idx + ssu_idx) % 2 == 0 else 0
                    i1 = 1 if h_idx == 1 else 0
                    i2 = 1 if p_idx == 1 else 0
                    i3 = 1 if ssu_idx == 2 else 0
                    rows_census.append(
                        {
                            "id": uid,
                            "stratum": s,
                            "psu": psu,
                            "ssu": ssu,
                            "f1": 1.0,
                            "f2": 0.5,
                            "w": 1.0,
                            "i0": i0,
                            "i1": i1,
                            "i2": i2,
                            "i3": i3,
                        }
                    )
                    uid += 1

    return pl.DataFrame(rows_fpc), pl.DataFrame(rows_census)


def generate_pps(seed: int = DEFAULT_SEED) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Generate PPS sample with and without joint inclusion probabilities.

    Returns:
        (df_pps, df_joint_probs)
    """
    rows = [
        {
            "stratum": "H1",
            "psu": "P1",
            "w": 10.0,
            "pi": 0.2,
            "i0": 1,
            "i1": 1,
            "i2": 0,
            "i3": 1,
        },
        {
            "stratum": "H1",
            "psu": "P1",
            "w": 10.0,
            "pi": 0.2,
            "i0": 1,
            "i1": 0,
            "i2": 1,
            "i3": 0,
        },
        {"stratum": "H1", "psu": "P2", "w": 5.0, "pi": 0.4, "i0": 0, "i1": 1, "i2": 0, "i3": 1},
        {"stratum": "H1", "psu": "P2", "w": 5.0, "pi": 0.4, "i0": 0, "i1": 0, "i2": 1, "i3": 0},
        {
            "stratum": "H2",
            "psu": "P3",
            "w": 4.0,
            "pi": 0.25,
            "i0": 1,
            "i1": 1,
            "i2": 1,
            "i3": 0,
        },
        {
            "stratum": "H2",
            "psu": "P3",
            "w": 4.0,
            "pi": 0.25,
            "i0": 1,
            "i1": 0,
            "i2": 0,
            "i3": 1,
        },
        {"stratum": "H2", "psu": "P4", "w": 2.0, "pi": 0.5, "i0": 0, "i1": 1, "i2": 1, "i3": 1},
        {"stratum": "H2", "psu": "P4", "w": 2.0, "pi": 0.5, "i0": 0, "i1": 0, "i2": 0, "i3": 0},
    ]
    df_pps = pl.DataFrame(rows)

    joint_rows = [
        {"stratum": "H1", "psu_a": "P1", "psu_b": "P1", "pi_ab": 0.2},
        {"stratum": "H1", "psu_a": "P1", "psu_b": "P2", "pi_ab": 0.05},
        {"stratum": "H1", "psu_a": "P2", "psu_b": "P1", "pi_ab": 0.05},
        {"stratum": "H1", "psu_a": "P2", "psu_b": "P2", "pi_ab": 0.4},
        {"stratum": "H2", "psu_a": "P3", "psu_b": "P3", "pi_ab": 0.25},
        {"stratum": "H2", "psu_a": "P3", "psu_b": "P4", "pi_ab": 0.08},
        {"stratum": "H2", "psu_a": "P4", "psu_b": "P3", "pi_ab": 0.08},
        {"stratum": "H2", "psu_a": "P4", "psu_b": "P4", "pi_ab": 0.5},
    ]
    df_joint = pl.DataFrame(joint_rows)

    return df_pps, df_joint


def generate_lonely_psu(seed: int = DEFAULT_SEED) -> pl.DataFrame:
    """Generate sample with a lonely PSU (stratum 3 has 1 PSU)."""
    rows = [
        # Stratum 1: 2 PSUs
        {"stratum": "H1", "psu": "P1", "w": 1.0, "i0": 1, "i1": 1, "i2": 0, "i3": 0},
        {"stratum": "H1", "psu": "P1", "w": 1.2, "i0": 0, "i1": 1, "i2": 1, "i3": 0},
        {"stratum": "H1", "psu": "P2", "w": 0.8, "i0": 1, "i1": 0, "i2": 1, "i3": 1},
        {"stratum": "H1", "psu": "P2", "w": 1.1, "i0": 0, "i1": 0, "i2": 0, "i3": 1},
        # Stratum 2: 2 PSUs
        {"stratum": "H2", "psu": "P3", "w": 1.0, "i0": 1, "i1": 0, "i2": 1, "i3": 0},
        {"stratum": "H2", "psu": "P3", "w": 1.3, "i0": 1, "i1": 1, "i2": 0, "i3": 1},
        {"stratum": "H2", "psu": "P4", "w": 0.9, "i0": 0, "i1": 1, "i2": 1, "i3": 0},
        {"stratum": "H2", "psu": "P4", "w": 1.4, "i0": 0, "i1": 0, "i2": 1, "i3": 1},
        # Stratum 3: Lonely PSU (P5)
        {"stratum": "H3", "psu": "P5", "w": 1.0, "i0": 1, "i1": 1, "i2": 1, "i3": 0},
        {"stratum": "H3", "psu": "P5", "w": 1.2, "i0": 1, "i1": 0, "i2": 0, "i3": 1},
    ]
    return pl.DataFrame(rows)


def generate_domains(seed: int = DEFAULT_SEED) -> pl.DataFrame:
    """Generate Stratified Cluster sample with domains crossing strata and small domains."""
    rows = [
        # Stratum 1
        {
            "stratum": "S1",
            "psu": "P1",
            "w": 1.0,
            "region": "North",
            "group": "G1",
            "i0": 1,
            "i1": 1,
            "i2": 0,
            "i3": 1,
        },
        {
            "stratum": "S1",
            "psu": "P1",
            "w": 1.2,
            "region": "North",
            "group": "G1",
            "i0": 0,
            "i1": 1,
            "i2": 1,
            "i3": 0,
        },
        {
            "stratum": "S1",
            "psu": "P2",
            "w": 0.8,
            "region": "South",
            "group": "G1",
            "i0": 1,
            "i1": 0,
            "i2": 1,
            "i3": 0,
        },
        {
            "stratum": "S1",
            "psu": "P2",
            "w": 1.1,
            "region": "South",
            "group": "G2",
            "i0": 1,
            "i1": 1,
            "i2": 0,
            "i3": 1,
        },
        # Stratum 2
        {
            "stratum": "S2",
            "psu": "P3",
            "w": 0.9,
            "region": "North",
            "group": "G1",
            "i0": 0,
            "i1": 0,
            "i2": 1,
            "i3": 0,
        },
        {
            "stratum": "S2",
            "psu": "P3",
            "w": 1.3,
            "region": "North",
            "group": "G2",
            "i0": 1,
            "i1": 0,
            "i2": 0,
            "i3": 1,
        },
        {
            "stratum": "S2",
            "psu": "P4",
            "w": 1.0,
            "region": "North",
            "group": "G2",
            "i0": 1,
            "i1": 1,
            "i2": 0,
            "i3": 0,
        },
        {
            "stratum": "S2",
            "psu": "P4",
            "w": 1.4,
            "region": "North",
            "group": "G2",
            "i0": 0,
            "i1": 1,
            "i2": 1,
            "i3": 0,
        },
        # Stratum 3
        {
            "stratum": "S3",
            "psu": "P5",
            "w": 0.7,
            "region": "South",
            "group": "G1",
            "i0": 1,
            "i1": 0,
            "i2": 1,
            "i3": 1,
        },
        {
            "stratum": "S3",
            "psu": "P5",
            "w": 1.2,
            "region": "South",
            "group": "G2",
            "i0": 0,
            "i1": 1,
            "i2": 0,
            "i3": 1,
        },
        {
            "stratum": "S3",
            "psu": "P6",
            "w": 1.1,
            "region": "North",
            "group": "G1",
            "i0": 1,
            "i1": 1,
            "i2": 0,
            "i3": 0,
        },
        {
            "stratum": "S3",
            "psu": "P6",
            "w": 0.9,
            "region": "North",
            "group": "G3",
            "i0": 1,
            "i1": 0,
            "i2": 1,
            "i3": 0,
        },
    ]
    return pl.DataFrame(rows)


def generate_af_limits(seed: int = DEFAULT_SEED) -> dict[str, pl.DataFrame]:
    """Generate datasets for boundary conditions of Alkire-Foster
    (zero poor, all poor, mixed).
    """
    rows_zero = [
        {"stratum": "S1", "psu": "P1", "w": 1.0, "i0": 0, "i1": 0, "i2": 0, "i3": 0},
        {"stratum": "S1", "psu": "P1", "w": 1.2, "i0": 0, "i1": 0, "i2": 0, "i3": 0},
        {"stratum": "S1", "psu": "P2", "w": 0.8, "i0": 0, "i1": 0, "i2": 0, "i3": 0},
        {"stratum": "S1", "psu": "P2", "w": 1.1, "i0": 0, "i1": 0, "i2": 0, "i3": 0},
        {"stratum": "S2", "psu": "P3", "w": 0.9, "i0": 0, "i1": 0, "i2": 0, "i3": 0},
        {"stratum": "S2", "psu": "P3", "w": 1.3, "i0": 0, "i1": 0, "i2": 0, "i3": 0},
        {"stratum": "S2", "psu": "P4", "w": 1.0, "i0": 0, "i1": 0, "i2": 0, "i3": 0},
        {"stratum": "S2", "psu": "P4", "w": 1.4, "i0": 0, "i1": 0, "i2": 0, "i3": 0},
    ]
    rows_all = [
        {"stratum": "S1", "psu": "P1", "w": 1.0, "i0": 1, "i1": 1, "i2": 1, "i3": 1},
        {"stratum": "S1", "psu": "P1", "w": 1.2, "i0": 1, "i1": 1, "i2": 1, "i3": 1},
        {"stratum": "S1", "psu": "P2", "w": 0.8, "i0": 1, "i1": 1, "i2": 1, "i3": 1},
        {"stratum": "S1", "psu": "P2", "w": 1.1, "i0": 1, "i1": 1, "i2": 1, "i3": 1},
        {"stratum": "S2", "psu": "P3", "w": 0.9, "i0": 1, "i1": 1, "i2": 1, "i3": 1},
        {"stratum": "S2", "psu": "P3", "w": 1.3, "i0": 1, "i1": 1, "i2": 1, "i3": 1},
        {"stratum": "S2", "psu": "P4", "w": 1.0, "i0": 1, "i1": 1, "i2": 1, "i3": 1},
        {"stratum": "S2", "psu": "P4", "w": 1.4, "i0": 1, "i1": 1, "i2": 1, "i3": 1},
    ]
    rows_mixed = [
        {"stratum": "S1", "psu": "P1", "w": 1.0, "i0": 1, "i1": 1, "i2": 1, "i3": 1},
        {"stratum": "S1", "psu": "P1", "w": 1.2, "i0": 0, "i1": 1, "i2": 1, "i3": 0},
        {"stratum": "S1", "psu": "P2", "w": 0.8, "i0": 1, "i1": 0, "i2": 0, "i3": 0},
        {"stratum": "S1", "psu": "P2", "w": 1.1, "i0": 0, "i1": 0, "i2": 0, "i3": 0},
        {"stratum": "S2", "psu": "P3", "w": 0.9, "i0": 1, "i1": 1, "i2": 0, "i3": 1},
        {"stratum": "S2", "psu": "P3", "w": 1.3, "i0": 0, "i1": 1, "i2": 0, "i3": 0},
        {"stratum": "S2", "psu": "P4", "w": 1.0, "i0": 1, "i1": 1, "i2": 1, "i3": 1},
        {"stratum": "S2", "psu": "P4", "w": 1.4, "i0": 0, "i1": 0, "i2": 1, "i3": 0},
    ]
    return {
        "zero_poor": pl.DataFrame(rows_zero),
        "all_poor": pl.DataFrame(rows_all),
        "mixed": pl.DataFrame(rows_mixed),
    }


def generate_data_limits(seed: int = DEFAULT_SEED) -> dict[str, pl.DataFrame]:
    """Generate datasets for data limits (extreme weights 1:10^6 and missing values)."""
    rows_weights = [
        {"stratum": "S1", "psu": "P1", "w": 1.0, "i0": 1, "i1": 1, "i2": 0, "i3": 1},
        {"stratum": "S1", "psu": "P1", "w": 1000000.0, "i0": 0, "i1": 1, "i2": 1, "i3": 0},
        {"stratum": "S1", "psu": "P2", "w": 1.0, "i0": 1, "i1": 0, "i2": 1, "i3": 0},
        {"stratum": "S1", "psu": "P2", "w": 500000.0, "i0": 1, "i1": 1, "i2": 0, "i3": 1},
        {"stratum": "S2", "psu": "P3", "w": 2.0, "i0": 0, "i1": 0, "i2": 1, "i3": 0},
        {"stratum": "S2", "psu": "P3", "w": 800000.0, "i0": 1, "i1": 0, "i2": 0, "i3": 1},
        {"stratum": "S2", "psu": "P4", "w": 1.0, "i0": 1, "i1": 1, "i2": 0, "i3": 0},
        {"stratum": "S2", "psu": "P4", "w": 1000000.0, "i0": 0, "i1": 1, "i2": 1, "i3": 0},
    ]
    rows_missing = [
        # Stratum S1, PSU P1
        {"stratum": "S1", "psu": "P1", "w": 1.0, "i0": 1, "i1": 1, "i2": 0, "i3": 1},
        {"stratum": "S1", "psu": "P1", "w": 1.2, "i0": None, "i1": 1, "i2": 1, "i3": 0},
        {"stratum": "S1", "psu": "P1", "w": 0.9, "i0": 1, "i1": 0, "i2": 1, "i3": 1},
        # Stratum S1, PSU P2
        {"stratum": "S1", "psu": "P2", "w": 0.8, "i0": 1, "i1": None, "i2": 1, "i3": 0},
        {"stratum": "S1", "psu": "P2", "w": 1.1, "i0": 1, "i1": 1, "i2": 0, "i3": None},
        {"stratum": "S1", "psu": "P2", "w": 1.0, "i0": 0, "i1": 1, "i2": 0, "i3": 1},
        # Stratum S2, PSU P3
        {"stratum": "S2", "psu": "P3", "w": 0.9, "i0": 0, "i1": 0, "i2": 1, "i3": 0},
        {
            "stratum": "S2",
            "psu": "P3",
            "w": 1.3,
            "i0": None,
            "i1": None,
            "i2": None,
            "i3": None,
        },
        {"stratum": "S2", "psu": "P3", "w": 1.1, "i0": 1, "i1": 0, "i2": 0, "i3": 1},
        # Stratum S2, PSU P4
        {"stratum": "S2", "psu": "P4", "w": 1.0, "i0": 1, "i1": 1, "i2": 1, "i3": 0},
        {"stratum": "S2", "psu": "P4", "w": 1.4, "i0": 0, "i1": 1, "i2": None, "i3": 0},
        {"stratum": "S2", "psu": "P4", "w": 0.8, "i0": 0, "i1": 0, "i2": 1, "i3": 1},
    ]
    return {
        "extreme_weights": pl.DataFrame(rows_weights),
        "missing_values": pl.DataFrame(rows_missing),
    }


def generate_replication(seed: int = DEFAULT_SEED) -> pl.DataFrame:
    """Generate Stratified Cluster sample for replicate weights (2 strata, 2 PSUs each)."""
    rows = [
        # Stratum S1: PSUs P1, P2 (3 obs each)
        {"id": 1, "stratum": "S1", "psu": "P1", "w": 1.0, "i0": 1, "i1": 1, "i2": 0, "i3": 1},
        {"id": 2, "stratum": "S1", "psu": "P1", "w": 1.2, "i0": 0, "i1": 1, "i2": 1, "i3": 0},
        {"id": 3, "stratum": "S1", "psu": "P1", "w": 0.8, "i0": 1, "i1": 0, "i2": 1, "i3": 0},
        {"id": 4, "stratum": "S1", "psu": "P2", "w": 1.1, "i0": 1, "i1": 1, "i2": 0, "i3": 1},
        {"id": 5, "stratum": "S1", "psu": "P2", "w": 0.9, "i0": 0, "i1": 0, "i2": 1, "i3": 0},
        {"id": 6, "stratum": "S1", "psu": "P2", "w": 1.3, "i0": 1, "i1": 0, "i2": 0, "i3": 1},
        # Stratum S2: PSUs P3, P4 (3 obs each)
        {"id": 7, "stratum": "S2", "psu": "P3", "w": 1.0, "i0": 1, "i1": 1, "i2": 0, "i3": 0},
        {"id": 8, "stratum": "S2", "psu": "P3", "w": 1.4, "i0": 0, "i1": 1, "i2": 1, "i3": 0},
        {"id": 9, "stratum": "S2", "psu": "P3", "w": 0.7, "i0": 1, "i1": 0, "i2": 1, "i3": 1},
        {"id": 10, "stratum": "S2", "psu": "P4", "w": 1.2, "i0": 0, "i1": 1, "i2": 0, "i3": 1},
        {"id": 11, "stratum": "S2", "psu": "P4", "w": 1.1, "i0": 1, "i1": 1, "i2": 0, "i3": 0},
        {"id": 12, "stratum": "S2", "psu": "P4", "w": 0.9, "i0": 1, "i1": 0, "i2": 1, "i3": 0},
    ]
    return pl.DataFrame(rows)


def generate_overlap(seed: int = DEFAULT_SEED) -> dict[str, pl.DataFrame]:
    """Generate panel and overlapping samples."""
    # Perfect panel (4 households across 2 waves)
    rows_perf_t0 = [
        {
            "wave": "t0",
            "stratum": "s1",
            "cluster": "c1",
            "hhid": "h1",
            "i0": 1,
            "i1": 1,
            "w": 1.0,
        },
        {
            "wave": "t0",
            "stratum": "s1",
            "cluster": "c1",
            "hhid": "h2",
            "i0": 1,
            "i1": 0,
            "w": 1.0,
        },
        {
            "wave": "t0",
            "stratum": "s1",
            "cluster": "c2",
            "hhid": "h3",
            "i0": 0,
            "i1": 0,
            "w": 1.0,
        },
        {
            "wave": "t0",
            "stratum": "s1",
            "cluster": "c2",
            "hhid": "h4",
            "i0": 0,
            "i1": 1,
            "w": 1.0,
        },
    ]
    rows_perf_t1 = [
        {
            "wave": "t1",
            "stratum": "s1",
            "cluster": "c1",
            "hhid": "h1",
            "i0": 1,
            "i1": 1,
            "w": 1.0,
        },
        {
            "wave": "t1",
            "stratum": "s1",
            "cluster": "c1",
            "hhid": "h2",
            "i0": 1,
            "i1": 1,
            "w": 1.0,
        },
        {
            "wave": "t1",
            "stratum": "s1",
            "cluster": "c2",
            "hhid": "h3",
            "i0": 0,
            "i1": 0,
            "w": 1.0,
        },
        {
            "wave": "t1",
            "stratum": "s1",
            "cluster": "c2",
            "hhid": "h4",
            "i0": 0,
            "i1": 0,
            "w": 1.0,
        },
    ]
    df_perf = pl.DataFrame(rows_perf_t0 + rows_perf_t1)

    # Partial overlap panel (7 households across 2 waves)
    rows_part_t0 = [
        {
            "wave": "t0",
            "stratum": "S1",
            "cluster": "P1",
            "hhid": "h1",
            "i0": 1,
            "i1": 1,
            "w": 1.2,
        },
        {
            "wave": "t0",
            "stratum": "S1",
            "cluster": "P1",
            "hhid": "h2",
            "i0": 0,
            "i1": 1,
            "w": 0.8,
        },
        {
            "wave": "t0",
            "stratum": "S1",
            "cluster": "P2",
            "hhid": "h3",
            "i0": 1,
            "i1": 0,
            "w": 1.0,
        },
        {
            "wave": "t0",
            "stratum": "S2",
            "cluster": "P3",
            "hhid": "h5",
            "i0": 0,
            "i1": 0,
            "w": 1.1,
        },
        {
            "wave": "t0",
            "stratum": "S2",
            "cluster": "P4",
            "hhid": "h6",
            "i0": 1,
            "i1": 1,
            "w": 0.9,
        },
    ]
    rows_part_t1 = [
        {
            "wave": "t1",
            "stratum": "S1",
            "cluster": "P1",
            "hhid": "h1",
            "i0": 1,
            "i1": 0,
            "w": 1.2,
        },
        {
            "wave": "t1",
            "stratum": "S1",
            "cluster": "P1",
            "hhid": "h2",
            "i0": 1,
            "i1": 1,
            "w": 0.8,
        },
        {
            "wave": "t1",
            "stratum": "S1",
            "cluster": "P2",
            "hhid": "h4",
            "i0": 0,
            "i1": 1,
            "w": 1.0,
        },
        {
            "wave": "t1",
            "stratum": "S2",
            "cluster": "P3",
            "hhid": "h5",
            "i0": 0,
            "i1": 1,
            "w": 1.1,
        },
        {
            "wave": "t1",
            "stratum": "S2",
            "cluster": "P4",
            "hhid": "h7",
            "i0": 0,
            "i1": 0,
            "w": 0.9,
        },
    ]
    df_part = pl.DataFrame(rows_part_t0 + rows_part_t1)

    return {
        "perfect_panel": df_perf,
        "partial_panel": df_part,
    }


def export_all_conformity_data(output_dir: str | Path) -> None:
    """Export all datasets to CSV for R reference scripts."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    generate_srs().write_csv(out_path / "data_srs.csv")
    generate_stratified_srs().write_csv(out_path / "data_stratified_srs.csv")
    generate_cluster_1stage().write_csv(out_path / "data_cluster_1stage.csv")
    generate_stratified_cluster().write_csv(out_path / "data_stratified_cluster.csv")

    df_ms_fpc, df_ms_census = generate_multistage()
    df_ms_fpc.write_csv(out_path / "data_multistage_fpc.csv")
    df_ms_census.write_csv(out_path / "data_multistage_census.csv")

    df_pps, df_joint = generate_pps()
    df_pps.write_csv(out_path / "data_pps.csv")
    df_joint.write_csv(out_path / "data_pps_joint.csv")

    generate_lonely_psu().write_csv(out_path / "data_lonely_psu.csv")
    generate_domains().write_csv(out_path / "data_domains.csv")

    af_lims = generate_af_limits()
    af_lims["zero_poor"].write_csv(out_path / "data_af_zero_poor.csv")
    af_lims["all_poor"].write_csv(out_path / "data_af_all_poor.csv")
    af_lims["mixed"].write_csv(out_path / "data_af_mixed.csv")

    data_lims = generate_data_limits()
    data_lims["extreme_weights"].write_csv(out_path / "data_extreme_weights.csv")
    data_lims["missing_values"].write_csv(out_path / "data_missing_values.csv")

    # Replicate designs export
    import json

    from afmpi import ReplicateDesign, Specification, estimate
    from afmpi.replicate_estimation import generate_replicate_weights

    df_rep = generate_replication()
    df_rep = (
        df_rep.with_columns(
            (0.25 * (pl.col("i0") + pl.col("i1") + pl.col("i2") + pl.col("i3"))).alias("c")
        )
        .with_columns((pl.col("c") >= 1 / 3).cast(pl.Float64).alias("poor"))
        .with_columns((pl.col("c") * pl.col("poor")).alias("ck"))
    )

    spec_rep = Specification({"d": ["i0", "i1", "i2", "i3"]})
    rep_methods = [
        ("JK1", ReplicateDesign(weights="w", psu="psu", method="JK1")),
        ("JKn", ReplicateDesign(weights="w", strata="stratum", psu="psu", method="JKn")),
        ("BRR", ReplicateDesign(weights="w", strata="stratum", psu="psu", method="BRR")),
        (
            "Fay_BRR",
            ReplicateDesign(
                weights="w", strata="stratum", psu="psu", method="Fay_BRR", fay=0.5
            ),
        ),
        (
            "bootstrap",
            ReplicateDesign(
                weights="w",
                strata="stratum",
                psu="psu",
                method="bootstrap",
                seed=42,
                replicates=20,
            ),
        ),
        ("SDR", ReplicateDesign(weights="w", strata="stratum", psu="psu", method="SDR")),
    ]
    rep_meta = {}
    for name, des in rep_methods:
        df_out, rep_cols, scale, rscales = generate_replicate_weights(df_rep, des)
        res = estimate(df_rep, spec_rep, des, k=1 / 3)
        se_df = res.se()
        h_se = se_df.filter(pl.col("measure") == "H")["se"].item()
        m0_se = se_df.filter(pl.col("measure") == "M0")["se"].item()
        a_se = se_df.filter(pl.col("measure") == "A")["se"].item()

        df_out.write_csv(out_path / f"data_rep_{name.lower()}.csv")
        rep_meta[name] = {
            "scale": scale,
            "rscales": list(rscales),
            "rep_cols": list(rep_cols),
            "H": res.H,
            "H_se": h_se,
            "M0": res.M0,
            "M0_se": m0_se,
            "A": res.A,
            "A_se": a_se,
            "df": des.degf if des.degf is not None else 2,
        }

    with open(out_path / "replication_meta.json", "w") as f:
        json.dump(rep_meta, f, indent=2)

    generate_replication().write_csv(out_path / "data_replication.csv")

    overlaps = generate_overlap()
    overlaps["perfect_panel"].write_csv(out_path / "data_perfect_panel.csv")
    overlaps["partial_panel"].write_csv(out_path / "data_partial_panel.csv")


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
    ref_data_dir = Path(__file__).resolve().parents[2] / "tools" / "reference" / "data"
    export_all_conformity_data(ref_data_dir)
    print(f"Exported all conformity datasets to {ref_data_dir}")
