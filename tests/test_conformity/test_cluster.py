"""Conformity tests for 1-stage cluster and stratified cluster designs (PLAN.md §14.10)."""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest

from afmpi import Specification, SurveyDesign, estimate
from tests.test_conformity.generate import (
    generate_cluster_1stage,
    generate_stratified_cluster,
)

REF_DIR = Path(__file__).resolve().parent / "reference"


def test_cluster_1stage_conformity():
    """Verify 1-stage cluster design against R survey reference."""
    ref_file = REF_DIR / "cluster_1stage.json"
    assert ref_file.exists(), f"Reference file {ref_file} missing"

    with open(ref_file) as f:
        ref = json.load(f)

    tol = ref["tolerance"]
    df_cl = generate_cluster_1stage(ref["generator_seed"])
    spec = Specification({"d": ["i0", "i1", "i2", "i3"]})
    design = SurveyDesign(weights="w", household_size="size", psu="psu")

    res = estimate(df_cl, spec, design, k=1/3)
    estimates = res.estimates()

    for val in ref["values"]:
        m = val["measure"]
        row = estimates.filter(pl.col("measure") == m).row(0, named=True)
        assert row["est"] == pytest.approx(val["est"], abs=tol["est"]), f"Mismatch in {m} est"
        assert row["se"] == pytest.approx(val["se"], abs=tol["se"]), f"Mismatch in {m} se"
        assert row["df"] == val["df"], f"Mismatch in {m} df"


def test_stratified_cluster_conformity():
    """Verify stratified cluster design against R survey reference."""
    ref_file = REF_DIR / "stratified_cluster.json"
    assert ref_file.exists(), f"Reference file {ref_file} missing"

    with open(ref_file) as f:
        ref = json.load(f)

    tol = ref["tolerance"]
    df_scl = generate_stratified_cluster(ref["generator_seed"])
    spec = Specification({"d": ["i0", "i1", "i2", "i3"]})
    design = SurveyDesign(weights="w", household_size="size", strata="stratum", psu="psu")

    res = estimate(df_scl, spec, design, k=1/3)
    estimates = res.estimates()

    for val in ref["values"]:
        m = val["measure"]
        row = estimates.filter(pl.col("measure") == m).row(0, named=True)
        assert row["est"] == pytest.approx(val["est"], abs=tol["est"]), f"Mismatch in {m} est"
        assert row["se"] == pytest.approx(val["se"], abs=tol["se"]), f"Mismatch in {m} se"
        assert row["df"] == val["df"], f"Mismatch in {m} df"


@pytest.mark.optional
def test_cluster_stata_mpitb_conformity():
    """Optional comparison to Stata mpitb reference (skipped when Stata JSON absent)."""
    stata_ref = REF_DIR / "cluster_stata.json"
    if not stata_ref.exists():
        pytest.skip("Stata mpitb reference file cluster_stata.json is not present (PLAN.md §14.10/§14.13)")
