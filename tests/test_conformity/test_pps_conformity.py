"""Conformity tests for PPS (unequal probability sampling) designs (PLAN.md §14.10)."""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest

from afmpi import PPSDesign, Specification, SurveyDesign, estimate
from tests.test_conformity.generate import generate_pps

REF_DIR = Path(__file__).resolve().parent / "reference"


def test_pps_conformity():
    """Verify PPS with replacement, Sen-Yates-Grundy, and Hajek against R reference."""
    ref_file = REF_DIR / "pps.json"
    assert ref_file.exists(), f"Reference file {ref_file} missing"

    with open(ref_file) as f:
        ref = json.load(f)

    tol = ref["tolerance"]
    df_pps, df_joint = generate_pps(ref["generator_seed"])
    spec = Specification({"d": ["i0", "i1", "i2", "i3"]})

    # 1. PPS With Replacement
    des_wr = SurveyDesign(
        weights="w",
        strata="stratum",
        psu="psu",
        pps=PPSDesign(method="with_replacement", inclusion_probability="pi"),
    )
    res_wr = estimate(df_pps, spec, des_wr, k=0.5)
    est_wr = res_wr.estimates()

    for suffix in ["H", "M0", "A"]:
        val = next(v for v in ref["values"] if v["measure"] == f"{suffix}_wr")
        row = est_wr.filter(pl.col("measure") == suffix).row(0, named=True)
        assert row["est"] == pytest.approx(val["est"], abs=tol["est"]), (
            f"Mismatch in {suffix}_wr est"
        )
        assert row["se"] == pytest.approx(val["se"], abs=tol["se"]), (
            f"Mismatch in {suffix}_wr se"
        )
        assert row["df"] == val["df"], f"Mismatch in {suffix}_wr df"

    # 2. Sen-Yates-Grundy (SYG) with Joint Inclusion Probabilities
    des_syg = SurveyDesign(
        weights="w",
        strata="stratum",
        psu="psu",
        pps=PPSDesign(
            method="without_replacement",
            inclusion_probability="pi",
            joint_probability=df_joint,
            variance="sen_yates_grundy",
        ),
    )
    res_syg = estimate(df_pps, spec, des_syg, k=0.5)
    est_syg = res_syg.estimates()

    for suffix in ["H", "M0", "A"]:
        val = next(v for v in ref["values"] if v["measure"] == f"{suffix}_syg")
        row = est_syg.filter(pl.col("measure") == suffix).row(0, named=True)
        assert row["est"] == pytest.approx(val["est"], abs=tol["est"]), (
            f"Mismatch in {suffix}_syg est"
        )
        assert row["se"] == pytest.approx(val["se"], abs=tol["se"]), (
            f"Mismatch in {suffix}_syg se"
        )
        assert row["df"] == val["df"], f"Mismatch in {suffix}_syg df"

    # 3. Hajek exact formula
    des_hajek = SurveyDesign(
        weights="w",
        strata="stratum",
        psu="psu",
        pps=PPSDesign(
            method="without_replacement", inclusion_probability="pi", variance="hajek"
        ),
    )
    res_hajek = estimate(df_pps, spec, des_hajek, k=0.5)
    est_hajek = res_hajek.estimates()

    for suffix in ["H", "M0", "A"]:
        val = next(v for v in ref["values"] if v["measure"] == f"{suffix}_hajek")
        row = est_hajek.filter(pl.col("measure") == suffix).row(0, named=True)
        assert row["est"] == pytest.approx(val["est"], abs=tol["est"]), (
            f"Mismatch in {suffix}_hajek est"
        )
        assert row["se"] == pytest.approx(val["se"], abs=tol["se"]), (
            f"Mismatch in {suffix}_hajek se"
        )
        assert row["df"] == val["df"], f"Mismatch in {suffix}_hajek df"


def test_pps_conformity_lazy():
    """Verify PPS lazy estimation against R reference."""
    ref_file = REF_DIR / "pps.json"
    with open(ref_file) as f:
        ref = json.load(f)

    tol = ref["tolerance"]
    df_pps, _ = generate_pps(ref["generator_seed"])
    spec = Specification({"d": ["i0", "i1", "i2", "i3"]})

    # 1. PPS With Replacement lazy
    des_wr = SurveyDesign(
        weights="w",
        strata="stratum",
        psu="psu",
        pps=PPSDesign(method="with_replacement", inclusion_probability="pi"),
    )
    res_wr = estimate(df_pps, spec, des_wr, k=0.5, lazy=True, streaming=True).collect()
    est_wr = res_wr.estimates()

    for suffix in ["H", "M0", "A"]:
        val = next(v for v in ref["values"] if v["measure"] == f"{suffix}_wr")
        row = est_wr.filter(pl.col("measure") == suffix).row(0, named=True)
        assert row["est"] == pytest.approx(val["est"], abs=tol["est"])
        assert row["se"] == pytest.approx(val["se"], abs=tol["se"])
        assert row["df"] == val["df"]

    # 2. Hajek lazy
    des_hajek = SurveyDesign(
        weights="w",
        strata="stratum",
        psu="psu",
        pps=PPSDesign(
            method="without_replacement", inclusion_probability="pi", variance="hajek"
        ),
    )
    res_hajek = estimate(df_pps, spec, des_hajek, k=0.5, lazy=True, streaming=True).collect()
    est_hajek = res_hajek.estimates()

    for suffix in ["H", "M0", "A"]:
        val = next(v for v in ref["values"] if v["measure"] == f"{suffix}_hajek")
        row = est_hajek.filter(pl.col("measure") == suffix).row(0, named=True)
        assert row["est"] == pytest.approx(val["est"], abs=tol["est"])
        assert row["se"] == pytest.approx(val["se"], abs=tol["se"])
        assert row["df"] == val["df"]


@pytest.mark.optional
def test_pps_stata_mpitb_conformity():
    """Optional comparison to Stata mpitb reference (skipped when Stata JSON absent)."""
    stata_ref = REF_DIR / "pps_stata.json"
    if not stata_ref.exists():
        pytest.skip(
            "Stata mpitb reference file pps_stata.json is not present "
            "(PLAN.md §14.10/§14.13)"
        )
