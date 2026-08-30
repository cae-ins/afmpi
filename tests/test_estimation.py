import pandas as pd
import polars as pl
import pytest

from afmpi import Specification, SurveyDesign, estimate

TOLERANCE = 1e-6

DIMENSIONS_02 = {
    "Education": [
        "frequentation_scolaire",
        "annee_scolarite",
        "alphabetisation",
        "etat_civil",
    ],
    "Sante": ["assurance_maladie", "insecurite_alimentaire", "renoncement_soins"],
    "Emploi": ["su3", "neet", "emploi_subsistance"],
    "Conditions de vie": [
        "electricite",
        "logement",
        "eau_potable",
        "energie_cuisson",
        "toilette",
        "biens_equipement",
        "promiscuite",
    ],
}


def test_all_or_no_deprivation_port_pythonipm_02():
    indicators = [item for members in DIMENSIONS_02.values() for item in members]
    data = pl.DataFrame(
        {
            **{indicator: [1, 0] for indicator in indicators},
            "ponderation_menage": [1.0, 1.0],
            "taille_menage": [4, 4],
        }
    )
    result = estimate(
        data,
        Specification(DIMENSIONS_02),
        SurveyDesign("ponderation_menage", "taille_menage"),
        k=1 / 3,
    )

    assert result.population == pytest.approx(8.0)
    assert result.H == pytest.approx(0.5, abs=TOLERANCE)
    assert result.A == pytest.approx(1.0, abs=TOLERANCE)
    assert result.M0 == pytest.approx(0.5, abs=TOLERANCE)
    contributions = result.contributions()
    assert contributions["H_j"].to_list() == pytest.approx([0.5] * 17)
    assert contributions["CH_j"].to_list() == pytest.approx([0.5] * 17)
    assert contributions["pctb_j"].sum() == pytest.approx(1.0, abs=TOLERANCE)


def test_household_situations_port_pythonipm_01():
    dimensions = {
        "Education": [
            "frequentation_scolaire",
            "annee_scolarite",
            "alphabetisation",
            "etat_civil",
        ],
        "Sante": ["assurance_maladie", "renoncement_soins"],
        "Emploi": ["su3", "neet", "emploi_subsistance"],
    }
    # Privation outputs implied by the three hand-built households in verifier() of step 01.
    data = pl.DataFrame(
        {
            "frequentation_scolaire": [1, 0, 0],
            "annee_scolarite": [1, 0, 0],
            "alphabetisation": [0, 1, 1],
            "etat_civil": [1, 0, 0],
            "assurance_maladie": [1, 0, 1],
            "renoncement_soins": [1, 0, 0],
            "su3": [1, 0, 1],
            "neet": [0, 0, 1],
            "emploi_subsistance": [1, 0, 0],
            "taille_menage": [2, 2, 2],
        }
    )
    result = estimate(
        data,
        Specification(dimensions),
        SurveyDesign(household_size="taille_menage"),
        k=1 / 3,
    )

    scores = result.scores()
    assert scores["score"].to_list() == pytest.approx([29 / 36, 1 / 12, 17 / 36])
    assert scores["poor"].to_list() == [True, False, True]
    assert result.H == pytest.approx(2 / 3)
    assert result.A == pytest.approx(23 / 36)
    assert result.M0 == pytest.approx(23 / 54)


