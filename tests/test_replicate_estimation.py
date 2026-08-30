"""Tests for ReplicateDesign: JK1 and JKn (PLAN.md §14.5a)."""

from __future__ import annotations

from math import isnan
from unittest.mock import patch

import pandas as pd
import polars as pl
import pytest

from afmpi import (
    EstimationResult,
    ReplicateDesign,
    Specification,
    SurveyDesign,
    estimate,
)
from afmpi.replicate_estimation import (
    generate_replicate_weights,
    replicate_totals,
)


@pytest.fixture
def sample_stratified_data() -> pd.DataFrame:
    """Stratified cluster sample with 2 strata and 2 PSUs per stratum."""

    data = []
    # Stratum 1: PSUs P1, P2
    for psu in ("P1", "P2"):
        for i in range(10):
            data.append(
                {
                    "stratum": "S1",
                    "psu": psu,
                    "weight": 2.0,
                    "region": "North" if i < 5 else "South",
                    "d1": 1 if i % 2 == 0 else 0,
                    "d2": 1 if i % 3 == 0 else 0,
                }
            )
    # Stratum 2: PSUs P3, P4
    for psu in ("P3", "P4"):
        for i in range(10):
            data.append(
                {
                    "stratum": "S2",
                    "psu": psu,
                    "weight": 3.0,
                    "region": "North" if i < 5 else "South",
                    "d1": 1 if i % 4 == 0 else 0,
                    "d2": 1 if i % 2 == 0 else 0,
                }
            )
    return pd.DataFrame(data)


# -----------------------------------------------------------------------------
# Test 1: JKn variance vs Taylor variance identity
# -----------------------------------------------------------------------------


def test_jkn_variance_matches_taylor_variance(sample_stratified_data: pd.DataFrame):
    """Test 1: JKn replicate variance matches Taylor linearization variance.

    For H and M0 (weighted means/totals), JKn variance is mathematically
    identical to Taylor linearization variance on a stratified cluster design.
    For A (ratio), JKn is asymptotically equivalent (relative tolerance 1e-6).
    """

    spec = Specification(
        dimensions={"dim1": ("d1",), "dim2": ("d2",)},
        weights={"d1": 0.5, "d2": 0.5},
    )

    taylor_design = SurveyDesign(strata="stratum", psu="psu", weights="weight")
    rep_design = ReplicateDesign(
        method="JKn", strata="stratum", psu="psu", weights="weight"
    )

    res_taylor = estimate(sample_stratified_data, spec, taylor_design, k=0.3)
    res_rep = estimate(sample_stratified_data, spec, rep_design, k=0.3)

    # Point estimates must be identical
    assert res_taylor.H == pytest.approx(res_rep.H, abs=1e-12)
    assert res_taylor.M0 == pytest.approx(res_rep.M0, abs=1e-12)
    assert res_taylor.A == pytest.approx(res_rep.A, abs=1e-12)

    # Standard errors
    se_taylor = (
        res_taylor.se().set_index("measure")["se"]
        if isinstance(res_taylor.se(), pd.DataFrame)
        else res_taylor.se()
    )
    se_rep = (
        res_rep.se().set_index("measure")["se"]
        if isinstance(res_rep.se(), pd.DataFrame)
        else res_rep.se()
    )

    # Exact equality for H and M0 (up to floating point precision abs=1e-8)
    assert float(se_rep.loc["H"]) == pytest.approx(float(se_taylor.loc["H"]), abs=1e-8)
    assert float(se_rep.loc["M0"]) == pytest.approx(float(se_taylor.loc["M0"]), abs=1e-8)

    # Close match for A (ratio estimand, rel=1e-6)
    assert float(se_rep.loc["A"]) == pytest.approx(float(se_taylor.loc["A"]), rel=1e-6)


# -----------------------------------------------------------------------------
# Test 2: Hardcoded replicate weights & hand calculation
# -----------------------------------------------------------------------------


