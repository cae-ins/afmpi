"""Conformity tests for the five lonely PSU policies (PLAN.md §14.10)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from afmpi import LonelyPSUWarning, Specification, SurveyDesign, estimate
from tests.test_conformity.generate import generate_lonely_psu

REF_DIR = Path(__file__).resolve().parent / "reference"


def test_lonely_conformity():
    """Verify all five lonely PSU policies against R survey reference."""
    ref_file = REF_DIR / "lonely_psu.json"
    assert ref_file.exists(), f"Reference file {ref_file} missing"

    with open(ref_file) as f:
        ref = json.load(f)

    tol = ref["tolerance"]
    df_lonely = generate_lonely_psu(ref["generator_seed"])
    spec = Specification({"d": ["i0", "i1", "i2", "i3"]})

    policies = ["fail", "certainty", "adjust", "average", "collapse"]

    for pol in policies:
        des = SurveyDesign(
            weights="w",
            strata="stratum",
            psu="psu",
            lonely_psu=pol,
        )
        if pol == "fail":
            with pytest.warns(LonelyPSUWarning, match="contain\\(s\\) a single PSU"):
                res = estimate(df_lonely, spec, des, k=0.5)
        else:
            res = estimate(df_lonely, spec, des, k=0.5)

        estimates = res.estimates()

        for suffix in ["H", "M0", "A"]:
            val = next(v for v in ref["values"] if v["measure"] == f"{suffix}_{pol}")
            row = estimates.filter(pl.col("measure") == suffix).row(0, named=True)
            assert row["est"] == pytest.approx(val["est"], abs=tol["est"]), (
                f"Mismatch in {suffix}_{pol} est"
            )

            if val["se"] is None:
                assert np.isnan(row["se"]), f"Expected NaN SE for {suffix}_{pol}"
            else:
                assert row["se"] == pytest.approx(val["se"], abs=tol["se"]), (
                    f"Mismatch in {suffix}_{pol} se"
                )

            assert row["df"] == val["df"], f"Mismatch in {suffix}_{pol} df"


@pytest.mark.optional
def test_lonely_stata_mpitb_conformity():
    """Optional comparison to Stata mpitb reference (skipped when Stata JSON absent)."""
    stata_ref = REF_DIR / "lonely_stata.json"
    if not stata_ref.exists():
        pytest.skip(
            "Stata mpitb reference file lonely_stata.json is not present "
            "(PLAN.md §14.10/§14.13)"
        )
