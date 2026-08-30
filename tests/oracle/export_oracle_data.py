"""Generate and export CSV datasets and metadata for R oracle validation scripts (Phases 5-7).

Execution:
    python tests/oracle/export_oracle_data.py
"""

import json
import os
import sys
from pathlib import Path

# Ensure afmpi package in src/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import polars as pl
from afmpi import Specification, ReplicateDesign, SurveyDesign, estimate
from afmpi.replicate_estimation import generate_replicate_weights

ORACLE_DIR = Path(__file__).resolve().parent

def export_replicate_data():
    rows = []
    # Stratum S1: PSUs P1, P2 (3 obs each)
    rows.append({"id": 1,  "stratum": "S1", "psu": "P1", "w": 1.0, "i0": 1, "i1": 1, "i2": 0, "i3": 1})
    rows.append({"id": 2,  "stratum": "S1", "psu": "P1", "w": 1.2, "i0": 0, "i1": 1, "i2": 1, "i3": 0})
    rows.append({"id": 3,  "stratum": "S1", "psu": "P1", "w": 0.8, "i0": 1, "i1": 0, "i2": 1, "i3": 0})
    rows.append({"id": 4,  "stratum": "S1", "psu": "P2", "w": 1.1, "i0": 1, "i1": 1, "i2": 0, "i3": 1})
    rows.append({"id": 5,  "stratum": "S1", "psu": "P2", "w": 0.9, "i0": 0, "i1": 0, "i2": 1, "i3": 0})
    rows.append({"id": 6,  "stratum": "S1", "psu": "P2", "w": 1.3, "i0": 1, "i1": 0, "i2": 0, "i3": 1})

    # Stratum S2: PSUs P3, P4 (3 obs each)
    rows.append({"id": 7,  "stratum": "S2", "psu": "P3", "w": 1.0, "i0": 1, "i1": 1, "i2": 0, "i3": 0})
    rows.append({"id": 8,  "stratum": "S2", "psu": "P3", "w": 1.4, "i0": 0, "i1": 1, "i2": 1, "i3": 0})
    rows.append({"id": 9,  "stratum": "S2", "psu": "P3", "w": 0.7, "i0": 1, "i1": 0, "i2": 1, "i3": 1})
    rows.append({"id": 10, "stratum": "S2", "psu": "P4", "w": 1.2, "i0": 0, "i1": 1, "i2": 0, "i3": 1})
    rows.append({"id": 11, "stratum": "S2", "psu": "P4", "w": 1.1, "i0": 1, "i1": 1, "i2": 0, "i3": 0})
    rows.append({"id": 12, "stratum": "S2", "psu": "P4", "w": 0.9, "i0": 1, "i1": 0, "i2": 1, "i3": 0})

    df = pl.DataFrame(rows)
    df = df.with_columns(
        (0.25 * (pl.col("i0") + pl.col("i1") + pl.col("i2") + pl.col("i3"))).alias("c")
    ).with_columns(
        (pl.col("c") >= 1/3).cast(pl.Float64).alias("poor")
    ).with_columns(
        (pl.col("c") * pl.col("poor")).alias("ck")
    )

    spec = Specification(dimensions={"d0": ("i0",), "d1": ("i1",), "d2": ("i2",), "d3": ("i3",)})

    methods = [
        ("JK1", ReplicateDesign(weights="w", psu="psu", method="JK1")),
        ("JKn", ReplicateDesign(weights="w", strata="stratum", psu="psu", method="JKn")),
        ("BRR", ReplicateDesign(weights="w", strata="stratum", psu="psu", method="BRR")),
        ("Fay_BRR", ReplicateDesign(weights="w", strata="stratum", psu="psu", method="Fay_BRR", fay=0.5)),
        ("bootstrap", ReplicateDesign(weights="w", strata="stratum", psu="psu", method="bootstrap", seed=42, replicates=20)),
        ("SDR", ReplicateDesign(weights="w", strata="stratum", psu="psu", method="SDR")),
    ]

    meta = {}
    for name, des in methods:
        df_out, rep_cols, scale, rscales = generate_replicate_weights(df, des)
        res = estimate(df, spec, des, k=1/3)
        se_df = res.se()
        h_se = se_df.filter(pl.col("measure") == "H")["se"].item()
        m0_se = se_df.filter(pl.col("measure") == "M0")["se"].item()
        a_se = se_df.filter(pl.col("measure") == "A")["se"].item()

        csv_path = ORACLE_DIR / f"data_{name.lower()}.csv"
        df_out.write_csv(csv_path)

        meta[name] = {
            "scale": scale,
            "rscales": list(rscales),
            "rep_cols": list(rep_cols),
            "H": res.H,
            "H_se": h_se,
            "M0": res.M0,
            "M0_se": m0_se,
            "A": res.A,
            "A_se": a_se,
        }

    with open(ORACLE_DIR / "replicate_meta.json", "w") as f:
        json.dump(meta, f, indent=2)

