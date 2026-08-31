"""Tests for configurable missing-value policies (PLAN.md §14.8)."""

from __future__ import annotations

import pandas as pd
import polars as pl
import pytest

from afmpi import MissingReport, Specification, estimate


def test_non_regression_listwise_and_reweighting():
    """Test 1: listwise_deletion and reweighting give identical expected results."""
    data = pl.DataFrame(
        {
            "i1": [1, 0, 1, None],
            "i2": [1, 1, None, 0],
        }
    )
    spec_lw = Specification({"d": ["i1", "i2"]}, missing_policy="listwise_deletion")
    res_lw = estimate(data, spec_lw, k=0.5)

    spec_rw = Specification({"d": ["i1", "i2"]}, missing_policy="reweighting")
    res_rw = estimate(data, spec_rw, k=0.5)

    # listwise: drops row 2 (1, None) and row 3 (None, 0).
    # Remaining: row 0 (1, 1 -> c_0=1.0) and row 1 (0, 1 -> c_1=0.5).
    assert res_lw.observations == 2
    assert res_lw.excluded_observations == 2
    assert res_lw.H == pytest.approx(1.0)
    assert res_lw.A == pytest.approx(0.75)
    assert res_lw.M0 == pytest.approx(0.75)

    # reweighting: keeps row 2 (i1=1, i2=None -> reweighted c_2 = 1.0)
    # and row 3 (i1=None, i2=0 -> reweighted c_3 = 0.0).
    assert res_rw.observations == 4
    assert res_rw.excluded_observations == 0
    assert res_rw.H == pytest.approx(0.75)
    assert res_rw.A == pytest.approx(5 / 6)
    assert res_rw.M0 == pytest.approx(0.625)


def test_all_three_policies_identical_when_no_missing_values():
    """Test 2: Without missing values, all 3 policies produce identical results."""
    data = pl.DataFrame(
        {
            "i1": [1, 0, 1, 0],
            "i2": [0, 1, 1, 0],
            "i3": [1, 0, 0, 1],
        }
    )
    spec_lw = Specification({"d": ["i1", "i2", "i3"]}, missing_policy="listwise_deletion")
    spec_rw = Specification({"d": ["i1", "i2", "i3"]}, missing_policy="reweighting")
    spec_tan = Specification({"d": ["i1", "i2", "i3"]}, missing_policy="treat_as_nondeprived")

    res_lw = estimate(data, spec_lw, k=0.5)
    res_rw = estimate(data, spec_rw, k=0.5)
    res_tan = estimate(data, spec_tan, k=0.5)

    assert res_lw.M0 == res_rw.M0 == res_tan.M0
    assert res_lw.H == res_rw.H == res_tan.H
    assert res_lw.A == res_rw.A == res_tan.A
    assert (res_lw.scores()["score"] == res_rw.scores()["score"]).all()
    assert (res_lw.scores()["score"] == res_tan.scores()["score"]).all()


def test_hand_calculated_three_distinct_c_i_scores():
    """Test 3: Hand-constructed case with hardcoded expected c_i values.

    Calculated by hand:
    Indicators: i1, i2, i3 with equal weights (1/3, 1/3, 1/3).
    Row: i1=1, i2=0, i3=None.

    - listwise_deletion: Row has a missing value -> dropped (0 rows in output).
    - reweighting: Observed indicators i1 (w=1/3) and i2 (w=1/3), observed_weight = 2/3.
      Reweighted weights w1' = 0.5, w2' = 0.5.
      g1=1, g2=0 -> c_i = 0.5 * 1 + 0.5 * 0 = 0.5 (exact: 1/2).
    - treat_as_nondeprived: Weights (1/3, 1/3, 1/3) unchanged.
      Missing i3 treated as non-deprived (g3=0).
      g1=1, g2=0, g3=0 -> c_i = (1/3)*1 + (1/3)*0 + (1/3)*0 = 1/3
      (exact: 0.3333333333333333).
    - Custom policy (treat_as_deprived): Missing i3 treated as deprived (g3=1).
      g1=1, g2=0, g3=1 -> c_i = (1/3)*1 + (1/3)*0 + (1/3)*1 = 2/3
      (exact: 0.6666666666666666).
    """
    data = pl.DataFrame(
        {
            "i1": [1],
            "i2": [0],
            "i3": [None],
        }
    )

    # 1. listwise_deletion drops the row
    spec_lw = Specification({"d": ["i1", "i2", "i3"]}, missing_policy="listwise_deletion")
    with pytest.raises(ValueError, match="no observations remain"):
        estimate(data, spec_lw)

    # 2. reweighting -> c_i = 0.5
    spec_rw = Specification({"d": ["i1", "i2", "i3"]}, missing_policy="reweighting")
    res_rw = estimate(data, spec_rw, k=0.1)
    assert res_rw.scores()["score"][0] == pytest.approx(0.5)

    # 3. treat_as_nondeprived -> c_i = 1/3
    spec_tan = Specification({"d": ["i1", "i2", "i3"]}, missing_policy="treat_as_nondeprived")
    res_tan = estimate(data, spec_tan, k=0.1)
    assert res_tan.scores()["score"][0] == pytest.approx(1 / 3)

    # 4. custom policy (treat_as_deprived) -> c_i = 2/3
    def treat_as_deprived(df: pl.DataFrame, spec: Specification) -> pl.DataFrame:
        weights = spec.indicator_weights
        indicators = spec.indicators
        g_cols = [
            pl.col(item).cast(pl.Float64).fill_null(1.0).alias(f"__afmpi_g{idx}")
            for idx, item in enumerate(indicators)
        ]
        obs_cols = [
            pl.lit(1.0, dtype=pl.Float64).alias(f"__afmpi_obs{idx}")
            for idx in range(len(indicators))
        ]
        wc_cols = [
            (pl.col(f"__afmpi_g{idx}") * weights[item]).alias(f"__afmpi_wc{idx}")
            for idx, item in enumerate(indicators)
        ]
        return df.with_columns(*g_cols, *obs_cols).with_columns(*wc_cols)

    spec_custom = Specification({"d": ["i1", "i2", "i3"]}, missing_policy=treat_as_deprived)
    res_custom = estimate(data, spec_custom, k=0.1)
    assert res_custom.scores()["score"][0] == pytest.approx(2 / 3)


