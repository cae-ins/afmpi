"""Tests for Phase 6b: panels and overlapping samples (PLAN.md §14.6b)."""

import pandas as pd
import polars as pl
import pytest

from afmpi import Specification, SurveyDesign, ReplicateDesign, estimate


def _make_panel_data():
    """Construct a 2-wave panel dataset with 1 stratum, 2 PSUs (c1, c2), 4 households."""

    rows_t0 = [
        {"wave": "t0", "stratum": "s1", "cluster": "c1", "hhid": "h1", "d1": 1, "d2": 1, "d3": 1, "w": 1.0},
        {"wave": "t0", "stratum": "s1", "cluster": "c1", "hhid": "h2", "d1": 1, "d2": 0, "d3": 1, "w": 1.0},
        {"wave": "t0", "stratum": "s1", "cluster": "c2", "hhid": "h3", "d1": 0, "d2": 0, "d3": 0, "w": 1.0},
        {"wave": "t0", "stratum": "s1", "cluster": "c2", "hhid": "h4", "d1": 0, "d2": 1, "d3": 0, "w": 1.0},
    ]

    # Perfect positive correlation between waves
    rows_t1_pos = [
        {"wave": "t1", "stratum": "s1", "cluster": "c1", "hhid": "h1", "d1": 1, "d2": 1, "d3": 1, "w": 1.0},
        {"wave": "t1", "stratum": "s1", "cluster": "c1", "hhid": "h2", "d1": 1, "d2": 1, "d3": 0, "w": 1.0},
        {"wave": "t1", "stratum": "s1", "cluster": "c2", "hhid": "h3", "d1": 0, "d2": 0, "d3": 0, "w": 1.0},
        {"wave": "t1", "stratum": "s1", "cluster": "c2", "hhid": "h4", "d1": 0, "d2": 0, "d3": 1, "w": 1.0},
    ]

    # Constructed negative correlation between waves
    rows_t1_neg = [
        {"wave": "t1", "stratum": "s1", "cluster": "c1", "hhid": "h1", "d1": 0, "d2": 0, "d3": 0, "w": 1.0},
        {"wave": "t1", "stratum": "s1", "cluster": "c1", "hhid": "h2", "d1": 0, "d2": 0, "d3": 0, "w": 1.0},
        {"wave": "t1", "stratum": "s1", "cluster": "c2", "hhid": "h3", "d1": 1, "d2": 1, "d3": 1, "w": 1.0},
        {"wave": "t1", "stratum": "s1", "cluster": "c2", "hhid": "h4", "d1": 1, "d2": 1, "d3": 1, "w": 1.0},
    ]

    df_pos = pl.DataFrame(rows_t0 + rows_t1_pos)
    df_neg = pl.DataFrame(rows_t0 + rows_t1_neg)
    return df_pos, df_neg


def test_perfect_panel_variance_reduction():
    """Test 1 (§14.6b): Perfect panel -> Var(Delta) < V1 + V0, with exact difference = 2*C."""

    df_pos, _ = _make_panel_data()
    spec = Specification({"d1": ["d1"], "d2": ["d2"], "d3": ["d3"]})
    design = SurveyDesign(strata="stratum", psu="cluster", weights="w")

    res = estimate(df_pos, spec, design, tvar="wave", panel_id="hhid", overlap="auto")
    changes = res.changes()

    # Filter H at k=1/3, type='abs'
    h_abs = changes.filter((pl.col("measure") == "H") & (pl.col("type") == "abs"))
    se_delta = h_abs.select("se").item()
    var_delta = se_delta ** 2

    # Calculate V0, V1 and C by hand for H at k=1/3:
    # t0: h1 (poor=1), h2 (poor=1), h3 (poor=0), h4 (poor=1). H_t0 = 3/4 = 0.75.
    # u_c1^(0) = (2 - 2*0.75)/4 = 0.125, u_c2^(0) = (1 - 2*0.75)/4 = -0.125.
    # V0 = 2 * (0.125^2 + (-0.125)^2) = 0.0625.
    # t1: h1 (poor=1), h2 (poor=1), h3 (poor=0), h4 (poor=1). H_t1 = 3/4 = 0.75.
    # u_c1^(1) = 0.125, u_c2^(1) = -0.125.
    # V1 = 0.0625.
    # C = 2 * (0.125*0.125 + (-0.125)*(-0.125)) = 0.0625.
    v0_hand = 0.0625
    v1_hand = 0.0625
    c_hand = 0.0625

    assert var_delta < (v1_hand + v0_hand)
    assert abs(var_delta - (v1_hand + v0_hand - 2.0 * c_hand)) < 1e-12
    assert abs((v1_hand + v0_hand) - var_delta - 2.0 * c_hand) < 1e-12


