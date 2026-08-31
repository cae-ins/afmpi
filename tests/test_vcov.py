"""Tests for variance-covariance matrix calculation (PLAN.md §14.7)."""

from math import sqrt

import numpy as np
import polars as pl
import pytest

from afmpi import (
    Design,
    ReplicateDesign,
    Specification,
    SurveyDesign,
    estimate,
)


class DummyCensusDesign(Design):
    @property
    def variance_path(self) -> str:
        return "census"

    @property
    def design_columns(self) -> tuple[str, ...]:
        return ()

    @property
    def required_columns(self) -> tuple[str, ...]:
        return ()


@pytest.fixture
def sample_data():
    return pl.DataFrame(
        {
            "stratum": ["1", "1", "1", "1", "2", "2", "2", "2"],
            "psu": ["101", "101", "102", "102", "201", "201", "202", "202"],
            "weight": [1.0, 1.0, 1.2, 1.2, 0.8, 0.8, 1.1, 1.1],
            "region": ["A", "A", "B", "B", "A", "A", "B", "B"],
            "d1_i1": [1, 0, 1, 1, 0, 0, 1, 0],
            "d1_i2": [0, 1, 1, 0, 1, 0, 0, 1],
            "d2_i3": [1, 1, 0, 1, 0, 1, 1, 0],
        }
    )


@pytest.fixture
def spec():
    return Specification(
        dimensions={"d1": ("d1_i1", "d1_i2"), "d2": ("d2_i3",)},
    )


def test_diag_vcov_equals_se_squared_taylor(sample_data, spec):
    """Test 1a: diag(vcov()) == se()**2 EXACTLY for Taylor design."""
    design = SurveyDesign(strata="stratum", psu="psu", weights="weight")
    res = estimate(sample_data, spec, design, k=1 / 3)

    vcov_table = res.vcov(measures=("H", "A", "M0"))
    estimates_table = res.estimates().filter(pl.col("measure").is_in(["H", "A", "M0"]))

    se_map = dict(
        zip(
            estimates_table["measure"].to_list(),
            estimates_table["se"].to_list(),
            strict=True,
        )
    )

    for row in vcov_table.to_dicts():
        term = row["term"]
        diag_val = row[term]
        se_val = se_map[term]
        # Check sqrt(diag_val) == se_val exactly or allclose at 1e-15
        np.testing.assert_allclose(sqrt(diag_val), se_val, rtol=1e-15, atol=1e-15)


def test_diag_vcov_equals_se_squared_replication(sample_data, spec):
    """Test 1b: diag(vcov()) == se()**2 EXACTLY for Replication design."""
    design = ReplicateDesign(strata="stratum", psu="psu", weights="weight", method="JKn")
    res = estimate(sample_data, spec, design, k=1 / 3)

    vcov_table = res.vcov(measures=("H", "A", "M0"))
    estimates_table = res.estimates().filter(pl.col("measure").is_in(["H", "A", "M0"]))

    se_map = dict(
        zip(
            estimates_table["measure"].to_list(),
            estimates_table["se"].to_list(),
            strict=True,
        )
    )

    for row in vcov_table.to_dicts():
        term = row["term"]
        diag_val = row[term]
        se_val = se_map[term]
        np.testing.assert_allclose(sqrt(diag_val), se_val, rtol=1e-15, atol=1e-15)


def test_diag_vcov_equals_se_squared_census(sample_data, spec):
    """Test 1c: diag(vcov()) == 0 for Census design."""
    design = DummyCensusDesign()
    res = estimate(sample_data, spec, design, k=1 / 3)

    vcov_table = res.vcov(measures=("H", "A", "M0"))
    for row in vcov_table.to_dicts():
        term = row["term"]
        assert row[term] == 0.0


def test_vcov_symmetric_and_positive_semidefinite(sample_data, spec):
    """Test 2: V is symmetric and positive semi-definite (eigenvalues >= -1e-12)."""
    design = SurveyDesign(strata="stratum", psu="psu", weights="weight")
    res = estimate(sample_data, spec, design, k=1 / 3)

    measures = ("H", "A", "M0", "hd::d1_i1", "actb_dim::d1")
    vcov_df = res.vcov(measures=measures)

    # Convert to matrix
    m_cols = [c for c in vcov_df.columns if c != "term"]
    V = vcov_df.select(m_cols).to_numpy()

    # Symmetry check bit-for-bit
    np.testing.assert_equal(V, V.T)

    # Eigenvalues check
    eigvals = np.linalg.eigvalsh(V)
    assert np.all(eigvals >= -1e-12)


