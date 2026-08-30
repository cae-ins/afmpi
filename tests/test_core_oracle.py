"""Oracle validation tests for the core survey engine against R 'survey' package.

Replays the scenarios from tests/oracle/core_oracle.R and asserts equality
to exact R reference values within 10^-10 tolerance (PLAN.md §17).
"""

import polars as pl
import pytest

from afmpi import Specification, SurveyDesign, estimate
from afmpi.variance import confidence_interval

SPEC = Specification({"d1": ["i0", "i1"], "d2": ["i2", "i3"]})

# --------------------------------------------------------------------------- #
# 1. SRS Simple (no strata, no clusters)
# --------------------------------------------------------------------------- #
DF_SRS = pl.DataFrame(
    {
        "id": list(range(1, 11)),
        "w": [1.0, 1.2, 0.8, 1.1, 0.9, 1.3, 1.0, 1.4, 0.7, 1.2],
        "size": [4, 3, 5, 2, 6, 4, 3, 5, 4, 2],
        "i0": [1, 0, 1, 1, 0, 1, 1, 0, 1, 0],
        "i1": [1, 1, 0, 1, 0, 0, 1, 1, 0, 1],
        "i2": [0, 1, 1, 0, 1, 0, 0, 1, 1, 0],
        "i3": [1, 0, 0, 1, 0, 1, 0, 0, 1, 1],
    }
)
DESIGN_SRS = SurveyDesign(weights="w", household_size="size")


def test_srs_oracle_against_r_survey():
    """Compare SRS simple design estimates, SEs, degf and CIs against R survey."""
    result = estimate(DF_SRS, SPEC, DESIGN_SRS, k=1 / 3, ci_method="logit")

    h_row = result.estimates().filter(pl.col("measure") == "H").row(0, named=True)
    assert h_row["est"] == pytest.approx(0.86363636363636, abs=1e-10)
    assert h_row["se"] == pytest.approx(0.13178106663145, abs=1e-10)
    assert h_row["se"] ** 2 == pytest.approx(0.017366249522523, abs=1e-10)
    assert h_row["lci"] == pytest.approx(0.33503733422103, abs=1e-10)
    assert h_row["uci"] == pytest.approx(0.9875946230251, abs=1e-10)

    m0_row = result.estimates().filter(pl.col("measure") == "M0").row(0, named=True)
    assert m0_row["est"] == pytest.approx(0.48863636363636, abs=1e-10)
    assert m0_row["se"] == pytest.approx(0.079575621777644, abs=1e-10)
    assert m0_row["se"] ** 2 == pytest.approx(0.0063322795812987, abs=1e-10)

    a_row = result.estimates().filter(pl.col("measure") == "A").row(0, named=True)
    assert a_row["est"] == pytest.approx(0.56578947368421, abs=1e-10)
    assert a_row["se"] == pytest.approx(0.03764209143743, abs=1e-10)
    assert a_row["se"] ** 2 == pytest.approx(0.0014169270477838, abs=1e-10)

    assert result.degf().row(0, named=True)["df"] == 9

    # Check normal and t lower confidence bounds against R
    res_t = estimate(DF_SRS, SPEC, DESIGN_SRS, k=1 / 3, ci_method="t")
    row_t = res_t.estimates().filter(pl.col("measure") == "H").row(0, named=True)
    assert row_t["lci"] == pytest.approx(0.56552687983484, abs=1e-10)

    res_norm = estimate(DF_SRS, SPEC, DESIGN_SRS, k=1 / 3, ci_method="normal")
    row_norm = res_norm.estimates().filter(pl.col("measure") == "H").row(0, named=True)
    assert row_norm["lci"] == pytest.approx(0.60535021919445, abs=1e-10)