def test_constructed_negative_correlation():
    """Test 2 (§14.6b): Negative correlation -> Var(Delta) > V1 + V0."""

    _, df_neg = _make_panel_data()
    spec = Specification({"d1": ["d1"], "d2": ["d2"], "d3": ["d3"]})
    design = SurveyDesign(strata="stratum", psu="cluster", weights="w")

    res = estimate(df_neg, spec, design, tvar="wave", panel_id="hhid", overlap="auto")
    changes = res.changes()

    h_abs = changes.filter((pl.col("measure") == "H") & (pl.col("type") == "abs"))
    se_delta = h_abs.select("se").item()
    var_delta = se_delta ** 2

    # Hand values:
    # t0: H_t0 = 0.75, u_c1^(0) = 0.125, u_c2^(0) = -0.125, V0 = 0.0625.
    # t1: h1, h2 poor=0; h3, h4 poor=1. H_t1 = 0.5.
    # u_c1^(1) = (0 - 2*0.5)/4 = -0.25, u_c2^(1) = (2 - 2*0.5)/4 = +0.25.
    # V1 = 2 * ((-0.25)^2 + (0.25)^2) = 0.25.
    # C = 2 * (0.125*(-0.25) + (-0.125)*(0.25)) = -0.125.
    # Var(Delta) = V1 + V0 - 2*C = 0.25 + 0.0625 - 2*(-0.125) = 0.5625.
    v0_hand = 0.0625
    v1_hand = 0.25
    c_hand = -0.125
    expected_var_delta = v1_hand + v0_hand - 2.0 * c_hand  # 0.5625

    assert var_delta > (v1_hand + v0_hand)
    assert abs(var_delta - expected_var_delta) < 1e-12


def test_overlap_independent_forces_zero_covariance():
    """Test 3 (§14.6b): overlap='independent' on panel data gives exactly V1 + V0 (full design) and logs diagnostic."""

    df_pos, _ = _make_panel_data()
    spec = Specification({"d1": ["d1"], "d2": ["d2"], "d3": ["d3"]})
    design = SurveyDesign(strata="stratum", psu="cluster", weights="w")

    res = estimate(df_pos, spec, design, tvar="wave", panel_id="hhid", overlap="independent")
    changes = res.changes()

    h_abs = changes.filter((pl.col("measure") == "H") & (pl.col("type") == "abs"))
    se_delta = h_abs.select("se").item()
    var_delta = se_delta ** 2

    # Under 4 independent clusters (m=4), m/(m-1) = 4/3.
    # v0_full = (4/3) * (0.015625 + 0.015625) = 1/24 = 0.04166666666666667
    # v1_full = (4/3) * (0.015625 + 0.015625) = 1/24 = 0.04166666666666667
    # var_delta = v0_full + v1_full = 1/12 = 0.08333333333333333
    v0_full = 4 / 3 * 0.03125
    v1_full = 4 / 3 * 0.03125

    assert abs(var_delta - (v1_full + v0_full)) < 1e-12

    diags = res.diagnostics()
    if isinstance(diags, pd.DataFrame):
        time_rows = diags[diags["topic"] == "time"]
        assert len(time_rows) > 0
        assert time_rows.iloc[0]["decision"] == "independent"
        assert "deliberately ignored" in time_rows.iloc[0]["detail"]
    else:
        time_rows = diags.filter(pl.col("topic") == "time")
        assert time_rows.height > 0
        assert time_rows.select("decision").item() == "independent"
        assert "deliberately ignored" in time_rows.select("detail").item()


