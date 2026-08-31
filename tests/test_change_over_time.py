"""Tests for change over time across independent waves (PLAN.md §14.6a).

The 7 mandatory tests from §14.6a:
1. Two disjoint waves: Var(Δ) = V1 + V0 to 1e-12 precision.
2. d = 1 -> ann_abs == abs and ann_rel == rel, exactly.
3. Three waves -> produced pairs: (1,2), (2,3) and (1,3), exactly, no duplicates.
4. θ̂0 = 0 -> rel and ann_rel are None, SE nan, no exception.
5. cot_year non-constant in a wave -> ValueError.
6. changes() without tvar -> ValueError ("no time variable was declared").
7. A change CI can be negative (not truncated to [0, 1]).
"""

import math
from math import isnan

import pandas as pd
import polars as pl
import pytest

from afmpi import Specification, SurveyDesign, estimate


def _make_two_wave_disjoint_data() -> pl.DataFrame:
    """Helper creating two disjoint waves (wave 1: PSUs 1..4, wave 2: PSUs 5..8)."""
    rows = []
    # Wave 1 (year 2018): 4 PSUs, 10 obs per PSU
    for psu in range(1, 5):
        for i in range(10):
            rows.append(
                {
                    "wave": "2018",
                    "year": 2018,
                    "stratum": "S1",
                    "psu": f"P{psu}",
                    "weight": 1.0,
                    "d1": 1 if (psu + i) % 2 == 0 else 0,
                    "d2": 1 if (psu + i) % 3 == 0 else 0,
                }
            )

    # Wave 2 (year 2021): 4 PSUs (disjoint PSU IDs), 10 obs per PSU
    for psu in range(5, 9):
        for i in range(10):
            rows.append(
                {
                    "wave": "2021",
                    "year": 2021,
                    "stratum": "S1",
                    "psu": f"P{psu}",
                    "weight": 1.0,
                    "d1": 1 if (psu + i) % 4 == 0 else 0,
                    "d2": 1 if (psu + i) % 2 == 0 else 0,
                }
            )

    return pl.DataFrame(rows)


def test_1_disjoint_waves_variance_sum():
    """1. Deux vagues disjointes (aucune grappe commune) : Var(Δ) = V₁ + V₀ à 1e-12."""

    df = _make_two_wave_disjoint_data()
    spec = Specification({"d1": ["d1"], "d2": ["d2"]})
    design = SurveyDesign(strata="stratum", psu="psu", weights="weight")

    # Full change estimation
    res = estimate(df, spec, design, tvar="wave", cot_year="year")
    ch = res.changes()
    if isinstance(ch, pd.DataFrame):
        ch = pl.from_pandas(ch)

    # Wave 1 and Wave 2 estimated as domains on the complete table
    res1 = res.domain("wave == '2018'")
    res2 = res.domain("wave == '2021'")

    # Check for M0, H, A
    for measure in ("M0", "H", "A"):
        abs_row = ch.filter((pl.col("measure") == measure) & (pl.col("type") == "abs")).row(
            0, named=True
        )
        se_delta = abs_row["se"]
        var_delta = se_delta**2

        se1 = res1._national_row(measure)["se"]
        se2 = res2._national_row(measure)["se"]
        var1 = se1**2
        var2 = se2**2

        assert abs(var_delta - (var1 + var2)) < 1e-12


def test_2_duration_one_identity():
    """2. d = 1 → ann_abs == abs et ann_rel == rel, exactement."""

    df = _make_two_wave_disjoint_data()
    spec = Specification({"d1": ["d1"], "d2": ["d2"]})
    design = SurveyDesign(strata="stratum", psu="psu", weights="weight")

    # Without cot_year, d=1
    res = estimate(df, spec, design, tvar="wave")
    ch = res.changes()
    if isinstance(ch, pd.DataFrame):
        ch = pl.from_pandas(ch)

    measures = ch.select(pl.col("measure").unique()).to_series().to_list()
    for m in measures:
        abs_row = ch.filter((pl.col("measure") == m) & (pl.col("type") == "abs")).row(
            0, named=True
        )
        ann_abs_row = ch.filter((pl.col("measure") == m) & (pl.col("type") == "ann_abs")).row(
            0, named=True
        )

        assert abs_row["est"] == ann_abs_row["est"]
        assert abs_row["se"] == ann_abs_row["se"]
        assert abs_row["lci"] == ann_abs_row["lci"]
        assert abs_row["uci"] == ann_abs_row["uci"]

        rel_row = ch.filter((pl.col("measure") == m) & (pl.col("type") == "rel")).row(
            0, named=True
        )
        ann_rel_row = ch.filter((pl.col("measure") == m) & (pl.col("type") == "ann_rel")).row(
            0, named=True
        )

        if rel_row["est"] is None:
            assert ann_rel_row["est"] is None
        else:
            assert abs(rel_row["est"] - ann_rel_row["est"]) < 1e-15
            assert abs(rel_row["se"] - ann_rel_row["se"]) < 1e-15
            assert abs(rel_row["lci"] - ann_rel_row["lci"]) < 1e-15
            assert abs(rel_row["uci"] - ann_rel_row["uci"]) < 1e-15


