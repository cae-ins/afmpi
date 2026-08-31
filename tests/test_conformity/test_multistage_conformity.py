"""Conformity tests for multi-stage and FPC designs (PLAN.md §14.10)."""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest

from afmpi import Specification, Stage, SurveyDesign, estimate
from tests.test_conformity.generate import generate_multistage

REF_DIR = Path(__file__).resolve().parent / "reference"


def test_multistage_2stage_fpc_conformity():
    """Verify 2-stage sampling with FPC at each stage against R survey reference."""
    ref_file = REF_DIR / "multistage.json"
    assert ref_file.exists(), f"Reference file {ref_file} missing"

    with open(ref_file) as f:
        ref = json.load(f)

    tol = ref["tolerance"]
    df_fpc, df_census = generate_multistage(ref["generator_seed"])
    spec = Specification({"d": ["i0", "i1", "i2", "i3"]})

    # 1. Two-stage FPC
    des_fpc = SurveyDesign(
        weights="w",
        stages=[
            Stage(id="psu", strata="stratum", fpc="f1"),
            Stage(id="ssu", fpc="f2"),
        ],
    )
    res_fpc = estimate(df_fpc, spec, des_fpc, k=0.5)
    est_fpc = res_fpc.estimates()

    for suffix in ["H", "M0", "A"]:
        val = next(v for v in ref["values"] if v["measure"] == f"{suffix}_fpc")
        row = est_fpc.filter(pl.col("measure") == suffix).row(0, named=True)
        assert row["est"] == pytest.approx(val["est"], abs=tol["est"]), (
            f"Mismatch in {suffix}_fpc est"
        )
        assert row["se"] == pytest.approx(val["se"], abs=tol["se"]), (
            f"Mismatch in {suffix}_fpc se"
        )
        assert row["df"] == val["df"], f"Mismatch in {suffix}_fpc df"

    # 2. Stage 1 Census
    des_census = SurveyDesign(
        weights="w",
        stages=[
            Stage(id="psu", strata="stratum", fpc="f1"),
            Stage(id="ssu", fpc="f2"),
        ],
    )
    res_census = estimate(df_census, spec, des_census, k=0.5)
    est_census = res_census.estimates()

    for suffix in ["H", "M0", "A"]:
        val = next(v for v in ref["values"] if v["measure"] == f"{suffix}_census1")
        row = est_census.filter(pl.col("measure") == suffix).row(0, named=True)
        assert row["est"] == pytest.approx(val["est"], abs=tol["est"]), (
            f"Mismatch in {suffix}_census1 est"
        )
        assert row["se"] == pytest.approx(val["se"], abs=tol["se"]), (
            f"Mismatch in {suffix}_census1 se"
        )
        assert row["df"] == val["df"], f"Mismatch in {suffix}_census1 df"


@pytest.mark.optional
def test_multistage_stata_mpitb_conformity():
    """Optional comparison to Stata mpitb reference (skipped when Stata JSON absent)."""
    stata_ref = REF_DIR / "multistage_stata.json"
    if not stata_ref.exists():
        pytest.skip(
            "Stata mpitb reference file multistage_stata.json is not present "
            "(PLAN.md §14.10/§14.13)"
        )