def test_reweighting_drops_row_when_all_indicators_missing():
    """Test 4: reweighting drops rows where all indicators are missing."""
    data = pl.DataFrame(
        {
            "i1": [1, None],
            "i2": [0, None],
        }
    )
    spec = Specification({"d": ["i1", "i2"]}, missing_policy="reweighting")
    res = estimate(data, spec, k=0.5)

    assert res.observations == 1
    assert res.excluded_observations == 1
    assert res.scores().height == 1
    assert res.scores()["score"][0] == pytest.approx(0.5)


def test_treat_as_nondeprived_keeps_all_rows():
    """Test 5: treat_as_nondeprived keeps all rows, excluded_observations == 0."""
    data = pl.DataFrame(
        {
            "i1": [1, None],
            "i2": [None, None],
        }
    )
    spec = Specification({"d": ["i1", "i2"]}, missing_policy="treat_as_nondeprived")
    res = estimate(data, spec, k=0.5)

    assert res.observations == 2
    assert res.excluded_observations == 0
    assert res.scores().height == 2
    assert res.scores()["score"][0] == pytest.approx(0.5)
    assert res.scores()["score"][1] == pytest.approx(0.0)


def test_custom_callable_policy_validation():
    """Test 6: Callable policy with missing columns or out-of-bounds c_i -> ValueError."""

    # 6a: Missing required column __afmpi_wc0
    def policy_missing_col(df: pl.DataFrame, spec: Specification) -> pl.DataFrame:
        return df.with_columns(
            pl.lit(1.0).alias("__afmpi_g0"),
            pl.lit(1.0).alias("__afmpi_obs0"),
        )

    spec_bad1 = Specification({"d": ["i1"]}, missing_policy=policy_missing_col)
    data = pl.DataFrame({"i1": [1]})
    with pytest.raises(ValueError, match="missing required column '__afmpi_wc0'"):
        estimate(data, spec_bad1)

    # 6b: Invalid g_ij value (2.0)
    def policy_bad_g(df: pl.DataFrame, spec: Specification) -> pl.DataFrame:
        return df.with_columns(
            pl.lit(2.0).alias("__afmpi_g0"),
            pl.lit(1.0).alias("__afmpi_obs0"),
            pl.lit(1.0).alias("__afmpi_wc0"),
        )

    spec_bad2 = Specification({"d": ["i1"]}, missing_policy=policy_bad_g)
    with pytest.raises(ValueError, match="must contain values in {0, 1}"):
        estimate(data, spec_bad2)

    # 6c: c_i > 1
    def policy_ci_over_1(df: pl.DataFrame, spec: Specification) -> pl.DataFrame:
        return df.with_columns(
            pl.lit(1.0).alias("__afmpi_g0"),
            pl.lit(1.0).alias("__afmpi_g1"),
            pl.lit(1.0).alias("__afmpi_obs0"),
            pl.lit(1.0).alias("__afmpi_obs1"),
            pl.lit(0.8).alias("__afmpi_wc0"),
            pl.lit(0.8).alias("__afmpi_wc1"),
        )

    spec_bad3 = Specification({"d": ["i1", "i2"]}, missing_policy=policy_ci_over_1)
    data2 = pl.DataFrame({"i1": [1], "i2": [1]})
    with pytest.raises(ValueError, match="outside \\[0, 1\\]"):
        estimate(data2, spec_bad3)


def test_missing_report_counts():
    """Test 7: missing_report() correctly counts per-indicator missing values."""
    data = pl.DataFrame(
        {
            "i1": [1, None, 0, 1],  # 1 missing out of 4 -> 0.25
            "i2": [None, None, 1, 0],  # 2 missing out of 4 -> 0.50
            "i3": [1, 1, 1, 1],  # 0 missing out of 4 -> 0.00
        }
    )
    spec = Specification({"d": ["i1", "i2", "i3"]}, missing_policy="reweighting")
    res = estimate(data, spec, k=0.5)

    report = res.missing_report()
    assert isinstance(report, MissingReport)
    assert report.policy == "reweighting"
    assert report.rows_in == 4
    assert report.rows_out == 4
    assert report.dropped == 0

    per_ind = report.per_indicator
    assert isinstance(per_ind, pl.DataFrame)
    i1_row = per_ind.filter(pl.col("indicator") == "i1").to_dicts()[0]
    assert i1_row["missing"] == 1
    assert i1_row["missing_share"] == pytest.approx(0.25)

    i2_row = per_ind.filter(pl.col("indicator") == "i2").to_dicts()[0]
    assert i2_row["missing"] == 2
    assert i2_row["missing_share"] == pytest.approx(0.50)

    i3_row = per_ind.filter(pl.col("indicator") == "i3").to_dicts()[0]
    assert i3_row["missing"] == 0
    assert i3_row["missing_share"] == pytest.approx(0.00)


def test_missing_report_with_pandas_input():
    """Test pandas output conversion for missing_report()."""
    data = pd.DataFrame({"i1": [1, None]})
    spec = Specification({"d": ["i1"]}, missing_policy="treat_as_nondeprived")
    res = estimate(data, spec)
    report = res.missing_report()
    assert isinstance(report.per_indicator, pd.DataFrame)
