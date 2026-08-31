"""Tests for CensusDesign and census estimation (PLAN.md §14.9)."""

from __future__ import annotations

import pandas as pd
import polars as pl
import pytest

import afmpi
from afmpi import CensusDesign, Specification, SurveyDesign, estimate


@pytest.fixture
def census_data() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "ind1": [1, 0, 1, 0, 1, 0, 1, 1, 0, 1],
            "ind2": [0, 1, 1, 0, 0, 1, 1, 0, 0, 1],
            "ind3": [1, 1, 0, 0, 1, 0, 1, 1, 1, 0],
            "weight": [1.5] * 10,
            "region": ["North", "North", "North", "South", "South", "South", "East", "East", "West", "West"],
        }
    )


def test_census_design_properties():
    design = CensusDesign(weights="weight", household_size=None)
    assert design.variance_path == "census"
    assert design.required_columns == ("weight",)
    assert design.design_columns == ()

    with pytest.raises(ValueError, match="a census has no sampling variance"):
        design.test()


def test_census_estimation_se_zero(census_data):
    spec = Specification(
        dimensions={"d1": ["ind1", "ind2"], "d2": ["ind3"]},
    )
    design = CensusDesign(weights="weight")
    res = estimate(census_data, spec, design, k=1 / 3, over="region")

    estimates = res.estimates()

    if isinstance(estimates, pd.DataFrame):
        for _, row in estimates.iterrows():
            assert row["se"] == 0.0
            assert row["lci"] == row["est"]
            assert row["uci"] == row["est"]
            assert row["cv"] == 0.0
            assert row["df"] == 0
            assert row["psus"] == 0
            assert row["strata"] == 0
    else:
        for row in estimates.iter_rows(named=True):
            assert row["se"] == 0.0
            assert row["lci"] == row["est"]
            assert row["uci"] == row["est"]
            assert row["cv"] == 0.0
            assert row["df"] == 0
            assert row["psus"] == 0
            assert row["strata"] == 0


def test_census_vs_surveydesign_point_estimates(census_data):
    spec = Specification(
        dimensions={"d1": ["ind1", "ind2"], "d2": ["ind3"]},
    )
    census_design = CensusDesign(weights="weight")
    survey_design = SurveyDesign(weights="weight")

    res_census = estimate(census_data, spec, census_design, k=1 / 3)
    res_survey = estimate(census_data, spec, survey_design, k=1 / 3)

    assert pytest.approx(res_census.M0) == res_survey.M0
    assert pytest.approx(res_census.H) == res_survey.H
    assert pytest.approx(res_census.A) == res_survey.A


def test_census_vcov_and_test(census_data):
    spec = Specification(
        dimensions={"d1": ["ind1", "ind2"], "d2": ["ind3"]},
    )
    design = CensusDesign(weights="weight")
    res = estimate(census_data, spec, design, k=1 / 3)

    vcov_df = res.vcov()
    if isinstance(vcov_df, pd.DataFrame):
        for col in ["H", "A", "M0"]:
            assert (vcov_df[col] == 0.0).all()
    else:
        for col in ["H", "A", "M0"]:
            assert (vcov_df[col] == 0.0).all()

    with pytest.raises(ValueError, match="a census has no sampling variance"):
        res.test("region == 'North'")