def test_weighted_four_households_port_pythonipm_05_and_pandas_input():
    # Scores are 0.50, 1.00, 0.25, 0.00 under four equal indicator weights.
    data = pd.DataFrame(
        {
            "i0": [1, 1, 1, 0],
            "i1": [1, 1, 0, 0],
            "i2": [0, 1, 0, 0],
            "i3": [0, 1, 0, 0],
            "taille_menage": [2, 8, 5, 5],
            "ponderation_menage": [1.0, 1.0, 1.0, 1.0],
        },
        index=["A", "B", "C", "D"],
    )
    spec = Specification({f"d{n}": [f"i{n}"] for n in range(4)})
    result = estimate(
        data,
        spec,
        SurveyDesign("ponderation_menage", "taille_menage"),
        k=1 / 3,
    )

    assert result.population == pytest.approx(20)
    assert result.H == pytest.approx(0.5, abs=TOLERANCE)
    assert result.A == pytest.approx(0.9, abs=TOLERANCE)
    assert result.M0 == pytest.approx(0.45, abs=TOLERANCE)
    assert isinstance(result.to_frame(), pd.DataFrame)
    contributions = result.contributions().set_index("indicator")
    assert contributions.loc["i0", "H_j"] == pytest.approx(0.75)
    assert contributions.loc["i0", "CH_j"] == pytest.approx(0.50)
    assert contributions.loc["i0", "actb_j"] == pytest.approx(0.125)
    assert contributions.loc["i0", "pctb_j"] == pytest.approx(0.125 / 0.45)
    assert contributions["pctb_j"].sum() == pytest.approx(1.0, abs=TOLERANCE)


def test_cutoff_boundaries_zero_and_one():
    data = pl.DataFrame({"a": [1, 0], "b": [1, 0]})
    spec = Specification({"d": ["a", "b"]})

    at_zero = estimate(data, spec, k=0)
    assert at_zero.H == pytest.approx(1.0)
    assert at_zero.A == pytest.approx(0.5)
    assert at_zero.M0 == pytest.approx(0.5)

    at_one = estimate(data, spec, k=1)
    assert at_one.H == pytest.approx(0.5)
    assert at_one.A == pytest.approx(1.0)
    assert at_one.M0 == pytest.approx(0.5)


@pytest.mark.parametrize(
    "values, exception",
    [
        ([0, 2], ValueError),
        ([0.0, 0.5], ValueError),
        (["0", "1"], TypeError),
    ],
)
def test_indicator_validation_is_strict(values, exception):
    with pytest.raises(exception, match="boolean or numeric 0/1|other than 0/1"):
        estimate(pl.DataFrame({"a": values}), Specification({"d": ["a"]}))


def test_boolean_indicators_are_accepted():
    result = estimate(pl.DataFrame({"a": [True, False]}), Specification({"d": ["a"]}))
    assert result.H == pytest.approx(0.5)


def test_missing_policies_listwise_and_reweighting():
    data = pl.DataFrame({"a": [1, 0], "b": [None, 0]})

    listwise = estimate(
        data,
        Specification({"d": ["a", "b"]}, missing_policy="listwise_deletion"),
        k=0.5,
    )
    assert listwise.observations == 1
    assert listwise.excluded_observations == 1
    assert listwise.M0 == pytest.approx(0.0)
    assert listwise.contributions()["pctb_j"].null_count() == 2

    reweighted = estimate(
        data,
        Specification({"d": ["a", "b"]}, missing_policy="reweighting"),
        k=0.5,
    )
    assert reweighted.observations == 2
    assert reweighted.H == pytest.approx(0.5)
    assert reweighted.A == pytest.approx(1.0)
    assert reweighted.M0 == pytest.approx(0.5)
    assert reweighted.contributions()["pctb_j"].sum() == pytest.approx(1.0)


def test_invalid_cutoffs_and_survey_weights_are_rejected():
    spec = Specification({"d": ["a"]})
    data = pl.DataFrame({"a": [0, 1], "w": [1.0, -1.0]})

    with pytest.raises(ValueError, match="between 0 and 1"):
        estimate(data, spec, k=1.01)
    with pytest.raises(ValueError, match="non-negative"):
        estimate(data, spec, SurveyDesign(weights="w"))


def test_summary_and_polars_output():
    result = estimate(pl.DataFrame({"a": [0, 1]}), Specification({"d": ["a"]}))
    assert isinstance(result.to_frame(), pl.DataFrame)
    assert result.to_frame().columns == [
        "k",
        "observations",
        "excluded_observations",
        "population",
        "H",
        "A",
        "M0",
    ]
    assert "H  = 0.500000" in result.summary()
    assert result.dimension_contributions()["pctb_dim"].sum() == pytest.approx(1.0)