def test_hand_calculated_replicate_variance():
    """Test 2: Hardcoded replicate weights match exact hand calculation.

    Hand-calculated model:
    4 rows, 2 indicators (equal weight 0.5), cutoff k=0.5.
    Base weights w = [2.0, 3.0, 1.0, 4.0] (population N = 10.0).
    Scores c_i = [1.0, 0.5, 0.0, 1.0].
    Poor indicators 1(c_i >= 0.5) = [1, 1, 0, 1].
    Censored scores c_i(0.5) = [1.0, 0.5, 0.0, 1.0].

    Point estimates:
      H  = (2*1 + 3*1 + 1*0 + 4*1) / 10 = 9 / 10 = 0.9
      M0 = (2*1 + 3*0.5 + 1*0 + 4*1) / 10 = 7.5 / 10 = 0.75
      A  = M0 / H = 0.75 / 0.9 = 5 / 6 = 0.8333333333333334

    3 Replicates (scale=0.5, rscales=(1.0, 1.0, 1.0), mse=True):
      rep1 = [0.0, 4.5, 1.5, 6.0] -> N1=12.0, H1=0.875, M0_1=0.6875, A1=11/14
      rep2 = [3.0, 0.0, 1.5, 6.0] -> N2=10.5, H2=6/7,   M0_2=6/7,    A2=1.0
      rep3 = [3.0, 4.5, 0.0, 0.0] -> N3=7.5,  H3=1.0,   M0_3=0.70,   A3=0.70

    Variances (scale * sum((theta_r - theta_hat)^2)):
      V(H)  = 0.5 * ((0.875 - 0.9)^2 + (6/7 - 0.9)^2 + (1.0 - 0.9)^2)
            = 0.0062308673469387755
      V(M0) = 0.5 * ((0.6875 - 0.75)^2 + (6/7 - 0.75)^2 + (0.70 - 0.75)^2)
            = 0.008942920918367347
      V(A)  = 0.5 * ((11/14 - 5/6)^2 + (1.0 - 5/6)^2 + (0.70 - 5/6)^2)
            = 0.02391156462585034
    """

    df = pd.DataFrame(
        {
            "w": [2.0, 3.0, 1.0, 4.0],
            "d1": [1, 1, 0, 1],
            "d2": [1, 0, 0, 1],
            "repw1": [0.0, 4.5, 1.5, 6.0],
            "repw2": [3.0, 0.0, 1.5, 6.0],
            "repw3": [3.0, 4.5, 0.0, 0.0],
        }
    )

    spec = Specification(
        dimensions={"dim1": ("d1",), "dim2": ("d2",)},
        weights={"d1": 0.5, "d2": 0.5},
    )

    design = ReplicateDesign(
        weights="w",
        replicate_weights=("repw1", "repw2", "repw3"),
        scale=0.5,
        rscales=(1.0, 1.0, 1.0),
        mse=True,
        combined_weights=True,
    )

    res = estimate(df, spec, design, k=0.5)

    assert res.H == pytest.approx(0.9, abs=1e-12)
    assert res.M0 == pytest.approx(0.75, abs=1e-12)
    assert res.A == pytest.approx(5 / 6, abs=1e-12)

    se_df = res.se().set_index("measure")
    se_H = float(se_df.loc["H", "se"])
    se_M0 = float(se_df.loc["M0", "se"])
    se_A = float(se_df.loc["A", "se"])

    expected_v_H = 0.0062308673469387755
    expected_v_M0 = 0.008942920918367347
    expected_v_A = 0.02391156462585034

    assert se_H**2 == pytest.approx(expected_v_H, abs=1e-12)
    assert se_M0**2 == pytest.approx(expected_v_M0, abs=1e-12)
    assert se_A**2 == pytest.approx(expected_v_A, abs=1e-12)


# -----------------------------------------------------------------------------
# Test 3: mse=True vs mse=False
# -----------------------------------------------------------------------------


def test_mse_true_vs_mse_false():
    """Test 3: mse=True and mse=False give different, exact formula values.

    Using the dataset from Test 2:
    - mse=True  centers at point estimate theta_hat:
        V_mse_True(H) = 0.0062308673469387755
    - mse=False centers at mean of replicates theta_bar = 51 / 56:
        V_mse_False(H) = 19 / 3136 = 0.006058673469387755
    """

    df = pd.DataFrame(
        {
            "w": [2.0, 3.0, 1.0, 4.0],
            "d1": [1, 1, 0, 1],
            "d2": [1, 0, 0, 1],
            "repw1": [0.0, 4.5, 1.5, 6.0],
            "repw2": [3.0, 0.0, 1.5, 6.0],
            "repw3": [3.0, 4.5, 0.0, 0.0],
        }
    )

    spec = Specification(
        dimensions={"dim1": ("d1",), "dim2": ("d2",)},
        weights={"d1": 0.5, "d2": 0.5},
    )

    design_mse_true = ReplicateDesign(
        weights="w",
        replicate_weights=("repw1", "repw2", "repw3"),
        scale=0.5,
        rscales=(1.0, 1.0, 1.0),
        mse=True,
    )

    design_mse_false = ReplicateDesign(
        weights="w",
        replicate_weights=("repw1", "repw2", "repw3"),
        scale=0.5,
        rscales=(1.0, 1.0, 1.0),
        mse=False,
    )

    res_true = estimate(df, spec, design_mse_true, k=0.5)
    res_false = estimate(df, spec, design_mse_false, k=0.5)

    se_true_H = float(res_true.se().set_index("measure").loc["H", "se"])
    se_false_H = float(res_false.se().set_index("measure").loc["H", "se"])

    v_true_H = se_true_H**2
    v_false_H = se_false_H**2

    assert v_true_H != pytest.approx(v_false_H, abs=1e-6)
    assert v_true_H == pytest.approx(0.0062308673469387755, abs=1e-12)
    assert v_false_H == pytest.approx(19 / 3136, abs=1e-12)


