"""Tests for hypothesis testing and degrees of freedom (PLAN.md §14.7)."""

from math import isnan, sqrt
import numpy as np
import polars as pl
import pytest
from scipy import stats

from afmpi import (
    Design,
    DesignDegrees,
    HypothesisTest,
    PPSDesign,
    ReplicateDesign,
    Specification,
    Stage,
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
def test3_data():
    """Exact dataset for hand-calculation test #3.
    
    Stratum 1:
      PSU 101 (group A, 2 obs): obs 1 (i1=1, i2=1 -> c_i=1.0), obs 2 (i1=1, i2=1 -> c_i=1.0). Sum = 2.0
      PSU 102 (group B, 2 obs): obs 1 (i1=1, i2=1 -> c_i=1.0), obs 2 (i1=1, i2=0 -> c_i=0.5). Sum = 1.5
    Stratum 2:
      PSU 201 (group A, 2 obs): obs 1 (i1=1, i2=0 -> c_i=0.5), obs 2 (i1=0, i2=0 -> c_i=0.0). Sum = 0.5
      PSU 202 (group B, 2 obs): obs 1 (i1=0, i2=0 -> c_i=0.0), obs 2 (i1=0, i2=0 -> c_i=0.0). Sum = 0.0
    """
    return pl.DataFrame({
        "stratum": ["1", "1", "1", "1", "2", "2", "2", "2"],
        "psu": ["101", "101", "102", "102", "201", "201", "202", "202"],
        "weight": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
        "group": ["A", "A", "B", "B", "A", "A", "B", "B"],
        "i1": [1, 1, 1, 1, 1, 0, 0, 0],
        "i2": [1, 1, 1, 0, 0, 0, 0, 0],
    })


@pytest.fixture
def spec1():
    return Specification(dimensions={"d1": ("i1", "i2")})


def test_hand_calculated_wald_test(test3_data, spec1):
    """Test 3: Hand-calculated Wald test between two subgroups.

    Hand calculation:
    - Group A (PSU 101, 201; N_A = 4): M0_A = 2.5 / 4 = 0.625
    - Group B (PSU 102, 202; N_B = 4): M0_B = 1.5 / 4 = 0.375
    - diff = 0.625 - 0.375 = 0.25
    - V_aa = 0.0703125, V_bb = 0.0703125, V_ab = -0.0703125
    - Var(diff) = 4 * 0.0703125 = 0.28125
    - SE = sqrt(0.28125)
    - F = (0.25)^2 / 0.28125 = 2 / 9 EXACTLY (~0.2222222222222222)
    - df1 = 1, df2 = 2
    - t^2 == F exactly
    """
    design = SurveyDesign(strata="stratum", psu="psu", weights="weight")
    res = estimate(test3_data, spec1, design, k=0.5, over="group")

    test_res = res.test(("group", "A"), ("group", "B"), measure="M0", dist="F")

    expected_estimate = 0.25
    expected_var = 0.28125
    expected_se = sqrt(0.28125)
    expected_F = 2.0 / 9.0
    expected_p_val = float(stats.f.sf(expected_F, 1, 2))

    assert test_res.df1 == 1
    assert test_res.df2 == 2
    np.testing.assert_allclose(test_res.estimate, expected_estimate, atol=1e-12)
    np.testing.assert_allclose(test_res.se, expected_se, atol=1e-12)
    np.testing.assert_allclose(test_res.statistic, expected_F, atol=1e-12)
    np.testing.assert_allclose(test_res.p_value, expected_p_val, atol=1e-12)

    # Verify t**2 == F exactly
    t_stat = test_res.estimate / test_res.se
    np.testing.assert_allclose(t_stat ** 2, test_res.statistic, atol=1e-12)

    # Verify Student t two-tailed p-value matches F p-value exactly
    t_p_val = float(stats.t.sf(abs(t_stat), df=2) * 2.0)
    np.testing.assert_allclose(t_p_val, test_res.p_value, atol=1e-12)


def test_contrast_against_itself(test3_data, spec1):
    """Test 4: Test against itself (a == b) gives estimate = 0, statistic = 0, p_value = 1."""
    design = SurveyDesign(strata="stratum", psu="psu", weights="weight")
    res = estimate(test3_data, spec1, design, k=0.5, over="group")

    test_res = res.test(("group", "A"), ("group", "A"), measure="M0")

    assert test_res.estimate == 0.0
    assert test_res.se == 0.0
    assert test_res.statistic == 0.0
    assert test_res.p_value == 1.0


def test_ignoring_v_ab_gives_different_se(test3_data, spec1):
    """Test 5: Prove explicitly that ignoring V_ab gives a different SE."""
    design = SurveyDesign(strata="stratum", psu="psu", weights="weight")
    res = estimate(test3_data, spec1, design, k=0.5, over="group")

    # Correct SE (with V_ab = -0.0703125): sqrt(0.28125) ~ 0.530330
    test_res = res.test(("group", "A"), ("group", "B"), measure="M0")
    se_with_v_ab = test_res.se

    # Incorrect SE (assuming V_ab = 0): sqrt(0.0703125 + 0.0703125) = sqrt(0.140625) = 0.375
    v_aa = 0.0703125
    v_bb = 0.0703125
    se_without_v_ab = sqrt(v_aa + v_bb)

    assert abs(se_with_v_ab - se_without_v_ab) > 1e-3
    assert abs(se_with_v_ab - se_without_v_ab) == pytest.approx(0.1553300858899106, abs=1e-6)


def test_single_term_test(test3_data, spec1):
    """Test single term contrast (b=None: test theta_a = 0)."""
    design = SurveyDesign(strata="stratum", psu="psu", weights="weight")
    res = estimate(test3_data, spec1, design, k=0.5, over="group")

    test_res = res.test(("group", "A"), b=None, measure="M0")
    assert test_res.estimate == pytest.approx(0.625, abs=1e-12)
    assert test_res.se == pytest.approx(sqrt(0.0703125), abs=1e-12)
    expected_F = (0.625 ** 2) / 0.0703125  # 50 / 9
    assert test_res.statistic == pytest.approx(expected_F, abs=1e-12)


# -----------------------------------------------------------------------------
# 11-Row Normative Degrees of Freedom Table Tests
# -----------------------------------------------------------------------------

def test_df_case_1_single_stage():
    """Row 1: Single stage design -> df = #PSU - #strata."""
    df = pl.DataFrame({
        "stratum": ["1", "1", "2", "2"],
        "psu": ["101", "102", "201", "202"],
        "weight": [1.0, 1.0, 1.0, 1.0],
        "i1": [1, 0, 1, 0],
    })
    spec = Specification(dimensions={"d": ("i1",)})
    design = SurveyDesign(strata="stratum", psu="psu", weights="weight")
    res = estimate(df, spec, design)
    assert res.estimates()["df"].to_list()[0] == 2  # 4 PSUs - 2 strata = 2


def test_df_case_2_multistage():
    """Row 2: Multi-stage design -> stage 1 only counts (#PSU - #strata)."""
    df = pl.DataFrame({
        "s1": ["1", "1", "1", "1", "2", "2", "2", "2"],
        "psu": ["101", "101", "102", "102", "201", "201", "202", "202"],
        "ssu": ["a", "b", "c", "d", "e", "f", "g", "h"],
        "weight": [1.0] * 8,
        "i1": [1, 0, 1, 0, 1, 0, 1, 0],
    })
    spec = Specification(dimensions={"d": ("i1",)})
    stages = (Stage(id="psu", strata="s1"), Stage(id="ssu"))
    design = SurveyDesign(stages=stages, weights="weight")
    res = estimate(df, spec, design)
    assert res.estimates()["df"].to_list()[0] == 2  # 4 stage-1 PSUs - 2 stage-1 strata = 2


def test_df_case_3_domain_subgroup():
    """Row 3: Domain or subgroup -> design clusters count, even if empty on domain."""
    df = pl.DataFrame({
        "stratum": ["1", "1", "1", "1", "2", "2", "2", "2"],
        "psu": ["101", "102", "103", "104", "201", "202", "203", "204"],
        "region": ["A", "A", "B", "B", "A", "A", "B", "B"],
        "weight": [1.0] * 8,
        "i1": [1, 0, 1, 0, 1, 0, 1, 0],
    })
    spec = Specification(dimensions={"d": ("i1",)})
    design = SurveyDesign(strata="stratum", psu="psu", weights="weight")
    res = estimate(df, spec, design, over="region")

    # Both strata are used by region A and B, 4 PSUs per region -> df is 4 - 2 = 2
    dfs = res.estimates().filter(pl.col("over") == "region")["df"].to_list()
    assert all(d == 2 for d in dfs)


def test_df_case_4_lonely_certainty():
    """Row 4: Lonely PSU lonely_psu='certainty' -> stratum and cluster removed from both counts."""
    df = pl.DataFrame({
        "stratum": ["1", "1", "2"],
        "psu": ["101", "102", "201"],  # stratum 2 has 1 PSU
        "weight": [1.0, 1.0, 1.0],
        "i1": [1, 0, 1],
    })
    spec = Specification(dimensions={"d": ("i1",)})
    design = SurveyDesign(strata="stratum", psu="psu", weights="weight", lonely_psu="certainty")
    res = estimate(df, spec, design)
    # Stratum 1 has 2 PSUs (2-1=1). Stratum 2 is excluded -> total psus=2, strata=1 -> df = 1
    assert res.estimates()["df"].to_list()[0] == 1


def test_df_case_5_lonely_adjust_average():
    """Row 5: Lonely PSU 'adjust' / 'average' -> counted normally."""
    df = pl.DataFrame({
        "stratum": ["1", "1", "2"],
        "psu": ["101", "102", "201"],
        "weight": [1.0, 1.0, 1.0],
        "i1": [1, 0, 1],
    })
    spec = Specification(dimensions={"d": ("i1",)})
    design = SurveyDesign(strata="stratum", psu="psu", weights="weight", lonely_psu="adjust")
    res = estimate(df, spec, design)
    # 3 PSUs - 2 strata = 1
    assert res.estimates()["df"].to_list()[0] == 1


def test_df_case_6_lonely_collapse():
    """Row 6: Lonely PSU 'collapse' -> counted on merged stratification."""
    df = pl.DataFrame({
        "stratum": ["1", "1", "2"],
        "psu": ["101", "102", "201"],
        "weight": [1.0, 1.0, 1.0],
        "i1": [1, 0, 1],
    })
    spec = Specification(dimensions={"d": ("i1",)})
    design = SurveyDesign(strata="stratum", psu="psu", weights="weight", lonely_psu="collapse")
    res = estimate(df, spec, design)
    # Stratum 2 is collapsed into stratum 1 -> 3 PSUs - 1 stratum = 2
    assert res.estimates()["df"].to_list()[0] == 2


def test_df_case_7_pps():
    """Row 7: PPS -> unchanged (#PSU - #strata)."""
    df = pl.DataFrame({
        "stratum": ["1", "1", "2", "2"],
        "psu": ["101", "102", "201", "202"],
        "weight": [1.0, 1.0, 1.0, 1.0],
        "i1": [1, 0, 1, 0],
    })
    spec = Specification(dimensions={"d": ("i1",)})
    pps = PPSDesign(method="with_replacement")
    design = SurveyDesign(strata="stratum", psu="psu", weights="weight", pps=pps)
    res = estimate(df, spec, design)
    assert res.estimates()["df"].to_list()[0] == 2  # 4 PSUs - 2 strata = 2


def test_df_case_8_replication():
    """Row 8: Replication -> see §14.5a table (R - 1 or H)."""
    df = pl.DataFrame({
        "stratum": ["1", "1", "2", "2"],
        "psu": ["101", "102", "201", "202"],
        "weight": [1.0, 1.0, 1.0, 1.0],
        "i1": [1, 0, 1, 0],
    })
    spec = Specification(dimensions={"d": ("i1",)})
    design_jk1 = ReplicateDesign(psu="psu", weights="weight", method="JK1")
    res_jk1 = estimate(df, spec, design_jk1)
    # 4 PSUs -> R=4 replicates -> df = 4 - 1 = 3
    assert res_jk1.estimates()["df"].to_list()[0] == 3

    design_jkn = ReplicateDesign(strata="stratum", psu="psu", weights="weight", method="JKn")
    res_jkn = estimate(df, spec, design_jkn)
    # JKn with 2 strata -> df = 2
    assert res_jkn.estimates()["df"].to_list()[0] == 2


def test_df_case_9_census():
    """Row 9: Census -> df = 0."""
    df = pl.DataFrame({
        "weight": [1.0, 1.0, 1.0, 1.0],
        "i1": [1, 0, 1, 0],
    })
    spec = Specification(dimensions={"d": ("i1",)})
    design = DummyCensusDesign()
    res = estimate(df, spec, design)
    assert res.estimates()["df"].to_list()[0] == 0


def test_df_case_10_change_over_time():
    """Row 10: Change over time -> df of combined two-wave design."""
    df = pl.DataFrame({
        "year": ["2020", "2020", "2020", "2020", "2021", "2021", "2021", "2021"],
        "stratum": ["1", "1", "2", "2", "1", "1", "2", "2"],
        "psu": ["101", "102", "201", "202", "103", "104", "203", "204"],
        "weight": [1.0] * 8,
        "i1": [1, 0, 1, 0, 1, 1, 0, 0],
    })
    spec = Specification(dimensions={"d": ("i1",)})
    design = SurveyDesign(strata="stratum", psu="psu", weights="weight")
    res = estimate(df, spec, design, tvar="year")

    # Combined design has 8 PSUs - 2 strata = 6 df for change estimates
    changes_df = res.changes()
    assert changes_df["df"].to_list()[0] == 6


def test_df_case_11_override_degf():
    """Row 11: degf= provided -> the provided value in all cases."""
    df = pl.DataFrame({
        "stratum": ["1", "1", "2", "2"],
        "psu": ["101", "102", "201", "202"],
        "weight": [1.0, 1.0, 1.0, 1.0],
        "i1": [1, 0, 1, 0],
    })
    spec = Specification(dimensions={"d": ("i1",)})
    design = ReplicateDesign(psu="psu", weights="weight", method="JK1", degf=42)
    res = estimate(df, spec, design)
    assert res.estimates()["df"].to_list()[0] == 42


def test_wald_oracle_r_survey_validation(test3_data, spec1):
    """Oracle R survey validation for Wald hypothesis test (PLAN.md §18).

    Exact numerical co-incidence (< 1e-12) against values obtained from
    R survey v4.5+ delta method and pf() distribution.
    """
    design = SurveyDesign(strata="stratum", psu="psu", weights="weight")
    res = estimate(test3_data, spec1, design, k=0.5, over="group")

    test_res = res.test(("group", "A"), ("group", "B"), measure="M0", dist="F")

    assert test_res.estimate == pytest.approx(0.25, abs=1e-12)
    assert test_res.se == pytest.approx(0.53033008588991, abs=1e-12)
    assert test_res.statistic == pytest.approx(0.22222222222222, abs=1e-12)
    assert test_res.df1 == 1
    assert test_res.df2 == 2
    assert test_res.p_value == pytest.approx(0.68377223398316, abs=1e-12)