def test_multiple_cutoffs_requires_k(sample_data, spec):
    """Test 3: Multiple cutoffs estimated -> k=None raises ValueError listing cutoffs."""
    design = SurveyDesign(strata="stratum", psu="psu", weights="weight")
    res = estimate(sample_data, spec, design, k=[1 / 3, 0.5])

    with pytest.raises(ValueError, match="multiple cutoffs estimated"):
        res.vcov()

    # Specifying k works
    vcov_df = res.vcov(k=0.5)
    assert vcov_df.height == 3


def test_custom_measures_selection(sample_data, spec):
    """Test 4: Default measures vs custom measures sequence."""
    design = SurveyDesign(strata="stratum", psu="psu", weights="weight")
    res = estimate(sample_data, spec, design, k=1 / 3)

    # Default
    default_df = res.vcov()
    assert default_df.columns == ["term", "H", "A", "M0"]

    # Custom
    custom_measures = ("M0", "hd::d1_i1", "pctb_dim::d1")
    custom_df = res.vcov(measures=custom_measures)
    assert custom_df.columns == ["term", "M0", "hd::d1_i1", "pctb_dim::d1"]
    assert custom_df["term"].to_list() == list(custom_measures)


def test_subgroup_vcov_context(sample_data, spec):
    """Test 6: Subgroup VCOV context."""
    design = SurveyDesign(strata="stratum", psu="psu", weights="weight")
    res = estimate(sample_data, spec, design, k=1 / 3, over="region")

    sub_vcov = res.vcov(over="region", subgroup="A", measures=("H", "A", "M0"))
    assert sub_vcov.height == 3

    # Check that requiring subgroup when over is provided raises ValueError
    with pytest.raises(ValueError, match="subgroup must be specified"):
        res.vcov(over="region")


def test_vcov_oracle_r_survey_validation():
    """Oracle R survey validation for variance-covariance matrix (PLAN.md §18).

    Exact numerical co-incidence (< 1e-12) against values obtained from
    R survey v4.5+ delta method on stacked domain indicators.
    """
    rows = [
        {"stratum": "1", "psu": "101", "weight": 1.0, "group": "A", "i1": 1, "i2": 1},
        {"stratum": "1", "psu": "101", "weight": 1.0, "group": "A", "i1": 1, "i2": 1},
        {"stratum": "1", "psu": "102", "weight": 1.0, "group": "B", "i1": 1, "i2": 1},
        {"stratum": "1", "psu": "102", "weight": 1.0, "group": "B", "i1": 1, "i2": 0},
        {"stratum": "2", "psu": "201", "weight": 1.0, "group": "A", "i1": 1, "i2": 0},
        {"stratum": "2", "psu": "201", "weight": 1.0, "group": "A", "i1": 0, "i2": 0},
        {"stratum": "2", "psu": "202", "weight": 1.0, "group": "B", "i1": 0, "i2": 0},
        {"stratum": "2", "psu": "202", "weight": 1.0, "group": "B", "i1": 0, "i2": 0},
    ]
    df = pl.DataFrame(rows)
    spec = Specification(dimensions={"d1": ("i1", "i2")})
    design = SurveyDesign(strata="stratum", psu="psu", weights="weight")

    res = estimate(df, spec, design, k=0.5, over="group")
    vcov_A = res.vcov(over="group", subgroup="A", measures=("M0",))
    vcov_B = res.vcov(over="group", subgroup="B", measures=("M0",))

    v_aa = vcov_A.filter(pl.col("term") == "M0")["M0"].item()
    v_bb = vcov_B.filter(pl.col("term") == "M0")["M0"].item()

    assert v_aa == pytest.approx(0.0703125, abs=1e-12)
    assert v_bb == pytest.approx(0.0703125, abs=1e-12)
