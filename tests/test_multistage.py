"""Tests for multi-stage designs and FPC (PLAN.md §14.4a)."""

import pandas as pd
import pytest

from afmpi import Specification, Stage, SurveyDesign, estimate


@pytest.fixture
def sample_data() -> pd.DataFrame:
    rows = []
    for h in [1, 2]:
        for psu in [1, 2]:
            for ssu in [1, 2]:
                for hh in [1, 2]:
                    rows.append(
                        {
                            "strata_1": f"H{h}",
                            "psu_1": f"P{h}_{psu}",
                            "ssu_2": f"S{h}_{psu}_{ssu}",
                            "fpc_1_frac": 0.5,
                            "fpc_1_pop": 4.0,
                            "fpc_2_frac": 0.25,
                            "fpc_2_pop": 8.0,
                            "weight": 1.0,
                            "ind1": 1 if (h + psu + ssu + hh) % 2 == 0 else 0,
                            "ind2": 1 if hh == 1 else 0,
                            "region": "A" if h == 1 else "B",
                        }
                    )
    return pd.DataFrame(rows)


@pytest.fixture
def spec() -> Specification:
    return Specification(
        dimensions={"d1": ["ind1"], "d2": ["ind2"]},
        weights={"d1": 0.5, "d2": 0.5},
    )


def test_multistage_non_regression(sample_data: pd.DataFrame, spec: Specification) -> None:
    """1. stages=[Stage(id='psu', strata='h')] gives exact same result as
    SurveyDesign(strata='h', psu='psu').
    """
    d1 = SurveyDesign(weights="weight", strata="strata_1", psu="psu_1")
    d2 = SurveyDesign(weights="weight", stages=[Stage(id="psu_1", strata="strata_1")])

    res1 = estimate(sample_data, spec, d1, k=0.5).estimates()
    res2 = estimate(sample_data, spec, d2, k=0.5).estimates()

    pd.testing.assert_frame_equal(res1, res2)


def test_fpc_fraction_vs_population(sample_data: pd.DataFrame, spec: Specification) -> None:
    """2. fpc in fraction (<= 1) and fpc in population count (> 1) giving the
    same f produce same variance.
    """
    d_frac = SurveyDesign(
        weights="weight",
        stages=[Stage(id="psu_1", strata="strata_1", fpc="fpc_1_frac")],
    )
    d_pop = SurveyDesign(
        weights="weight",
        stages=[Stage(id="psu_1", strata="strata_1", fpc="fpc_1_pop")],
    )

    res_frac = estimate(sample_data, spec, d_frac, k=0.5).estimates()
    res_pop = estimate(sample_data, spec, d_pop, k=0.5).estimates()

    pd.testing.assert_frame_equal(res_frac, res_pop)


def test_two_stages_without_fpc_equals_ultimate_cluster(
    sample_data: pd.DataFrame, spec: Specification
) -> None:
    """3. Two stages without FPC = one stage (ultimate cluster)."""
    d_1stage = SurveyDesign(weights="weight", strata="strata_1", psu="psu_1")
    d_2stage = SurveyDesign(
        weights="weight",
        stages=[
            Stage(id="psu_1", strata="strata_1"),
            Stage(id="ssu_2"),
        ],
    )

    res1 = estimate(sample_data, spec, d_1stage, k=0.5).estimates()
    res2 = estimate(sample_data, spec, d_2stage, k=0.5).estimates()

    pd.testing.assert_frame_equal(res1, res2)


def test_hand_calculated_2stage_example(spec: Specification) -> None:
    """4. Hand-calculated 2-stage example with exact numeric oracle assertions."""
    df = pd.DataFrame(
        [
            {
                "h": "H1",
                "psu": "P1_1",
                "ssu": "S1_1_1",
                "f1": 0.5,
                "f2": 0.25,
                "w": 1.0,
                "ind1": 1,
                "ind2": 1,
            },
            {
                "h": "H1",
                "psu": "P1_1",
                "ssu": "S1_1_2",
                "f1": 0.5,
                "f2": 0.25,
                "w": 1.0,
                "ind1": 1,
                "ind2": 0,
            },
            {
                "h": "H1",
                "psu": "P1_2",
                "ssu": "S1_2_1",
                "f1": 0.5,
                "f2": 0.25,
                "w": 1.0,
                "ind1": 0,
                "ind2": 0,
            },
            {
                "h": "H1",
                "psu": "P1_2",
                "ssu": "S1_2_2",
                "f1": 0.5,
                "f2": 0.25,
                "w": 1.0,
                "ind1": 0,
                "ind2": 0,
            },
            {
                "h": "H2",
                "psu": "P2_1",
                "ssu": "S2_1_1",
                "f1": 0.5,
                "f2": 0.25,
                "w": 1.0,
                "ind1": 1,
                "ind2": 1,
            },
            {
                "h": "H2",
                "psu": "P2_1",
                "ssu": "S2_1_2",
                "f1": 0.5,
                "f2": 0.25,
                "w": 1.0,
                "ind1": 1,
                "ind2": 1,
            },
            {
                "h": "H2",
                "psu": "P2_2",
                "ssu": "S2_2_1",
                "f1": 0.5,
                "f2": 0.25,
                "w": 1.0,
                "ind1": 0,
                "ind2": 1,
            },
            {
                "h": "H2",
                "psu": "P2_2",
                "ssu": "S2_2_2",
                "f1": 0.5,
                "f2": 0.25,
                "w": 1.0,
                "ind1": 0,
                "ind2": 1,
            },
        ]
    )

    d = SurveyDesign(
        weights="w",
        stages=[
            Stage(id="psu", strata="h", fpc="f1"),
            Stage(id="ssu", fpc="f2"),
        ],
    )

    res = estimate(df, spec, d, k=0.5)
    res_df = res.estimates()

    h_row = res_df[res_df["measure"] == "H"].iloc[0]
    m0_row = res_df[res_df["measure"] == "M0"].iloc[0]
    a_row = res_df[res_df["measure"] == "A"].iloc[0]

    assert h_row["est"] == pytest.approx(0.75, abs=1e-12)
    assert h_row["se"] == pytest.approx(0.17677669529663687, abs=1e-10)

    assert m0_row["est"] == pytest.approx(0.5625, abs=1e-12)
    assert m0_row["se"] == pytest.approx(0.16387638252684803, abs=1e-10)

    assert a_row["est"] == pytest.approx(0.75, abs=1e-12)
    assert a_row["se"] == pytest.approx(0.1284252917281313, abs=1e-10)


