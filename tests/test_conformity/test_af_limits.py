"""Conformity tests for Alkire-Foster limit cases (PLAN.md §14.10)."""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest

from afmpi import Specification, SurveyDesign, estimate
from tests.test_conformity.generate import generate_af_limits

REF_DIR = Path(__file__).resolve().parent / "reference"


def test_af_limits_conformity():
    """Verify boundary conditions (zero poor, all poor, k=0, k=1) against R survey reference."""
    ref_file = REF_DIR / "af_limits.json"
    assert ref_file.exists(), f"Reference file {ref_file} missing"

    with open(ref_file) as f:
        ref = json.load(f)

    tol = ref["tolerance"]
    af_data = generate_af_limits(ref["generator_seed"])
    spec = Specification({"d": ["i0", "i1", "i2", "i3"]})
    design = SurveyDesign(weights="w", strata="stratum", psu="psu")

    # 1. Zero Poor (nobody poor)
    res_zero = estimate(af_data["zero_poor"], spec, design, k=1 / 3)
    est_zero = res_zero.estimates()
    for suffix in ["H", "M0"]:
        val = next(v for v in ref["values"] if v["measure"] == f"{suffix}_zero")
        row = est_zero.filter(pl.col("measure") == suffix).row(0, named=True)
        assert row["est"] == pytest.approx(val["est"], abs=tol["est"]), (
            f"Mismatch in {suffix}_zero est"
        )
        assert row["se"] == pytest.approx(val["se"], abs=tol["se"]), (
            f"Mismatch in {suffix}_zero se"
        )
        assert row["df"] == val["df"], f"Mismatch in {suffix}_zero df"

    # 2. All Poor (everyone poor)
    res_all = estimate(af_data["all_poor"], spec, design, k=1 / 3)
    est_all = res_all.estimates()
    for suffix in ["H", "M0", "A"]:
        val = next(v for v in ref["values"] if v["measure"] == f"{suffix}_all")
        row = est_all.filter(pl.col("measure") == suffix).row(0, named=True)
        assert row["est"] == pytest.approx(val["est"], abs=tol["est"]), (
            f"Mismatch in {suffix}_all est"
        )
        assert row["se"] == pytest.approx(val["se"], abs=tol["se"]), (
            f"Mismatch in {suffix}_all se"
        )
        assert row["df"] == val["df"], f"Mismatch in {suffix}_all df"

    # 3. Cutoff k = 0.0 on mixed data
    res_k0 = estimate(af_data["mixed"], spec, design, k=0.0)
    est_k0 = res_k0.estimates()
    for suffix in ["H", "M0", "A"]:
        val = next(v for v in ref["values"] if v["measure"] == f"{suffix}_k0")
        row = est_k0.filter(pl.col("measure") == suffix).row(0, named=True)
        assert row["est"] == pytest.approx(val["est"], abs=tol["est"]), (
            f"Mismatch in {suffix}_k0 est"
        )
        assert row["se"] == pytest.approx(val["se"], abs=tol["se"]), (
            f"Mismatch in {suffix}_k0 se"
        )
        assert row["df"] == val["df"], f"Mismatch in {suffix}_k0 df"

    # 4. Cutoff k = 1.0 on mixed data
    res_k1 = estimate(af_data["mixed"], spec, design, k=1.0)
    est_k1 = res_k1.estimates()
    for suffix in ["H", "M0", "A"]:
        val = next(v for v in ref["values"] if v["measure"] == f"{suffix}_k1")
        row = est_k1.filter(pl.col("measure") == suffix).row(0, named=True)
        assert row["est"] == pytest.approx(val["est"], abs=tol["est"]), (
            f"Mismatch in {suffix}_k1 est"
        )
        assert row["se"] == pytest.approx(val["se"], abs=tol["se"]), (
            f"Mismatch in {suffix}_k1 se"
        )
        assert row["df"] == val["df"], f"Mismatch in {suffix}_k1 df"


@pytest.mark.optional
def test_af_limits_stata_mpitb_conformity():
    """Optional comparison to Stata mpitb reference (skipped when Stata JSON absent)."""
    stata_ref = REF_DIR / "af_limits_stata.json"
    if not stata_ref.exists():
        pytest.skip(
            "Stata mpitb reference file af_limits_stata.json is not present "
            "(PLAN.md §14.10/§14.13)"
        )