# --------------------------------------------------------------------------- #
# 2. Stratified Simple 1-Stage
# --------------------------------------------------------------------------- #
DF_STRAT = pl.DataFrame(
    {
        "id": list(range(1, 13)),
        "stratum": [1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3],
        "psu": [1, 1, 2, 3, 4, 4, 5, 5, 6, 7, 7, 8],
        "w": [1.0, 1.2, 0.8, 1.1, 0.9, 1.3, 1.0, 1.4, 0.7, 1.2, 1.1, 0.9],
        "size": [4, 3, 5, 2, 6, 4, 3, 5, 4, 2, 6, 3],
        "i0": [1, 0, 1, 1, 0, 1, 1, 0, 1, 0, 1, 1],
        "i1": [1, 1, 0, 1, 0, 0, 1, 1, 0, 1, 1, 0],
        "i2": [0, 1, 1, 0, 1, 0, 0, 1, 1, 0, 0, 1],
        "i3": [1, 0, 0, 1, 0, 1, 0, 0, 1, 1, 0, 0],
    }
)
DESIGN_STRAT = SurveyDesign(
    weights="w", household_size="size", strata="stratum", psu="psu"
)


def test_stratified_oracle_against_r_survey():
    """Compare 1-stage stratified design estimates, SEs, degf and CIs against R survey."""
    result = estimate(DF_STRAT, SPEC, DESIGN_STRAT, k=1 / 3, ci_method="logit")

    h_row = result.estimates().filter(pl.col("measure") == "H").row(0, named=True)
    assert h_row["est"] == pytest.approx(0.88957055214724, abs=1e-10)
    assert h_row["se"] == pytest.approx(0.11050862058823, abs=1e-10)
    assert h_row["se"] ** 2 == pytest.approx(0.012212155224313, abs=1e-10)
    assert h_row["lci"] == pytest.approx(0.30887194903561, abs=1e-10)
    assert h_row["uci"] == pytest.approx(0.99316012400656, abs=1e-10)

    m0_row = result.estimates().filter(pl.col("measure") == "M0").row(0, named=True)
    assert m0_row["est"] == pytest.approx(0.49079754601227, abs=1e-10)
    assert m0_row["se"] == pytest.approx(0.059673872946972, abs=1e-10)
    assert m0_row["se"] ** 2 == pytest.approx(0.0035609711124913, abs=1e-10)

    a_row = result.estimates().filter(pl.col("measure") == "A").row(0, named=True)
    assert a_row["est"] == pytest.approx(0.55172413793103, abs=1e-10)
    assert a_row["se"] == pytest.approx(0.027485625356477, abs=1e-10)
    assert a_row["se"] ** 2 == pytest.approx(0.0007554596012366, abs=1e-10)

    assert result.degf().row(0, named=True)["df"] == 5

    res_t = estimate(DF_STRAT, SPEC, DESIGN_STRAT, k=1 / 3, ci_method="t")
    row_t = res_t.estimates().filter(pl.col("measure") == "H").row(0, named=True)
    assert row_t["lci"] == pytest.approx(0.60549909938192, abs=1e-10)

    res_norm = estimate(DF_STRAT, SPEC, DESIGN_STRAT, k=1 / 3, ci_method="normal")
    row_norm = res_norm.estimates().filter(pl.col("measure") == "H").row(0, named=True)
    assert row_norm["lci"] == pytest.approx(0.67297763581311, abs=1e-10)


# --------------------------------------------------------------------------- #
# 3. Domain (subset in R) on Stratified Design
# --------------------------------------------------------------------------- #
DF_LAYOUT = pl.DataFrame(
    {
        "i0": [1, 0, 1, 1, 0, 1, 1, 0, 1, 0, 1, 1],
        "i1": [1, 1, 0, 1, 0, 0, 1, 1, 0, 1, 1, 0],
        "i2": [0, 1, 1, 0, 1, 0, 0, 1, 1, 0, 0, 1],
        "i3": [1, 0, 0, 1, 0, 1, 0, 0, 1, 1, 0, 0],
        "w": [1.0, 1.2, 0.8, 1.1, 0.9, 1.3, 1.0, 1.4, 0.7, 1.2, 1.1, 0.9],
        "size": [4, 3, 5, 2, 6, 4, 3, 5, 4, 2, 6, 3],
        "strate": [1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3],
        "grappe": [1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6],
        "region": ["A", "A", "B", "B", "A", "A", "A", "A", "B", "B", "A", "A"],
    }
)
DESIGN_LAYOUT = SurveyDesign(
    weights="w", household_size="size", strata="strate", psu="grappe"
)