# -----------------------------------------------------------------------------
# Test 4: combined_weights=False equivalence
# -----------------------------------------------------------------------------


def test_combined_weights_false_equivalence():
    """Test 4: combined_weights=False with factors=w^(r)/w gives identical results."""

    df = pd.DataFrame(
        {
            "w": [2.0, 3.0, 1.0, 4.0],
            "d1": [1, 1, 0, 1],
            "d2": [1, 0, 0, 1],
            "repw1": [0.0, 4.5, 1.5, 6.0],
            "repw2": [3.0, 0.0, 1.5, 6.0],
            "repw3": [3.0, 4.5, 0.0, 0.0],
        }
    )

    df["factor1"] = df["repw1"] / df["w"]
    df["factor2"] = df["repw2"] / df["w"]
    df["factor3"] = df["repw3"] / df["w"]

    spec = Specification(
        dimensions={"dim1": ("d1",), "dim2": ("d2",)},
        weights={"d1": 0.5, "d2": 0.5},
    )

    design_combined = ReplicateDesign(
        weights="w",
        replicate_weights=("repw1", "repw2", "repw3"),
        scale=0.5,
        rscales=(1.0, 1.0, 1.0),
        combined_weights=True,
    )

    design_factors = ReplicateDesign(
        weights="w",
        replicate_weights=("factor1", "factor2", "factor3"),
        scale=0.5,
        rscales=(1.0, 1.0, 1.0),
        combined_weights=False,
    )

    res_combined = estimate(df, spec, design_combined, k=0.5)
    res_factors = estimate(df, spec, design_factors, k=0.5)

    df_combined = res_combined.estimates()
    df_factors = res_factors.estimates()

    pd.testing.assert_frame_equal(df_combined, df_factors)


# -----------------------------------------------------------------------------
# Test 5: batch_size invariance
# -----------------------------------------------------------------------------


def test_batch_size_invariance(sample_stratified_data: pd.DataFrame):
    """Test 5: batch_size=1, 7, 1000 produce bit-for-bit identical results."""

    spec = Specification(
        dimensions={"dim1": ("d1",), "dim2": ("d2",)},
        weights={"d1": 0.5, "d2": 0.5},
    )

    rep_design = ReplicateDesign(
        method="JKn", strata="stratum", psu="psu", weights="weight"
    )

    matrix = estimate(sample_stratified_data, spec, rep_design, k=0.3)

    # Test replicate_totals directly with different batch_sizes
    frame_work, repw_cols, scale, rscales = generate_replicate_weights(
        matrix._matrix.frame, rep_design
    )
    from afmpi.replicate_estimation import replicate_weight_expressions

    exprs = replicate_weight_expressions(rep_design, frame_work)

    from afmpi.estimands import build as build_estimands

    estimands = build_estimands(spec, 0.3)

    tot1 = replicate_totals(frame_work, estimands, exprs, batch_size=1)
    tot7 = replicate_totals(frame_work, estimands, exprs, batch_size=7)
    tot1000 = replicate_totals(frame_work, estimands, exprs, batch_size=1000)

    assert tot1 == tot7
    assert tot7 == tot1000


# -----------------------------------------------------------------------------
# Test 6: over= breakdown decomposability and O(R) scans count
# -----------------------------------------------------------------------------


