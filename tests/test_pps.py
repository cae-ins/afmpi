import numpy as np
import pandas as pd
import pytest

from afmpi import (
    LonelyPSUWarning,
    PPSDesign,
    Specification,
    Stage,
    SurveyDesign,
    estimate,
)


@pytest.fixture
def pps_data() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"h": "H1", "psu": "P1", "w": 10.0, "pi": 0.1, "ind1": 1, "ind2": 0},
            {"h": "H1", "psu": "P1", "w": 10.0, "pi": 0.1, "ind1": 1, "ind2": 1},
            {"h": "H1", "psu": "P2", "w": 5.0, "pi": 0.2, "ind1": 0, "ind2": 0},
            {"h": "H1", "psu": "P2", "w": 5.0, "pi": 0.2, "ind1": 0, "ind2": 1},
            {"h": "H2", "psu": "P3", "w": 4.0, "pi": 0.25, "ind1": 1, "ind2": 1},
            {"h": "H2", "psu": "P3", "w": 4.0, "pi": 0.25, "ind1": 1, "ind2": 0},
            {"h": "H2", "psu": "P4", "w": 2.0, "pi": 0.5, "ind1": 0, "ind2": 1},
            {"h": "H2", "psu": "P4", "w": 2.0, "pi": 0.5, "ind1": 0, "ind2": 0},
        ]
    )


@pytest.fixture
def spec() -> Specification:
    return Specification(
        dimensions={"d1": ["ind1"], "d2": ["ind2"]},
        weights={"d1": 0.5, "d2": 0.5},
    )


def test_pps_with_replacement_identical_to_v020(
    pps_data: pd.DataFrame, spec: Specification
) -> None:
    """1. with_replacement produces exact same result as v0.2.0 without pps=."""
    d1 = SurveyDesign(weights="w", strata="h", psu="psu")
    d2 = SurveyDesign(
        weights="w",
        strata="h",
        psu="psu",
        pps=PPSDesign(method="with_replacement", inclusion_probability="pi"),
    )

    res1 = estimate(pps_data, spec, d1, k=0.5).estimates()
    res2 = estimate(pps_data, spec, d2, k=0.5).estimates()

    pd.testing.assert_frame_equal(res1, res2)


def test_sen_yates_grundy_hand_calculated(spec: Specification) -> None:
    """2. Sen-Yates-Grundy on 2 PSUs per stratum with exact numeric oracle assertions."""
    df = pd.DataFrame(
        [
            {"h": "H1", "psu": "P1", "w": 10.0, "pi": 0.2, "ind1": 1, "ind2": 1},
            {"h": "H1", "psu": "P2", "w": 10.0, "pi": 0.2, "ind1": 0, "ind2": 0},
        ]
    )

    joint_p = pd.DataFrame(
        [
            {"psu_a": "P1", "psu_b": "P2", "pi_ab": 0.03},
        ]
    )

    d = SurveyDesign(
        weights="w",
        strata="h",
        psu="psu",
        pps=PPSDesign(
            method="without_replacement",
            inclusion_probability="pi",
            joint_probability=joint_p,
            variance="sen_yates_grundy",
        ),
    )

    res = estimate(df, spec, d, k=0.5).estimates()

    h_row = res[res["measure"] == "H"].iloc[0]
    m0_row = res[res["measure"] == "M0"].iloc[0]
    a_row = res[res["measure"] == "A"].iloc[0]

    assert h_row["est"] == pytest.approx(0.50, abs=1e-12)
    assert h_row["se"] == pytest.approx(0.28867513459481287, abs=1e-10)

    assert m0_row["est"] == pytest.approx(0.50, abs=1e-12)
    assert m0_row["se"] == pytest.approx(0.28867513459481287, abs=1e-10)

    assert a_row["est"] == pytest.approx(1.0, abs=1e-12)
    assert a_row["se"] == pytest.approx(0.0, abs=1e-12)


def test_sen_yates_grundy_independence_gives_zero_variance(spec: Specification) -> None:
    """3. Sen-Yates-Grundy with pi_cd = pi_c * pi_d gives zero variance term by term."""
    df = pd.DataFrame(
        [
            {"h": "H1", "psu": "P1", "w": 10.0, "pi": 0.2, "ind1": 1, "ind2": 1},
            {"h": "H1", "psu": "P2", "w": 10.0, "pi": 0.3, "ind1": 0, "ind2": 0},
        ]
    )

    joint_p = pd.DataFrame(
        [
            {"psu_a": "P1", "psu_b": "P2", "pi_ab": 0.06},
        ]
    )

    d = SurveyDesign(
        weights="w",
        strata="h",
        psu="psu",
        pps=PPSDesign(
            method="without_replacement",
            inclusion_probability="pi",
            joint_probability=joint_p,
            variance="sen_yates_grundy",
        ),
    )

    res = estimate(df, spec, d, k=0.5).estimates()
    for _, row in res.iterrows():
        if row["se"] is not None and pd.notna(row["se"]):
            assert abs(row["se"]) < 1e-12


