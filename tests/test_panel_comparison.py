"""Oracle comparison tests for panel and overlapping samples (PLAN.md §18).

Validates numerical equivalence against values from tests/oracle/panel_oracle.R
and tests/oracle/panel_meta.json using R 'survey' package.
"""

import json
from pathlib import Path

import polars as pl
import pytest

from afmpi import Specification, SurveyDesign, estimate

ORACLE_DIR = Path(__file__).resolve().parent / "oracle"


def test_perfect_panel_comparison_against_r_oracle():
    """Compare 2-wave perfect panel change against R survey oracle."""
    meta_path = ORACLE_DIR / "panel_meta.json"
    assert meta_path.exists(), f"Oracle metadata {meta_path} missing"

    with open(meta_path) as f:
        meta = json.load(f)

    data_path = ORACLE_DIR / "data_panel_perfect.csv"
    if data_path.exists():
        df_perf = pl.read_csv(data_path)
    else:
        cols = ["wave", "stratum", "cluster", "hhid", "d1", "d2", "w"]
        rows_t0 = [
            dict(zip(cols, vals, strict=True))
            for vals in [
                ("t0", "s1", "c1", "h1", 1, 1, 1.0),
                ("t0", "s1", "c1", "h2", 1, 0, 1.0),
                ("t0", "s1", "c2", "h3", 0, 0, 1.0),
                ("t0", "s1", "c2", "h4", 0, 1, 1.0),
            ]
        ]
        rows_t1 = [
            dict(zip(cols, vals, strict=True))
            for vals in [
                ("t1", "s1", "c1", "h1", 1, 1, 1.0),
                ("t1", "s1", "c1", "h2", 1, 1, 1.0),
                ("t1", "s1", "c2", "h3", 0, 0, 1.0),
                ("t1", "s1", "c2", "h4", 0, 0, 1.0),
            ]
        ]
        df_perf = pl.DataFrame(rows_t0 + rows_t1)

    spec = Specification(dimensions={"d1": ("d1",), "d2": ("d2",)})
    design = SurveyDesign(strata="stratum", psu="cluster", weights="w")

    res_perf = estimate(df_perf, spec, design, tvar="wave", panel_id="hhid", overlap="auto")
    ch_perf = res_perf.changes()

    h_abs_perf = ch_perf.filter((pl.col("measure") == "H") & (pl.col("type") == "abs"))
    se_h = h_abs_perf.select("se").item()
    est_h = h_abs_perf.select("est").item()

    oracle_perf = meta["perfect"]
    assert est_h == pytest.approx(oracle_perf["est_H_diff"], abs=1e-12)
    assert se_h == pytest.approx(oracle_perf["se_H_diff"], abs=1e-10)


def test_partial_overlap_panel_comparison_against_r_oracle():
    """Compare partial overlap panel change against R survey oracle."""
    meta_path = ORACLE_DIR / "panel_meta.json"
    assert meta_path.exists(), f"Oracle metadata {meta_path} missing"

    with open(meta_path) as f:
        meta = json.load(f)

    data_path = ORACLE_DIR / "data_panel_partial.csv"
    if data_path.exists():
        df_part = pl.read_csv(data_path)
    else:
        cols = ["wave", "stratum", "cluster", "hhid", "d1", "d2", "w"]
        rows_part_t0 = [
            dict(zip(cols, vals, strict=True))
            for vals in [
                ("t0", "S1", "P1", "h1", 1, 1, 1.2),
                ("t0", "S1", "P1", "h2", 0, 1, 0.8),
                ("t0", "S1", "P2", "h3", 1, 0, 1.0),
                ("t0", "S2", "P3", "h5", 0, 0, 1.1),
                ("t0", "S2", "P4", "h6", 1, 1, 0.9),
            ]
        ]
        rows_part_t1 = [
            dict(zip(cols, vals, strict=True))
            for vals in [
                ("t1", "S1", "P1", "h1", 1, 0, 1.2),
                ("t1", "S1", "P1", "h2", 1, 1, 0.8),
                ("t1", "S1", "P2", "h4", 0, 1, 1.0),
                ("t1", "S2", "P3", "h5", 0, 1, 1.1),
                ("t1", "S2", "P4", "h7", 0, 0, 0.9),
            ]
        ]
        df_part = pl.DataFrame(rows_part_t0 + rows_part_t1)

    spec = Specification(dimensions={"d1": ("d1",), "d2": ("d2",)})
    design = SurveyDesign(strata="stratum", psu="cluster", weights="w")

    res_part = estimate(df_part, spec, design, tvar="wave", panel_id="hhid", overlap="auto")
    ch_part = res_part.changes()

    h_abs_part = ch_part.filter((pl.col("measure") == "H") & (pl.col("type") == "abs"))
    se_h = h_abs_part.select("se").item()
    est_h = h_abs_part.select("est").item()

    oracle_part = meta["partial"]
    assert est_h == pytest.approx(oracle_part["est_H_diff"], abs=1e-12)
    assert se_h == pytest.approx(oracle_part["se_H_diff"], abs=1e-10)