def test_over_decomposability_and_scan_count(sample_stratified_data: pd.DataFrame):
    """Test 6: over= breakdown satisfies decomposability and runs O(R) scans."""

    spec = Specification(
        dimensions={"dim1": ("d1",), "dim2": ("d2",)},
        weights={"d1": 0.5, "d2": 0.5},
    )

    rep_design = ReplicateDesign(
        method="JKn", strata="stratum", psu="psu", weights="weight"
    )

    with patch("afmpi.estimation.replicate_totals", wraps=replicate_totals) as spy:
        res = estimate(
            sample_stratified_data, spec, rep_design, k=0.3, over="region"
        )

        # Decomposability audit must pass
        decomp = res.decomposition()
        assert (decomp["error"] <= 1e-9).all()

        # Check call count of replicate_totals:
        # 1 call for national totals (group_column=None) +
        # 1 call for region over (group_column='region')
        # Total calls = 2 (independent of number of regions)
        assert spy.call_count == 2


# -----------------------------------------------------------------------------
# Test 7: m_h = 1 in JKn raises ValueError naming the stratum
# -----------------------------------------------------------------------------


def test_jkn_single_psu_stratum_raises_value_error():
    """Test 7: m_h = 1 in JKn raises ValueError naming the stratum."""

    data = pd.DataFrame(
        {
            "stratum": ["S1", "S1", "S2"],
            "psu": ["P1", "P2", "P3"],  # S2 has only 1 PSU (P3)
            "weight": [1.0, 1.0, 1.0],
            "d1": [1, 0, 1],
            "d2": [0, 1, 0],
        }
    )

    spec = Specification(
        dimensions={"dim1": ("d1",), "dim2": ("d2",)},
        weights={"d1": 0.5, "d2": 0.5},
    )

    rep_design = ReplicateDesign(
        method="JKn", strata="stratum", psu="psu", weights="weight"
    )

    with pytest.raises(ValueError) as exc_info:
        estimate(data, spec, rep_design, k=0.5)

    assert "S2" in str(exc_info.value)


# -----------------------------------------------------------------------------
# Test 8: Undefined ratio in replicate gives NaN variance
# -----------------------------------------------------------------------------


def test_undefined_replicate_ratio_gives_nan_variance():
    """Test 8: Undefined ratio in a replicate yields NaN variance for A."""

    # 3 rows, row 1 poor, row 2-3 non-poor
    df = pd.DataFrame(
        {
            "w": [1.0, 1.0, 1.0],
            "d1": [1, 0, 0],
            "d2": [1, 0, 0],
            "repw1": [1.0, 1.0, 1.0],  # normal replicate
            "repw2": [0.0, 1.0, 1.0],  # row 1 has weight 0 -> nobody poor!
        }
    )

    spec = Specification(
        dimensions={"dim1": ("d1",), "dim2": ("d2",)},
        weights={"d1": 0.5, "d2": 0.5},
    )

    design = ReplicateDesign(
        weights="w",
        replicate_weights=("repw1", "repw2"),
        scale=0.5,
        rscales=(1.0, 1.0),
    )

    res = estimate(df, spec, design, k=0.5)
    se_df = res.se().set_index("measure")

    # H and M0 have valid numeric standard errors
    se_H = float(se_df.loc["H", "se"])
    se_M0 = float(se_df.loc["M0", "se"])
    assert not isnan(se_H)
    assert not isnan(se_M0)

    # A has undefined denominator in replicate 2, so se(A) is NaN
    se_A = float(se_df.loc["A", "se"])
    assert isnan(se_A)

    # Degrees of freedom is still R - 1 = 2 - 1 = 1 (replicate was not dropped)
    degf_df = res.degf()
    assert int(degf_df["psus"].iloc[0]) == 2


# -----------------------------------------------------------------------------
# Phase 5b tests: BRR and Fay BRR (PLAN.md §14.5b)
# -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("num_strata", "expected_replicates"),
    [(3, 4), (4, 8), (7, 8), (8, 16)],
)
def test_hadamard_order_selection_rule(num_strata: int, expected_replicates: int):
    """Test #3: Ordre choisi H=3 -> R=4 ; H=4 -> R=8 ; H=7 -> R=8 ; H=8 -> R=16."""
    rows = []
    for h in range(1, num_strata + 1):
        for p in (1, 2):
            rows.append(
                {
                    "stratum": f"S{h}",
                    "psu": f"P{h}_{p}",
                    "w": 1.0,
                    "d1": 1,
                    "d2": 0,
                }
            )
    df = pl.DataFrame(rows)
    rd = ReplicateDesign(weights="w", strata="stratum", psu="psu", method="BRR")
    _, repw_cols, _, _ = generate_replicate_weights(df, rd)
    assert len(repw_cols) == expected_replicates