def test_hajek_reproduces_stratified_estimator(spec: Specification) -> None:
    """4. Hajek with all pi equal to m/M with exact numeric oracle assertions."""
    df = pd.DataFrame(
        [
            {"h": "H1", "psu": "P1", "w": 1.0, "pi": 0.5, "ind1": 1, "ind2": 1},
            {"h": "H1", "psu": "P1", "w": 1.0, "pi": 0.5, "ind1": 1, "ind2": 0},
            {"h": "H1", "psu": "P2", "w": 1.0, "pi": 0.5, "ind1": 0, "ind2": 0},
            {"h": "H1", "psu": "P2", "w": 1.0, "pi": 0.5, "ind1": 0, "ind2": 1},
        ]
    )

    d_hajek = SurveyDesign(
        weights="w",
        strata="h",
        psu="psu",
        pps=PPSDesign(
            method="without_replacement",
            inclusion_probability="pi",
            variance="hajek",
        ),
    )

    res = estimate(df, spec, d_hajek, k=0.5).estimates()
    h_row = res[res["measure"] == "H"].iloc[0]
    m0_row = res[res["measure"] == "M0"].iloc[0]
    a_row = res[res["measure"] == "A"].iloc[0]

    assert h_row["est"] == pytest.approx(0.75, abs=1e-12)
    assert h_row["se"] == pytest.approx(0.17677669529663687, abs=1e-10)

    assert m0_row["est"] == pytest.approx(0.50, abs=1e-12)
    assert m0_row["se"] == pytest.approx(0.17677669529663687, abs=1e-10)

    assert a_row["est"] == pytest.approx(2.0 / 3.0, abs=1e-12)
    assert a_row["se"] == pytest.approx(0.07856742013183863, abs=1e-10)


def test_pps_with_replacement_hansen_hurwitz_proof(
    pps_data: pd.DataFrame, spec: Specification
) -> None:
    """5. Proof that PPS with replacement equals Hansen-Hurwitz variance estimator."""
    d_pps = SurveyDesign(
        weights="w",
        strata="h",
        psu="psu",
        pps=PPSDesign(method="with_replacement", inclusion_probability="pi"),
    )
    d_std = SurveyDesign(weights="w", strata="h", psu="psu")

    res_pps = estimate(pps_data, spec, d_pps, k=0.5).estimates()
    res_std = estimate(pps_data, spec, d_std, k=0.5).estimates()

    pd.testing.assert_frame_equal(res_pps, res_std)


def test_syg_with_duplicate_psu_names_across_strata(spec: Specification) -> None:
    """6. SYG matching when two strata share PSU names ('P1', 'P2') with different pi_ab."""
    df = pd.DataFrame(
        [
            {"h": "H1", "psu": "P1", "w": 10.0, "pi": 0.2, "ind1": 1, "ind2": 1},
            {"h": "H1", "psu": "P2", "w": 10.0, "pi": 0.2, "ind1": 0, "ind2": 0},
            {"h": "H2", "psu": "P1", "w": 5.0, "pi": 0.4, "ind1": 1, "ind2": 0},
            {"h": "H2", "psu": "P2", "w": 5.0, "pi": 0.4, "ind1": 1, "ind2": 1},
        ]
    )

    # Different pi_ab for H1 and H2
    joint_p = pd.DataFrame(
        [
            {"stratum": "H1", "psu_a": "P1", "psu_b": "P2", "pi_ab": 0.03},
            {"stratum": "H2", "psu_a": "P1", "psu_b": "P2", "pi_ab": 0.12},
        ]
    )

    d = SurveyDesign(
        weights="w",
        strata="h",
        psu="psu",
        pps=PPSDesign(
            method="without_replacement",
            inclusion_probability="pi",
            joint_probability=joint_p,
            variance="sen_yates_grundy",
        ),
    )

    res = estimate(df, spec, d, k=0.5).estimates()
    m0_row = res[res["measure"] == "M0"].iloc[0]
    # Per-stratum SYG variance summed across H1 (pi_ab=0.03) and H2 (pi_ab=0.12), each keyed by
    # (stratum, psu_a, psu_b): had the stratum key been dropped, "P1"/"P2" would collide across
    # H1/H2 and silently pick up the wrong pi_ab. Value confirmed against R survey::svydesign
    # (pps = ppsmat(...), variance = "YG") on the equivalent per-stratum design.
    assert m0_row["est"] == pytest.approx(0.5833333333333334, abs=1e-12)
    assert m0_row["se"] == pytest.approx(0.19837301190396817, abs=1e-10)


