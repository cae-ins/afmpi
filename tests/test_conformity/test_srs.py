"""Conformity tests for SRS and Stratified SRS designs (PLAN.md §14.10)."""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest

from afmpi import Specification, SurveyDesign, estimate
from tests.test_conformity.generate import generate_srs, generate_stratified_srs

REF_DIR = Path(__file__).resolve().parent / "reference"


def test_srs_conformity():
    """Verify SRS point estimates, standard errors, and degrees of freedom against R survey reference."""
    ref_file = REF_DIR / "srs.json"
    assert ref_file.exists(), f"Reference file {ref_file} missing"

    with open(ref_file) as f:
        ref = json.load(f)

    tol = ref["tolerance"]
    df_srs = generate_srs(ref["generator_seed"])
    spec = Specification({"d": ["i0", "i1", "i2", "i3"]})
    design = SurveyDesign(weights="w", household_size="size")

    res = estimate(df_srs, spec, design, k=1/3)
    estimates = res.estimates()

    for val in ref["values"]:
        m = val["measure"]
        row = estimates.filter(pl.col("measure") == m).row(0, named=True)
        assert row["est"] == pytest.approx(val["est"], abs=tol["est"]), f"Mismatch in {m} est"
        assert row["se"] == pytest.approx(val["se"], abs=tol["se"]), f"Mismatch in {m} se"
        assert row["df"] == val["df"], f"Mismatch in {m} df"


def test_stratified_srs_conformity():
    """Verify Stratified SRS against R survey reference."""
    ref_file = REF_DIR / "stratified_srs.json"
    assert ref_file.exists(), f"Reference file {ref_file} missing"

    with open(ref_file) as f:
        ref = json.load(f)

    tol = ref["tolerance"]
    df_strat = generate_stratified_srs(ref["generator_seed"])
    spec = Specification({"d": ["i0", "i1", "i2", "i3"]})
    design = SurveyDesign(weights="w", household_size="size", strata="stratum")

    res = estimate(df_strat, spec, design, k=1/3)
    estimates = res.estimates()

    for val in ref["values"]:
        m = val["measure"]
        row = estimates.filter(pl.col("measure") == m).row(0, named=True)
        assert row["est"] == pytest.approx(val["est"], abs=tol["est"]), f"Mismatch in {m} est"
        assert row["se"] == pytest.approx(val["se"], abs=tol["se"]), f"Mismatch in {m} se"
        assert row["df"] == val["df"], f"Mismatch in {m} df"


@pytest.mark.optional
def test_srs_stata_mpitb_conformity():
    """Optional comparison to Stata mpitb reference (skipped when Stata JSON absent)."""
    stata_ref = REF_DIR / "srs_stata.json"
    if not stata_ref.exists():
        pytest.skip("Stata mpitb reference file srs_stata.json is not present (PLAN.md §14.10/§14.13)")
