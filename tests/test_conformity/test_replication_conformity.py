"""Conformity tests for ReplicateDesign methods (JK, BRR, Fay, Boot, SDR) (PLAN.md §14.10)."""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest

from afmpi import ReplicateDesign, Specification, estimate
from tests.test_conformity.generate import generate_replication

REF_DIR = Path(__file__).resolve().parent / "reference"


def test_replication_conformity():
    """Verify all six replicate weight methods against R survey reference."""
    ref_file = REF_DIR / "replication.json"
    assert ref_file.exists(), f"Reference file {ref_file} missing"

    with open(ref_file) as f:
        ref = json.load(f)

    tol = ref["tolerance"]
    df_rep = generate_replication(ref["generator_seed"])
    spec = Specification({"d": ["i0", "i1", "i2", "i3"]})

    rep_designs = {
        "JK1": ReplicateDesign(weights="w", psu="psu", method="JK1"),
        "JKn": ReplicateDesign(weights="w", strata="stratum", psu="psu", method="JKn"),
        "BRR": ReplicateDesign(weights="w", strata="stratum", psu="psu", method="BRR"),
        "Fay_BRR": ReplicateDesign(
            weights="w", strata="stratum", psu="psu", method="Fay_BRR", fay=0.5
        ),
        "bootstrap": ReplicateDesign(
            weights="w", strata="stratum", psu="psu", method="bootstrap", seed=42, replicates=20
        ),
        "SDR": ReplicateDesign(weights="w", strata="stratum", psu="psu", method="SDR"),
    }

    for method, des in rep_designs.items():
        res = estimate(df_rep, spec, des, k=1 / 3)
        estimates = res.estimates()

        for suffix in ["H", "M0", "A"]:
            val = next(v for v in ref["values"] if v["measure"] == f"{suffix}_{method}")
            row = estimates.filter(pl.col("measure") == suffix).row(0, named=True)
            assert row["est"] == pytest.approx(val["est"], abs=tol["est"]), (
                f"Mismatch in {suffix}_{method} est"
            )
            assert row["se"] == pytest.approx(val["se"], abs=tol["se"]), (
                f"Mismatch in {suffix}_{method} se"
            )
            assert row["df"] == val["df"], f"Mismatch in {suffix}_{method} df"


@pytest.mark.optional
def test_replication_stata_mpitb_conformity():
    """Optional comparison to Stata mpitb reference (skipped when Stata JSON absent)."""
    stata_ref = REF_DIR / "replication_stata.json"
    if not stata_ref.exists():
        pytest.skip(
            "Stata mpitb reference file replication_stata.json is not present "
            "(PLAN.md §14.10/§14.13)"
        )
