"""Tests for the five lonely PSU policies (PLAN.md §14.4c)."""

import numpy as np
import pandas as pd
import polars as pl
import pytest

from afmpi import LonelyPSUWarning, Specification, SurveyDesign, estimate


@pytest.fixture
def lonely_data() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"h": "H1", "psu": "P1", "w": 1.0, "ind1": 1, "ind2": 0, "sub": "X"},
            {"h": "H1", "psu": "P2", "w": 1.0, "ind1": 0, "ind2": 1, "sub": "X"},
            {"h": "H2", "psu": "P3", "w": 1.0, "ind1": 1, "ind2": 1, "sub": "X"},
            {"h": "H2", "psu": "P4", "w": 1.0, "ind1": 0, "ind2": 0, "sub": "X"},
            {"h": "H3", "psu": "P5", "w": 1.0, "ind1": 1, "ind2": 1, "sub": "X"},
        ]
    )


@pytest.fixture
def spec() -> Specification:
    return Specification(
        dimensions={"d1": ["ind1"], "d2": ["ind2"]},
        weights={"d1": 0.5, "d2": 0.5},
    )


def test_five_policies_on_same_dataset(lonely_data: pd.DataFrame, spec: Specification) -> None:
    """1. Test all five policies on a dataset with 3 strata including 1 lonely stratum."""
    policies = ["fail", "certainty", "adjust", "average", "collapse"]
    results = {}

    for pol in policies:
        d = SurveyDesign(weights="w", strata="h", psu="psu", lonely_psu=pol)
        if pol == "fail":
            with pytest.warns(LonelyPSUWarning):
                res = estimate(lonely_data, spec, d, k=0.5).estimates()
        else:
            res = estimate(lonely_data, spec, d, k=0.5).estimates()
        results[pol] = res

    m0_fail = results["fail"][results["fail"]["measure"] == "M0"].iloc[0]
    assert np.isnan(m0_fail["se"])

    for pol in ["certainty", "adjust", "average", "collapse"]:
        m0_row = results[pol][results[pol]["measure"] == "M0"].iloc[0]
        assert not np.isnan(m0_row["se"])
        assert m0_row["se"] >= 0


def test_fail_emits_warning_and_returns_nan(lonely_data: pd.DataFrame, spec: Specification) -> None:
    """2. "fail" returns nan AND emits exactly one LonelyPSUWarning."""
    d = SurveyDesign(weights="w", strata="h", psu="psu", lonely_psu="fail")
    with pytest.warns(LonelyPSUWarning, match="contain\\(s\\) a single PSU"):
        res = estimate(lonely_data, spec, d, k=0.5).estimates()

    for _, row in res.iterrows():
        assert np.isnan(row["se"])


def test_certainty_same_variance_as_data_without_lonely_stratum(
    lonely_data: pd.DataFrame, spec: Specification
) -> None:
    """3. "certainty" gives zero variance contribution for the lonely stratum."""
    data_without_h3 = lonely_data[lonely_data["h"] != "H3"].copy()

    d_cert = SurveyDesign(weights="w", strata="h", psu="psu", lonely_psu="certainty")
    d_no_h3 = SurveyDesign(weights="w", strata="h", psu="psu")

    res_cert = estimate(lonely_data, spec, d_cert, k=0.5).estimates()
    res_no_h3 = estimate(data_without_h3, spec, d_no_h3, k=0.5).estimates()

    m0_cert = res_cert[res_cert["measure"] == "M0"].iloc[0]
    m0_no_h3 = res_no_h3[res_no_h3["measure"] == "M0"].iloc[0]

    assert m0_cert["df"] == m0_no_h3["df"]
    # Ratio of population is 4/5, so SE scales accordingly
    assert m0_cert["se"] == pytest.approx(m0_no_h3["se"] * 4.0 / 5.0, abs=1e-12)