def test_3_three_waves_pairs():
    """3. Trois vagues → paires produites : (1,2), (2,3) et (1,3), exactement, sans doublon."""

    rows = []
    for wave in ("1", "2", "3"):
        for psu in range(1, 3):
            for i in range(5):
                rows.append(
                    {
                        "wave": wave,
                        "stratum": "S1",
                        "psu": f"P_{wave}_{psu}",
                        "weight": 1.0,
                        "d1": 1 if i % 2 == 0 else 0,
                    }
                )
    df = pl.DataFrame(rows)
    spec = Specification({"d1": ["d1"]})
    design = SurveyDesign(strata="stratum", psu="psu", weights="weight")

    res = estimate(df, spec, design, tvar="wave")
    ch = res.changes()
    if isinstance(ch, pd.DataFrame):
        ch = pl.from_pandas(ch)

    pairs = ch.select(pl.col("t0"), pl.col("t1")).unique(maintain_order=True).to_dicts()
    pair_tuples = [(p["t0"], p["t1"]) for p in pairs]

    assert pair_tuples == [("1", "2"), ("2", "3"), ("1", "3")]


def test_4_zero_baseline():
    """4. θ̂₀ = 0 → rel et ann_rel valent None, SE nan, pas d'exception."""

    rows = []
    # Wave 1: 0 deprivation (theta0 = 0)
    for psu in (1, 2):
        for _ in range(5):
            rows.append(
                {
                    "wave": "1",
                    "stratum": "S1",
                    "psu": f"P1_{psu}",
                    "weight": 1.0,
                    "d1": 0,
                }
            )

    # Wave 2: some deprivation (theta1 > 0)
    for psu in (3, 4):
        for _ in range(5):
            rows.append(
                {
                    "wave": "2",
                    "stratum": "S1",
                    "psu": f"P2_{psu}",
                    "weight": 1.0,
                    "d1": 1,
                }
            )

    df = pl.DataFrame(rows)
    spec = Specification({"d1": ["d1"]})
    design = SurveyDesign(strata="stratum", psu="psu", weights="weight")

    res = estimate(df, spec, design, tvar="wave")
    ch = res.changes()
    if isinstance(ch, pd.DataFrame):
        ch = pl.from_pandas(ch)

    rel_rows = ch.filter(pl.col("type").is_in(["rel", "ann_rel"]))
    for r in rel_rows.iter_rows(named=True):
        assert r["est"] is None
        assert isnan(r["se"])
        assert isnan(r["lci"])
        assert isnan(r["uci"])


def test_5_cot_year_non_constant():
    """5. cot_year non constant dans une vague → ValueError."""

    df = pl.DataFrame(
        {
            "wave": ["2018", "2018", "2021", "2021"],
            "year": [2018, 2019, 2021, 2021],  # 2018 has non-constant year!
            "stratum": ["S1", "S1", "S1", "S1"],
            "psu": ["P1", "P2", "P3", "P4"],
            "weight": [1.0, 1.0, 1.0, 1.0],
            "d1": [1, 0, 1, 0],
        }
    )
    spec = Specification({"d1": ["d1"]})
    design = SurveyDesign(strata="stratum", psu="psu", weights="weight")

    with pytest.raises(ValueError, match="cot_year.*not constant"):
        estimate(df, spec, design, tvar="wave", cot_year="year")


def test_6_changes_without_tvar():
    """6. changes() sans tvar déclaré → ValueError."""

    df = _make_two_wave_disjoint_data()
    spec = Specification({"d1": ["d1"]})
    design = SurveyDesign(strata="stratum", psu="psu", weights="weight")

    res = estimate(df, spec, design)  # no tvar!
    with pytest.raises(ValueError, match="no time variable was declared"):
        res.changes()


def test_7_negative_change_interval():
    """7. Un IC de changement peut être négatif (non tronqué à [0, 1])."""

    rows = []
    # Wave 1: high deprivation (M0 high)
    for psu in (1, 2):
        for _ in range(10):
            rows.append(
                {
                    "wave": "1",
                    "stratum": "S1",
                    "psu": f"P1_{psu}",
                    "weight": 1.0,
                    "d1": 1,
                }
            )

    # Wave 2: low deprivation (M0 low) -> Delta < 0
    for psu in (3, 4):
        for i in range(10):
            rows.append(
                {
                    "wave": "2",
                    "stratum": "S1",
                    "psu": f"P2_{psu}",
                    "weight": 1.0,
                    "d1": 1 if i < 2 else 0,
                }
            )

    df = pl.DataFrame(rows)
    spec = Specification({"d1": ["d1"]})
    design = SurveyDesign(strata="stratum", psu="psu", weights="weight")

    res = estimate(df, spec, design, tvar="wave", ci_method="logit")
    ch = res.changes()
    if isinstance(ch, pd.DataFrame):
        ch = pl.from_pandas(ch)

    abs_row = ch.filter((pl.col("measure") == "M0") & (pl.col("type") == "abs")).row(
        0, named=True
    )

    assert abs_row["est"] < 0
    # Lower bound must be strictly negative, not truncated to 0!
    assert abs_row["lci"] < 0
    # uci is also less than 0 or valid float
    assert not math.isnan(abs_row["uci"])


def test_lazy_path_with_tvar_raises_not_implemented():
    """Point 2: tvar with lazy=True raises explicit NotImplementedError."""
    df = _make_two_wave_disjoint_data()
    spec = Specification({"d1": ["d1"], "d2": ["d2"]})
    design = SurveyDesign(strata="stratum", psu="psu", weights="weight")

    with pytest.raises(NotImplementedError, match="Changes over time .* not supported on lazy"):
        estimate(df, spec, design, tvar="wave", lazy=True)


def test_lazy_path_with_nonexistent_tvar_raises_value_error():
    """Point 2: nonexistent tvar with lazy=True raises ValueError on column absence."""
    df = _make_two_wave_disjoint_data()
    spec = Specification({"d1": ["d1"], "d2": ["d2"]})
    design = SurveyDesign(strata="stratum", psu="psu", weights="weight")

    with pytest.raises(ValueError, match="tvar column 'nonexistent_col' is absent"):
        estimate(df, spec, design, tvar="nonexistent_col", lazy=True)