def export_panel_data():
    spec = Specification(dimensions={"d1": ("d1",), "d2": ("d2",)})
    design = SurveyDesign(strata="stratum", psu="cluster", weights="w")

    # 1. Perfect panel
    rows_t0 = [
        {"wave": "t0", "stratum": "s1", "cluster": "c1", "hhid": "h1", "d1": 1, "d2": 1, "w": 1.0},
        {"wave": "t0", "stratum": "s1", "cluster": "c1", "hhid": "h2", "d1": 1, "d2": 0, "w": 1.0},
        {"wave": "t0", "stratum": "s1", "cluster": "c2", "hhid": "h3", "d1": 0, "d2": 0, "w": 1.0},
        {"wave": "t0", "stratum": "s1", "cluster": "c2", "hhid": "h4", "d1": 0, "d2": 1, "w": 1.0},
    ]
    rows_t1 = [
        {"wave": "t1", "stratum": "s1", "cluster": "c1", "hhid": "h1", "d1": 1, "d2": 1, "w": 1.0},
        {"wave": "t1", "stratum": "s1", "cluster": "c1", "hhid": "h2", "d1": 1, "d2": 1, "w": 1.0},
        {"wave": "t1", "stratum": "s1", "cluster": "c2", "hhid": "h3", "d1": 0, "d2": 0, "w": 1.0},
        {"wave": "t1", "stratum": "s1", "cluster": "c2", "hhid": "h4", "d1": 0, "d2": 0, "w": 1.0},
    ]
    df_perf = pl.DataFrame(rows_t0 + rows_t1)
    res_perf = estimate(df_perf, spec, design, tvar="wave", panel_id="hhid", overlap="auto")
    ch_perf = res_perf.changes()
    h_abs_perf = ch_perf.filter((pl.col("measure") == "H") & (pl.col("type") == "abs"))
    se_h_perf = h_abs_perf.select("se").item()
    est_h_perf = h_abs_perf.select("est").item()

    df_perf_calc = df_perf.with_columns(
        (0.5 * (pl.col("d1") + pl.col("d2"))).alias("c")
    ).with_columns(
        (pl.col("c") >= 0.5).cast(pl.Float64).alias("poor")
    ).with_columns(
        (pl.col("c") * pl.col("poor")).alias("ck")
    )
    df_perf_calc.write_csv(ORACLE_DIR / "data_panel_perfect.csv")

    # 2. Partial overlap panel
    rows_part_t0 = [
        {"wave": "t0", "stratum": "S1", "cluster": "P1", "hhid": "h1", "d1": 1, "d2": 1, "w": 1.2},
        {"wave": "t0", "stratum": "S1", "cluster": "P1", "hhid": "h2", "d1": 0, "d2": 1, "w": 0.8},
        {"wave": "t0", "stratum": "S1", "cluster": "P2", "hhid": "h3", "d1": 1, "d2": 0, "w": 1.0},
        {"wave": "t0", "stratum": "S2", "cluster": "P3", "hhid": "h5", "d1": 0, "d2": 0, "w": 1.1},
        {"wave": "t0", "stratum": "S2", "cluster": "P4", "hhid": "h6", "d1": 1, "d2": 1, "w": 0.9},
    ]
    rows_part_t1 = [
        {"wave": "t1", "stratum": "S1", "cluster": "P1", "hhid": "h1", "d1": 1, "d2": 0, "w": 1.2},
        {"wave": "t1", "stratum": "S1", "cluster": "P1", "hhid": "h2", "d1": 1, "d2": 1, "w": 0.8},
        {"wave": "t1", "stratum": "S1", "cluster": "P2", "hhid": "h4", "d1": 0, "d2": 1, "w": 1.0},
        {"wave": "t1", "stratum": "S2", "cluster": "P3", "hhid": "h5", "d1": 0, "d2": 1, "w": 1.1},
        {"wave": "t1", "stratum": "S2", "cluster": "P4", "hhid": "h7", "d1": 0, "d2": 0, "w": 0.9},
    ]
    df_part = pl.DataFrame(rows_part_t0 + rows_part_t1)
    res_part = estimate(df_part, spec, design, tvar="wave", panel_id="hhid", overlap="auto")
    ch_part = res_part.changes()
    h_abs_part = ch_part.filter((pl.col("measure") == "H") & (pl.col("type") == "abs"))
    se_h_part = h_abs_part.select("se").item()
    est_h_part = h_abs_part.select("est").item()

    df_part_calc = df_part.with_columns(
        (0.5 * (pl.col("d1") + pl.col("d2"))).alias("c")
    ).with_columns(
        (pl.col("c") >= 0.5).cast(pl.Float64).alias("poor")
    ).with_columns(
        (pl.col("c") * pl.col("poor")).alias("ck")
    )
    df_part_calc.write_csv(ORACLE_DIR / "data_panel_partial.csv")

    meta = {
        "perfect": {"est_H_diff": est_h_perf, "se_H_diff": se_h_perf, "var_H_diff": se_h_perf**2},
        "partial": {"est_H_diff": est_h_part, "se_H_diff": se_h_part, "var_H_diff": se_h_part**2},
    }
    with open(ORACLE_DIR / "panel_meta.json", "w") as f:
        json.dump(meta, f, indent=2)