def test_fay_brr_fay_0_matches_brr_exactly():
    """Test #4: Fay_BRR(fay=0.0) donne exactement BRR (au bit près)."""
    data = []
    for h in range(1, 4):
        for p in (1, 2):
            for i in range(5):
                data.append(
                    {
                        "strata": f"S{h}",
                        "psu": f"P{h}_{p}",
                        "weight": 2.0,
                        "d1": i % 2,
                        "d2": (i + 1) % 2,
                    }
                )
    df = pl.DataFrame(data)

    rd_brr = ReplicateDesign(
        weights="weight", strata="strata", psu="psu", method="BRR"
    )
    rd_fay0 = ReplicateDesign(
        weights="weight", strata="strata", psu="psu", method="Fay_BRR", fay=0.0
    )

    frame_brr, cols_brr, scale_brr, rscales_brr = generate_replicate_weights(
        df, rd_brr
    )
    frame_fay, cols_fay, scale_fay, rscales_fay = generate_replicate_weights(
        df, rd_fay0
    )

    assert cols_brr == cols_fay
    assert scale_brr == scale_fay
    assert rscales_brr == rscales_fay
    for col in cols_brr:
        assert (frame_brr[col] == frame_fay[col]).all()

    spec = Specification(
        dimensions={"d1": ("d1",), "d2": ("d2",)}, weights={"d1": 0.5, "d2": 0.5}
    )
    res_brr = estimate(df, spec, rd_brr, k=0.5)
    res_fay = estimate(df, spec, rd_fay0, k=0.5)

    assert res_brr.H == res_fay.H
    assert res_brr.M0 == res_fay.M0
    assert (
        res_brr.se()["se"].to_list() == res_fay.se()["se"].to_list()
    )


def test_brr_variance_matches_taylor_variance_for_2psu_strata():
    """Test #5: Sur un plan à H strates x 2 PSU, BRR et la linéarisation donnent la même variance pour M0 à 1e-10."""
    data = []
    for h in range(1, 4):
        for p in (1, 2):
            for i in range(10):
                data.append(
                    {
                        "stratum": f"S{h}",
                        "psu": f"P{h}_{p}",
                        "weight": 1.0,
                        "d1": 1 if (p == 1 and i < 8) else (1 if i < 2 else 0),
                        "d2": 1 if (p == 1 and i < 6) else (1 if i < 4 else 0),
                    }
                )
    df = pl.DataFrame(data)

    spec = Specification(
        dimensions={"d1": ("d1",), "d2": ("d2",)}, weights={"d1": 0.5, "d2": 0.5}
    )

    taylor_design = SurveyDesign(strata="stratum", psu="psu", weights="weight")
    brr_design = ReplicateDesign(
        method="BRR", strata="stratum", psu="psu", weights="weight"
    )

    res_taylor = estimate(df, spec, taylor_design, k=0.3)
    res_brr = estimate(df, spec, brr_design, k=0.3)

    se_taylor_M0 = res_taylor.se().filter(pl.col("measure") == "M0")["se"].item()
    se_brr_M0 = res_brr.se().filter(pl.col("measure") == "M0")["se"].item()

    var_taylor = se_taylor_M0**2
    var_brr = se_brr_M0**2
    diff = abs(var_brr - var_taylor)

    assert diff < 1e-10


@pytest.mark.parametrize("num_psu", [1, 3])
def test_brr_invalid_psu_count_raises_value_error(num_psu: int):
    """Test #6: Une strate à 1 ou 3 PSU -> ValueError nommant la strate."""
    rows = []
    # Stratum S1 has 2 PSUs
    for p in (1, 2):
        rows.append(
            {"stratum": "S1", "psu": f"P1_{p}", "w": 1.0, "d1": 1, "d2": 0}
        )
    # Stratum S2 has num_psu PSUs (1 or 3)
    for p in range(1, num_psu + 1):
        rows.append(
            {"stratum": "S2", "psu": f"P2_{p}", "w": 1.0, "d1": 0, "d2": 1}
        )
    df = pl.DataFrame(rows)

    rd = ReplicateDesign(weights="w", strata="stratum", psu="psu", method="BRR")

    with pytest.raises(ValueError) as exc_info:
        generate_replicate_weights(df, rd)

    assert "S2" in str(exc_info.value)

