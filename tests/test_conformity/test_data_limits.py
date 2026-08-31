"""Conformity tests for Data Limits (extreme weights and missing value policies) (PLAN.md §14.10)."""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest

from afmpi import Specification, SurveyDesign, estimate
from tests.test_conformity.generate import generate_data_limits

REF_DIR = Path(__file__).resolve().parent / "reference"


def test_data_limits_conformity():
    """Verify extreme weights and missing value policies against R survey reference."""
    ref_file = REF_DIR / "data_limits.json"
    assert ref_file.exists(), f"Reference file {ref_file} missing"

    with open(ref_file) as f:
        ref = json.load(f)

    tol = ref["tolerance"]
    data_lims = generate_data_limits(ref["generator_seed"])
    design = SurveyDesign(weights="w", strata="stratum", psu="psu")

    # 1. Extreme weights (1:1,000,000 ratio)
    spec_ext = Specification({"d": ["i0", "i1", "i2", "i3"]})
    res_ext = estimate(data_lims["extreme_weights"], spec_ext, design, k=0.5)
    est_ext = res_ext.estimates()

    for suffix in ["H", "M0", "A"]:
        val = next(v for v in ref["values"] if v["measure"] == f"{suffix}_ext")
        row = est_ext.filter(pl.col("measure") == suffix).row(0, named=True)
        assert row["est"] == pytest.approx(val["est"], abs=tol["est"]), f"Mismatch in {suffix}_ext est"
        assert row["se"] == pytest.approx(val["se"], abs=tol["se"]), f"Mismatch in {suffix}_ext se"
        assert row["df"] == val["df"], f"Mismatch in {suffix}_ext df"

    # 2. Missing values: listwise deletion
    spec_lw = Specification({"d": ["i0", "i1", "i2", "i3"]}, missing_policy="listwise_deletion")
    res_lw = estimate(data_lims["missing_values"], spec_lw, design, k=0.5)
    est_lw = res_lw.estimates()

    for suffix in ["H", "M0", "A"]:
        val = next(v for v in ref["values"] if v["measure"] == f"{suffix}_lw")
        row = est_lw.filter(pl.col("measure") == suffix).row(0, named=True)
        assert row["est"] == pytest.approx(val["est"], abs=tol["est"]), f"Mismatch in {suffix}_lw est"
        assert row["se"] == pytest.approx(val["se"], abs=tol["se"]), f"Mismatch in {suffix}_lw se"
        assert row["df"] == val["df"], f"Mismatch in {suffix}_lw df"

    # 3. Missing values: treat as non-deprived
    spec_tan = Specification({"d": ["i0", "i1", "i2", "i3"]}, missing_policy="treat_as_nondeprived")
    res_tan = estimate(data_lims["missing_values"], spec_tan, design, k=0.5)
    est_tan = res_tan.estimates()

    for suffix in ["H", "M0", "A"]:
        val = next(v for v in ref["values"] if v["measure"] == f"{suffix}_tan")
        row = est_tan.filter(pl.col("measure") == suffix).row(0, named=True)
        assert row["est"] == pytest.approx(val["est"], abs=tol["est"]), f"Mismatch in {suffix}_tan est"
        assert row["se"] == pytest.approx(val["se"], abs=tol["se"]), f"Mismatch in {suffix}_tan se"
        assert row["df"] == val["df"], f"Mismatch in {suffix}_tan df"

    # 4. Missing values: reweighting
    spec_rw = Specification({"d": ["i0", "i1", "i2", "i3"]}, missing_policy="reweighting")
    res_rw = estimate(data_lims["missing_values"], spec_rw, design, k=0.5)
    est_rw = res_rw.estimates()

    for suffix in ["H", "M0", "A"]:
        val = next(v for v in ref["values"] if v["measure"] == f"{suffix}_rw")
        row = est_rw.filter(pl.col("measure") == suffix).row(0, named=True)
        assert row["est"] == pytest.approx(val["est"], abs=tol["est"]), f"Mismatch in {suffix}_rw est"
        assert row["se"] == pytest.approx(val["se"], abs=tol["se"]), f"Mismatch in {suffix}_rw se"
        assert row["df"] == val["df"], f"Mismatch in {suffix}_rw df"


@pytest.mark.optional
def test_data_limits_stata_mpitb_conformity():
    """Optional comparison to Stata mpitb reference (skipped when Stata JSON absent)."""
    stata_ref = REF_DIR / "data_limits_stata.json"
    if not stata_ref.exists():
        pytest.skip("Stata mpitb reference file data_limits_stata.json is not present (PLAN.md §14.10/§14.13)")
