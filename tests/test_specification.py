import pytest

from afmpi import Specification, SurveyDesign

DIMENSIONS_05 = {
    "Education": [f"i{n}" for n in range(4)],
    "Sante": [f"i{n}" for n in range(4, 7)],
    "Emploi": [f"i{n}" for n in range(7, 9)],
    "Conditions de vie": [f"i{n}" for n in range(9, 16)],
}


def test_equal_nested_weights_port_pythonipm_05():
    spec = Specification().set(DIMENSIONS_05)

    assert sum(spec.indicator_weights.values()) == pytest.approx(1.0)
    assert spec.indicator_weights["i0"] == pytest.approx(0.0625)
    assert spec.indicator_weights["i7"] == pytest.approx(0.125)
    assert spec.indicator_weights["i9"] == pytest.approx(0.25 / 7)


def test_three_dimension_variant_port_pythonipm_05():
    dimensions = {key: value for key, value in DIMENSIONS_05.items() if key != "Emploi"}
    spec = Specification(dimensions)

    assert len(spec.indicators) == 14
    assert spec.indicator_weights["i0"] == pytest.approx(1 / 12)
    assert spec.indicator_weights["i4"] == pytest.approx(1 / 9)
    assert spec.indicator_weights["i9"] == pytest.approx(1 / 21)


def test_custom_weights_must_be_complete_and_sum_to_one():
    spec = Specification({"d1": ["a"], "d2": ["b"]})
    spec.set_weights({"a": 0.7, "b": 0.3})
    assert spec.dimension_weights == {"d1": 0.7, "d2": 0.3}

    with pytest.raises(ValueError, match="sum to 1"):
        spec.set_weights({"a": 0.7, "b": 0.2})
    with pytest.raises(ValueError, match="exactly all dimensions or all indicators"):
        spec.set_weights({"d1": 1.0})


def test_indicator_cannot_appear_in_two_dimensions():
    with pytest.raises(ValueError, match="only one dimension"):
        Specification({"d1": ["a"], "d2": ["a"]})


def test_survey_design_supports_individual_and_household_weights():
    assert SurveyDesign(weights="person_weight").required_columns == ("person_weight",)
    assert SurveyDesign(
        weights="household_weight", household_size="household_size"
    ).required_columns == ("household_weight", "household_size")