def test_domain_oracle_against_r_survey():
    """Confirm degf() and estimates under domain subset match R svydesign |> subset."""
    whole = estimate(DF_LAYOUT, SPEC, DESIGN_LAYOUT, k=1 / 3)
    assert whole.degf().row(0, named=True) == {"psus": 6, "strata": 3, "df": 3}

    domain = whole.domain(pl.col("region") == "A")
    assert domain.degf().row(0, named=True) == {"psus": 4, "strata": 3, "df": 1}

    h_row = domain.estimates().filter(pl.col("measure") == "H").row(0, named=True)
    assert h_row["est"] == pytest.approx(0.856, abs=1e-10)
    assert h_row["se"] == pytest.approx(0.14901278205577, abs=1e-10)
    assert h_row["se"] ** 2 == pytest.approx(0.022204809216, abs=1e-10)

    m0_row = domain.estimates().filter(pl.col("measure") == "M0").row(0, named=True)
    assert m0_row["est"] == pytest.approx(0.45466666666667, abs=1e-10)
    assert m0_row["se"] == pytest.approx(0.080572953981983, abs=1e-10)
    assert m0_row["se"] ** 2 == pytest.approx(0.0064920009133827, abs=1e-10)

    a_row = domain.estimates().filter(pl.col("measure") == "A").row(0, named=True)
    assert a_row["est"] == pytest.approx(0.53115264797508, abs=1e-10)
    assert a_row["se"] == pytest.approx(0.025855432927348, abs=1e-10)
    assert a_row["se"] ** 2 == pytest.approx(0.00066850341186061, abs=1e-10)


# --------------------------------------------------------------------------- #
# 4. Boundary cases for Logit CI (H close to 0 or 1)
# --------------------------------------------------------------------------- #
def test_logit_ci_boundary_behavior_against_r():
    """Verify logit CI respects [0,1] bounds by construction while linear/t overflow."""
    est_low, se_low, df_low = 0.1, 0.095916630466254, 4
    est_high, se_high, df_high = 0.9, 0.095916630466254, 4

    # Low H (0.1)
    lci_logit, uci_logit = confidence_interval(est_low, se_low, df_low, method="logit")
    assert lci_logit == pytest.approx(0.0057305648745028, abs=1e-10)
    assert uci_logit == pytest.approx(0.68173246548443, abs=1e-10)
    assert 0.0 <= lci_logit <= uci_logit <= 1.0

    lci_t_unbound, uci_t_unbound = confidence_interval(
        est_low, se_low, df_low, method="t", bounded=False
    )
    assert lci_t_unbound == pytest.approx(-0.1663072591651, abs=1e-10)
    assert uci_t_unbound == pytest.approx(0.3663072591651, abs=1e-10)
    assert lci_t_unbound < 0.0

    lci_norm_unbound, uci_norm_unbound = confidence_interval(
        est_low, se_low, df_low, method="normal", bounded=False
    )
    assert lci_norm_unbound == pytest.approx(-0.087993141232296, abs=1e-10)
    assert uci_norm_unbound == pytest.approx(0.2879931412323, abs=1e-10)
    assert lci_norm_unbound < 0.0

    # High H (0.9)
    lci_h_logit, uci_h_logit = confidence_interval(est_high, se_high, df_high, method="logit")
    assert lci_h_logit == pytest.approx(0.31826753451557, abs=1e-10)
    assert uci_h_logit == pytest.approx(0.9942694351255, abs=1e-10)
    assert 0.0 <= lci_h_logit <= uci_h_logit <= 1.0

    lci_h_t_unbound, uci_h_t_unbound = confidence_interval(
        est_high, se_high, df_high, method="t", bounded=False
    )
    assert lci_h_t_unbound == pytest.approx(0.6336927408349, abs=1e-10)
    assert uci_h_t_unbound == pytest.approx(1.1663072591651, abs=1e-10)
    assert uci_h_t_unbound > 1.0

    lci_h_norm_unbound, uci_h_norm_unbound = confidence_interval(
        est_high, se_high, df_high, method="normal", bounded=False
    )
    assert lci_h_norm_unbound == pytest.approx(0.7120068587677, abs=1e-10)
    assert uci_h_norm_unbound == pytest.approx(1.0879931412323, abs=1e-10)
    assert uci_h_norm_unbound > 1.0