def test_pps_errors(spec: Specification) -> None:
    """7. PPS error validation cases."""
    with pytest.raises(ValueError, match="inclusion_probability must be provided"):
        PPSDesign(method="without_replacement", inclusion_probability=None)

    with pytest.raises(ValueError, match="joint_probability must be provided"):
        PPSDesign(variance="sen_yates_grundy", joint_probability=None)

    with pytest.raises(ValueError, match="PPS is supported for one-stage designs only"):
        SurveyDesign(
            weights="w",
            stages=[Stage(id="p1"), Stage(id="p2")],
            pps=PPSDesign(method="without_replacement", inclusion_probability="pi"),
        )

    with pytest.raises(ValueError, match="PPS cannot be combined with fpc"):
        SurveyDesign(
            weights="w",
            stages=[Stage(id="p1", fpc="fpc1")],
            pps=PPSDesign(method="without_replacement", inclusion_probability="pi"),
        )


def test_pps_lonely_psu_five_policies(spec: Specification) -> None:
    """8. Test all 5 lonely PSU policies on a PPS design with a single PSU in a stratum."""
    # 2 strata: H1 has 2 PSUs (P1, P2), H2 has 1 lonely PSU (P3)
    df = pd.DataFrame(
        [
            {"h": "H1", "psu": "P1", "w": 10.0, "pi": 0.1, "ind1": 1, "ind2": 0},
            {"h": "H1", "psu": "P1", "w": 10.0, "pi": 0.1, "ind1": 1, "ind2": 1},
            {"h": "H1", "psu": "P2", "w": 5.0, "pi": 0.2, "ind1": 0, "ind2": 0},
            {"h": "H1", "psu": "P2", "w": 5.0, "pi": 0.2, "ind1": 0, "ind2": 1},
            {"h": "H2", "psu": "P3", "w": 4.0, "pi": 0.25, "ind1": 1, "ind2": 1},
            {"h": "H2", "psu": "P3", "w": 4.0, "pi": 0.25, "ind1": 1, "ind2": 0},
        ]
    )

    # 1. fail: emits LonelyPSUWarning and returns NaN SE
    d_fail = SurveyDesign(
        weights="w",
        strata="h",
        psu="psu",
        lonely_psu="fail",
        pps=PPSDesign(
            method="without_replacement", inclusion_probability="pi", variance="hajek"
        ),
    )
    with pytest.warns(LonelyPSUWarning, match="contain\\(s\\) a single PSU"):
        res_fail = estimate(df, spec, d_fail, k=0.5).estimates()
    h_fail = res_fail[res_fail["measure"] == "H"].iloc[0]
    assert np.isnan(h_fail["se"])

    # 2. certainty: lonely stratum has 0 variance contribution
    d_cert = SurveyDesign(
        weights="w",
        strata="h",
        psu="psu",
        lonely_psu="certainty",
        pps=PPSDesign(
            method="without_replacement", inclusion_probability="pi", variance="hajek"
        ),
    )
    res_cert = estimate(df, spec, d_cert, k=0.5).estimates()
    h_cert = res_cert[res_cert["measure"] == "H"].iloc[0]
    assert np.isfinite(h_cert["se"])
    assert h_cert["se"] > 0

    # 3. collapse: merges lonely stratum and computes valid variance
    d_col = SurveyDesign(
        weights="w",
        strata="h",
        psu="psu",
        lonely_psu="collapse",
        pps=PPSDesign(
            method="without_replacement", inclusion_probability="pi", variance="hajek"
        ),
    )
    res_col = estimate(df, spec, d_col, k=0.5).estimates()
    h_col = res_col[res_col["measure"] == "H"].iloc[0]
    assert np.isfinite(h_col["se"])
    assert h_col["se"] > 0

    # 4. adjust: raises ValueError for PPS without replacement
    with pytest.raises(ValueError, match="not supported for PPS without replacement"):
        SurveyDesign(
            weights="w",
            strata="h",
            psu="psu",
            lonely_psu="adjust",
            pps=PPSDesign(
                method="without_replacement", inclusion_probability="pi", variance="hajek"
            ),
        )

    # 5. average: raises ValueError for PPS without replacement
    with pytest.raises(ValueError, match="not supported for PPS without replacement"):
        SurveyDesign(
            weights="w",
            strata="h",
            psu="psu",
            lonely_psu="average",
            pps=PPSDesign(
                method="without_replacement", inclusion_probability="pi", variance="hajek"
            ),
        )