def test_overlap_panel_without_overlap_raises_error():
    """Test 4 (§14.6b): overlap='panel' without overlap raises ValueError."""

    # Disjoint waves (different clusters and hhids)
    df_no_overlap = pl.DataFrame([
        {"wave": "t0", "stratum": "s1", "cluster": "c1", "hhid": "h1", "d1": 1, "d2": 1, "d3": 1, "w": 1.0},
        {"wave": "t0", "stratum": "s1", "cluster": "c2", "hhid": "h2", "d1": 0, "d2": 0, "d3": 0, "w": 1.0},
        {"wave": "t1", "stratum": "s1", "cluster": "c3", "hhid": "h3", "d1": 1, "d2": 0, "d3": 1, "w": 1.0},
        {"wave": "t1", "stratum": "s1", "cluster": "c4", "hhid": "h4", "d1": 0, "d2": 1, "d3": 0, "w": 1.0},
    ])
    spec = Specification({"d1": ["d1"], "d2": ["d2"], "d3": ["d3"]})
    design = SurveyDesign(strata="stratum", psu="cluster", weights="w")

    with pytest.raises(ValueError, match="overlap='panel' was requested but no unit is shared between waves"):
        estimate(df_no_overlap, spec, design, tvar="wave", panel_id="hhid", overlap="panel")


def test_overlap_auto_without_overlap_retains_independent_regime():
    """Test 5 (§14.6b): overlap='auto' without overlap logs independent regime."""

    df_no_overlap = pl.DataFrame([
        {"wave": "t0", "stratum": "s1", "cluster": "c1", "hhid": "h1", "d1": 1, "d2": 1, "d3": 1, "w": 1.0},
        {"wave": "t0", "stratum": "s1", "cluster": "c2", "hhid": "h2", "d1": 0, "d2": 0, "d3": 0, "w": 1.0},
        {"wave": "t1", "stratum": "s1", "cluster": "c3", "hhid": "h3", "d1": 1, "d2": 0, "d3": 1, "w": 1.0},
        {"wave": "t1", "stratum": "s1", "cluster": "c4", "hhid": "h4", "d1": 0, "d2": 1, "d3": 0, "w": 1.0},
    ])
    spec = Specification({"d1": ["d1"], "d2": ["d2"], "d3": ["d3"]})
    design = SurveyDesign(strata="stratum", psu="cluster", weights="w")

    res = estimate(df_no_overlap, spec, design, tvar="wave", panel_id="hhid", overlap="auto")
    diags = res.diagnostics()

    if isinstance(diags, pd.DataFrame):
        time_rows = diags[diags["topic"] == "time"]
        assert len(time_rows) > 0
        assert time_rows.iloc[0]["decision"] == "independent"
        assert "no unit shared between waves" in time_rows.iloc[0]["detail"]
    else:
        time_rows = diags.filter(pl.col("topic") == "time")
        assert time_rows.height > 0
        assert time_rows.select("decision").item() == "independent"
        assert "no unit shared between waves" in time_rows.select("detail").item()


def test_replicate_design_divergent_weights_raises_error():
    """Test 6 (§14.6b): Replicate design with divergent replicate columns between waves raises ValueError."""

    df_rep = pl.DataFrame([
        {"wave": "t0", "d1": 1, "d2": 1, "d3": 1, "w": 1.0, "w_rep1": 1.1, "w_rep2": 0.9},
        {"wave": "t0", "d1": 0, "d2": 0, "d3": 0, "w": 1.0, "w_rep1": 0.9, "w_rep2": 1.1},
        {"wave": "t1", "d1": 1, "d2": 0, "d3": 1, "w": 1.0, "w_rep1": 0.0, "w_rep2": 0.0},
        {"wave": "t1", "d1": 0, "d2": 1, "d3": 0, "w": 1.0, "w_rep1": 0.0, "w_rep2": 0.0},
    ])
    spec = Specification({"d1": ["d1"], "d2": ["d2"], "d3": ["d3"]})
    rep_design = ReplicateDesign(weights="w", replicate_weights=["w_rep1", "w_rep2"], method="BRR")

    with pytest.raises(ValueError, match="Replicate design weights or configuration diverge between waves"):
        estimate(df_rep, spec, rep_design, tvar="wave")