def export_vcov_wald_data():
    rows = [
        {"stratum": "1", "psu": "101", "weight": 1.0, "group": "A", "i1": 1, "i2": 1},
        {"stratum": "1", "psu": "101", "weight": 1.0, "group": "A", "i1": 1, "i2": 1},
        {"stratum": "1", "psu": "102", "weight": 1.0, "group": "B", "i1": 1, "i2": 1},
        {"stratum": "1", "psu": "102", "weight": 1.0, "group": "B", "i1": 1, "i2": 0},
        {"stratum": "2", "psu": "201", "weight": 1.0, "group": "A", "i1": 1, "i2": 0},
        {"stratum": "2", "psu": "201", "weight": 1.0, "group": "A", "i1": 0, "i2": 0},
        {"stratum": "2", "psu": "202", "weight": 1.0, "group": "B", "i1": 0, "i2": 0},
        {"stratum": "2", "psu": "202", "weight": 1.0, "group": "B", "i1": 0, "i2": 0},
    ]
    df = pl.DataFrame(rows)
    df = df.with_columns(
        (0.5 * (pl.col("i1") + pl.col("i2"))).alias("c")
    ).with_columns(
        (pl.col("c") >= 0.5).cast(pl.Float64).alias("poor")
    ).with_columns(
        (pl.col("c") * pl.col("poor")).alias("ck")
    )
    spec = Specification(dimensions={"d1": ("i1", "i2")})
    design = SurveyDesign(strata="stratum", psu="psu", weights="weight")

    res = estimate(df, spec, design, k=0.5, over="group")
    test_res = res.test(("group", "A"), ("group", "B"), measure="M0", dist="F")

    vcov_A = res.vcov(over="group", subgroup="A", measures=("H", "A", "M0"))
    vcov_B = res.vcov(over="group", subgroup="B", measures=("H", "A", "M0"))

    df.write_csv(ORACLE_DIR / "data_vcov_wald.csv")

    meta = {
        "test": {
            "estimate": test_res.estimate,
            "se": test_res.se,
            "statistic": test_res.statistic,
            "df1": test_res.df1,
            "df2": test_res.df2,
            "p_value": test_res.p_value,
        },
        "vcov_A": vcov_A.to_dicts(),
        "vcov_B": vcov_B.to_dicts(),
    }
    with open(ORACLE_DIR / "vcov_wald_meta.json", "w") as f:
        json.dump(meta, f, indent=2)

def main():
    export_replicate_data()
    export_panel_data()
    export_vcov_wald_data()
    print("All oracle datasets and metadata exported successfully.")

if __name__ == "__main__":
    main()
