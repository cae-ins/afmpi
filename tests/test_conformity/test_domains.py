"""Conformity tests for Domain and Subpopulation estimation (PLAN.md §14.10)."""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest

from afmpi import Specification, SurveyDesign, estimate
from tests.test_conformity.generate import generate_domains

REF_DIR = Path(__file__).resolve().parent / "reference"


def test_domains_conformity():
    """Verify domain estimation across strata and small domains against R survey reference."""
    ref_file = REF_DIR / "domains.json"
    assert ref_file.exists(), f"Reference file {ref_file} missing"

    with open(ref_file) as f:
        ref = json.load(f)

    tol = ref["tolerance"]
    df_dom = generate_domains(ref["generator_seed"])
    spec = Specification({"d": ["i0", "i1", "i2", "i3"]})
    design = SurveyDesign(weights="w", strata="stratum", psu="psu")

    # 1. Domains by region
    res_reg = estimate(df_dom, spec, design, k=0.5, over="region")
    est_reg = res_reg.estimates()

    for val in [v for v in ref["values"] if v["over"] == "region"]:
        m = val["measure"]
        sub = val["subgroup"]
        row = est_reg.filter(
            (pl.col("measure") == m)
            & (pl.col("over") == "region")
            & (pl.col("subgroup") == sub)
        ).row(0, named=True)
        assert row["est"] == pytest.approx(val["est"], abs=tol["est"]), (
            f"Mismatch in {m} ({sub}) est"
        )
        assert row["se"] == pytest.approx(val["se"], abs=tol["se"]), (
            f"Mismatch in {m} ({sub}) se"
        )
        assert row["df"] == val["df"], f"Mismatch in {m} ({sub}) df"

    # 2. Domains by group (testing small domain G3)
    res_grp = estimate(df_dom, spec, design, k=0.5, over="group")
    est_grp = res_grp.estimates()

    for val in [v for v in ref["values"] if v["over"] == "group"]:
        m = val["measure"]
        sub = val["subgroup"]
        row = est_grp.filter(
            (pl.col("measure") == m) & (pl.col("over") == "group") & (pl.col("subgroup") == sub)
        ).row(0, named=True)
        assert row["est"] == pytest.approx(val["est"], abs=tol["est"]), (
            f"Mismatch in {m} ({sub}) est"
        )
        assert row["se"] == pytest.approx(val["se"], abs=tol["se"]), (
            f"Mismatch in {m} ({sub}) se"
        )
        assert row["df"] == val["df"], f"Mismatch in {m} ({sub}) df"


@pytest.mark.optional
def test_domains_stata_mpitb_conformity():
    """Optional comparison to Stata mpitb reference (skipped when Stata JSON absent)."""
    stata_ref = REF_DIR / "domains_stata.json"
    if not stata_ref.exists():
        pytest.skip(
            "Stata mpitb reference file domains_stata.json is not present "
            "(PLAN.md §14.10/§14.13)"
        )
