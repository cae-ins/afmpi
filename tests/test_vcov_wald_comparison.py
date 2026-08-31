"""Oracle comparison tests for VCOV matrix and Wald hypothesis testing (PLAN.md §18).

Validates numerical equivalence against values from tests/oracle/vcov_wald_oracle.R
and tests/oracle/vcov_wald_meta.json using R 'survey' package.
"""

import json
from pathlib import Path

import polars as pl
import pytest

from afmpi import Specification, SurveyDesign, estimate

ORACLE_DIR = Path(__file__).resolve().parent / "oracle"


def test_vcov_wald_comparison_against_r_oracle():
    """Compare cross-domain VCOV and Wald test against R survey oracle."""
    meta_path = ORACLE_DIR / "vcov_wald_meta.json"
    assert meta_path.exists(), f"Oracle metadata {meta_path} missing"

    with open(meta_path) as f:
        meta = json.load(f)

    data_path = ORACLE_DIR / "data_vcov_wald.csv"
    if data_path.exists():
        df = pl.read_csv(data_path)
    else:
        rows = [
            {
                "stratum": s,
                "psu": p,
                "weight": 1.0,
                "group": g,
                "i1": i1,
                "i2": i2,
            }
            for s, p, g, i1, i2 in [
                ("1", "101", "A", 1, 1),
                ("1", "101", "A", 1, 1),
                ("1", "102", "B", 1, 1),
                ("1", "102", "B", 1, 0),
                ("2", "201", "A", 1, 0),
                ("2", "201", "A", 0, 0),
                ("2", "202", "B", 0, 0),
                ("2", "202", "B", 0, 0),
            ]
        ]
        df = pl.DataFrame(rows)

    spec = Specification(dimensions={"d1": ("i1", "i2")})
    design = SurveyDesign(strata="stratum", psu="psu", weights="weight")

    res = estimate(df, spec, design, k=0.5, over="group")

    # 1. Wald Hypothesis Test
    test_res = res.test(("group", "A"), ("group", "B"), measure="M0", dist="F")
    oracle_test = meta["test"]

    assert test_res.estimate == pytest.approx(oracle_test["estimate"], abs=1e-12)
    assert test_res.se == pytest.approx(oracle_test["se"], abs=1e-10)
    assert test_res.statistic == pytest.approx(oracle_test["statistic"], abs=1e-10)
    assert test_res.df1 == oracle_test["df1"]
    assert test_res.df2 == oracle_test["df2"]
    assert test_res.p_value == pytest.approx(oracle_test["p_value"], abs=1e-10)

    # 2. Subgroup A VCOV Matrix
    vcov_A = res.vcov(over="group", subgroup="A", measures=("H", "A", "M0"))
    oracle_vcov_A = meta["vcov_A"]
    for row_dict, oracle_dict in zip(vcov_A.to_dicts(), oracle_vcov_A, strict=True):
        assert row_dict["term"] == oracle_dict["term"]
        for m in ("H", "A", "M0"):
            assert row_dict[m] == pytest.approx(oracle_dict[m], abs=1e-12)

    # 3. Subgroup B VCOV Matrix
    vcov_B = res.vcov(over="group", subgroup="B", measures=("H", "A", "M0"))
    oracle_vcov_B = meta["vcov_B"]
    for row_dict, oracle_dict in zip(vcov_B.to_dicts(), oracle_vcov_B, strict=True):
        assert row_dict["term"] == oracle_dict["term"]
        for m in ("H", "A", "M0"):
            assert row_dict[m] == pytest.approx(oracle_dict[m], abs=1e-12)