def test_collapse_matches_manual_merge(spec: Specification) -> None:
    """4. "collapse" on two lonely strata gives same df as manual merge upstream."""
    df_2lonely = pd.DataFrame(
        [
            {"h": "H1", "psu": "P1", "w": 1.0, "ind1": 1, "ind2": 0},
            {"h": "H1", "psu": "P2", "w": 1.0, "ind1": 0, "ind2": 1},
            {"h": "H2", "psu": "P3", "w": 1.0, "ind1": 1, "ind2": 1},
            {"h": "H3", "psu": "P4", "w": 1.0, "ind1": 0, "ind2": 0},
        ]
    )

    df_merged = df_2lonely.copy()
    df_merged["h"] = df_merged["h"].replace({"H2": "__afmpi_collapsed", "H3": "__afmpi_collapsed"})

    d_col = SurveyDesign(weights="w", strata="h", psu="psu", lonely_psu="collapse")
    d_manual = SurveyDesign(weights="w", strata="h", psu="psu")

    res_col = estimate(df_2lonely, spec, d_col, k=0.5).estimates()
    res_manual = estimate(df_merged, spec, d_manual, k=0.5).estimates()

    m0_col = res_col[res_col["measure"] == "M0"].iloc[0]
    m0_manual = res_manual[res_manual["measure"] == "M0"].iloc[0]

    assert m0_col["df"] == m0_manual["df"]
    assert m0_col["se"] == pytest.approx(m0_manual["se"], abs=1e-12)


def test_average_with_empty_h2_falls_back_to_fail(spec: Specification) -> None:
    """5. "average" with empty H2 -> fallback to "fail" + warning."""
    df_all_lonely = pd.DataFrame(
        [
            {"h": "H1", "psu": "P1", "w": 1.0, "ind1": 1, "ind2": 0},
            {"h": "H2", "psu": "P2", "w": 1.0, "ind1": 0, "ind2": 1},
        ]
    )

    d = SurveyDesign(weights="w", strata="h", psu="psu", lonely_psu="average")
    with pytest.warns(LonelyPSUWarning, match="falling back to 'fail'"):
        res = estimate(df_all_lonely, spec, d, k=0.5).estimates()

    for _, row in res.iterrows():
        assert np.isnan(row["se"])


def test_domain_induced_lonely_psu(spec: Specification) -> None:
    """6. Lonely PSU induced by a domain affect only rows of that subgroup."""
    df = pd.DataFrame(
        [
            {"h": "H1", "psu": "P1", "sub": "A", "w": 1.0, "ind1": 1, "ind2": 0},
            {"h": "H1", "psu": "P2", "sub": "A", "w": 1.0, "ind1": 0, "ind2": 1},
            {"h": "H2", "psu": "P3", "sub": "A", "w": 1.0, "ind1": 1, "ind2": 1},
            {"h": "H2", "psu": "P4", "sub": "B", "w": 1.0, "ind1": 0, "ind2": 0},
        ]
    )

    d = SurveyDesign(weights="w", strata="h", psu="psu", lonely_psu="certainty")
    res = estimate(df, spec, d, k=0.5, over="sub").estimates()

    sub_a = res[res["subgroup"] == "A"]
    assert len(sub_a) > 0
    for _, row in sub_a.iterrows():
        assert not np.isnan(row["se"])


def test_non_regression_without_lonely_strata(spec: Specification) -> None:
    """7. Non-regression: without lonely strata, all 5 policies give exact same result."""
    df = pd.DataFrame(
        [
            {"h": "H1", "psu": "P1", "w": 1.0, "ind1": 1, "ind2": 0},
            {"h": "H1", "psu": "P2", "w": 1.0, "ind1": 0, "ind2": 1},
            {"h": "H2", "psu": "P3", "w": 1.0, "ind1": 1, "ind2": 1},
            {"h": "H2", "psu": "P4", "w": 1.0, "ind1": 0, "ind2": 0},
        ]
    )

    results = []
    for pol in ["fail", "certainty", "adjust", "average", "collapse"]:
        d = SurveyDesign(weights="w", strata="h", psu="psu", lonely_psu=pol)
        res = estimate(df, spec, d, k=0.5).estimates()
        results.append(res)

    for i in range(1, len(results)):
        pd.testing.assert_frame_equal(results[0], results[i])
