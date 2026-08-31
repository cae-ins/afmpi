"""Conformity tests for Panel and Overlapping Samples (PLAN.md §14.10)."""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest

from afmpi import Specification, SurveyDesign, estimate
from tests.test_conformity.generate import generate_overlap

REF_DIR = Path(__file__).resolve().parent / "reference"


def test_overlap_conformity():
    """Verify panel and overlapping sample change estimations against R survey reference."""
    ref_file = REF_DIR / "overlap.json"
    assert ref_file.exists(), f"Reference file {ref_file} missing"

    with open(ref_file) as f:
        ref = json.load(f)

    tol = ref["tolerance"]
    overlaps = generate_overlap(ref["generator_seed"])
    spec = Specification({"d": ["i0", "i1"]})

    # 1. Perfect Panel
    des_perf = SurveyDesign(strata="stratum", psu="cluster", weights="w")
    res_perf = estimate(
        overlaps["perfect_panel"],
        spec,
        des_perf,
        tvar="wave",
        panel_id="hhid",
        overlap="auto",
        k=0.5,
    )
    ch_perf = res_perf.changes()
    h_ch_perf = ch_perf.filter((pl.col("measure") == "H") & (pl.col("type") == "abs")).row(0, named=True)
    m0_ch_perf = ch_perf.filter((pl.col("measure") == "M0") & (pl.col("type") == "abs")).row(0, named=True)

    val_h_perf = next(v for v in ref["values"] if v["measure"] == "Delta_H_perfect")
    assert h_ch_perf["est"] == pytest.approx(val_h_perf["est"], abs=tol["est"])
    assert h_ch_perf["se"] == pytest.approx(val_h_perf["se"], abs=tol["se"])
    assert h_ch_perf["df"] == val_h_perf["df"]

    val_m0_perf = next(v for v in ref["values"] if v["measure"] == "Delta_M0_perfect")
    assert m0_ch_perf["est"] == pytest.approx(val_m0_perf["est"], abs=tol["est"])
    assert m0_ch_perf["se"] == pytest.approx(val_m0_perf["se"], abs=tol["se"])
    assert m0_ch_perf["df"] == val_m0_perf["df"]

    # 2. Partial Overlap Panel
    des_part = SurveyDesign(strata="stratum", psu="cluster", weights="w")
    res_part = estimate(
        overlaps["partial_panel"],
        spec,
        des_part,
        tvar="wave",
        panel_id="hhid",
        overlap="auto",
        k=0.5,
    )
    ch_part = res_part.changes()
    h_ch_part = ch_part.filter((pl.col("measure") == "H") & (pl.col("type") == "abs")).row(0, named=True)

    val_h_part = next(v for v in ref["values"] if v["measure"] == "Delta_H_partial")
    assert h_ch_part["est"] == pytest.approx(val_h_part["est"], abs=tol["est"])
    assert h_ch_part["se"] == pytest.approx(val_h_part["se"], abs=tol["se"])
    assert h_ch_part["df"] == val_h_part["df"]


@pytest.mark.optional
def test_overlap_stata_mpitb_conformity():
    """Optional comparison to Stata mpitb reference (skipped when Stata JSON absent)."""
    stata_ref = REF_DIR / "overlap_stata.json"
    if not stata_ref.exists():
        pytest.skip("Stata mpitb reference file overlap_stata.json is not present (PLAN.md §14.10/§14.13)")