def test_f1_equals_1_only_stage2_contributes(spec: Specification) -> None:
    """5. f_1 = 1: only stage 2 contributes to variance with exact oracle values."""
    df = pd.DataFrame(
        [
            {
                "h": "H1",
                "psu": "P1_1",
                "ssu": "S1_1_1",
                "f1": 1.0,
                "f2": 0.5,
                "w": 1.0,
                "ind1": 1,
                "ind2": 1,
            },
            {
                "h": "H1",
                "psu": "P1_1",
                "ssu": "S1_1_2",
                "f1": 1.0,
                "f2": 0.5,
                "w": 1.0,
                "ind1": 0,
                "ind2": 0,
            },
            {
                "h": "H1",
                "psu": "P1_2",
                "ssu": "S1_2_1",
                "f1": 1.0,
                "f2": 0.5,
                "w": 1.0,
                "ind1": 1,
                "ind2": 0,
            },
            {
                "h": "H1",
                "psu": "P1_2",
                "ssu": "S1_2_2",
                "f1": 1.0,
                "f2": 0.5,
                "w": 1.0,
                "ind1": 0,
                "ind2": 1,
            },
        ]
    )
    d = SurveyDesign(
        weights="w",
        stages=[
            Stage(id="psu", strata="h", fpc="f1"),
            Stage(id="ssu", fpc="f2"),
        ],
    )
    res_df = estimate(df, spec, d, k=0.5).estimates()

    h_row = res_df[res_df["measure"] == "H"].iloc[0]
    m0_row = res_df[res_df["measure"] == "M0"].iloc[0]
    a_row = res_df[res_df["measure"] == "A"].iloc[0]

    assert h_row["est"] == pytest.approx(0.75, abs=1e-12)
    assert h_row["se"] == pytest.approx(0.17677669529663687, abs=1e-10)

    assert m0_row["est"] == pytest.approx(0.50, abs=1e-12)
    assert m0_row["se"] == pytest.approx(0.17677669529663687, abs=1e-10)

    assert a_row["est"] == pytest.approx(2.0 / 3.0, abs=1e-12)
    assert a_row["se"] == pytest.approx(0.07856742013183863, abs=1e-10)


def test_multistage_errors(spec: Specification) -> None:
    """6. Validation errors for invalid stage/fpc declarations."""
    with pytest.raises(ValueError, match="stages must be a non-empty sequence"):
        SurveyDesign(stages=[])

    with pytest.raises(ValueError, match="declare either strata=/psu="):
        SurveyDesign(psu="p", stages=[Stage(id="p")])

    df_non_const = pd.DataFrame(
        [
            {"h": "H1", "p": "P1", "fpc": 0.5, "w": 1.0, "ind1": 1, "ind2": 0},
            {"h": "H1", "p": "P2", "fpc": 0.8, "w": 1.0, "ind1": 0, "ind2": 1},
        ]
    )
    d_non_const = SurveyDesign(weights="w", stages=[Stage(id="p", strata="h", fpc="fpc")])
    with pytest.raises(ValueError, match="not constant within stratum"):
        estimate(df_non_const, spec, d_non_const)

    df_mixed = pd.DataFrame(
        [
            {"h": "H1", "p": "P1", "fpc": 0.5, "w": 1.0, "ind1": 1, "ind2": 0},
            {"h": "H2", "p": "P2", "fpc": 10.0, "w": 1.0, "ind1": 0, "ind2": 1},
        ]
    )
    d_mixed = SurveyDesign(weights="w", stages=[Stage(id="p", strata="h", fpc="fpc")])
    with pytest.raises(ValueError, match="mixes values <= 1 and > 1"):
        estimate(df_mixed, spec, d_mixed)

    df_N_less = pd.DataFrame(
        [
            {"h": "H1", "p": "P1", "fpc": 1.5, "w": 1.0, "ind1": 1, "ind2": 0},
            {"h": "H1", "p": "P2", "fpc": 1.5, "w": 1.0, "ind1": 0, "ind2": 1},
        ]
    )
    d_N_less = SurveyDesign(weights="w", stages=[Stage(id="p", strata="h", fpc="fpc")])
    with pytest.raises(ValueError, match="smaller than the m="):
        estimate(df_N_less, spec, d_N_less)


def test_multistage_decomposability_with_over(
    sample_data: pd.DataFrame, spec: Specification
) -> None:
    """7. Domain and over= on a 2-stage design: decomposability holds."""
    d = SurveyDesign(
        weights="weight",
        stages=[
            Stage(id="psu_1", strata="strata_1", fpc="fpc_1_frac"),
            Stage(id="ssu_2", fpc="fpc_2_frac"),
        ],
    )
    res = estimate(sample_data, spec, d, k=0.5, over="region")
    assert float(res.decomposition()["error"].max()) < 1e-9
