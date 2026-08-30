"""Phase 1: influence functions, checked without any sampling design.

Every assertion here is about the linearization itself (PLAN.md §5). Nothing in
this file declares strata, clusters or a variance estimator: if these properties
hold, any design-based variance estimator applied to the influence values is
computing the right thing, and if they fail, no design can rescue it.
"""

import polars as pl
import pytest

from afmpi import Specification, SurveyDesign
from afmpi import deprivation, estimands as estimands_module, linearization
from afmpi.deprivation import PSU, STRATUM, WEIGHT

TOLERANCE = 1e-12

# The four households of PythonIPM/pipeline/05_indices_ipm.py::verifier, restated
# through indicators so that afmpi computes the scores instead of being handed
# them: weighted scores are 0.50, 1.00, 0.25 and 0.00 under four equal weights.
FOUR_HOUSEHOLDS = pl.DataFrame(
    {
        "i0": [1, 1, 1, 0],
        "i1": [1, 1, 0, 0],
        "i2": [0, 1, 0, 0],
        "i3": [0, 1, 0, 0],
        "taille_menage": [2, 8, 5, 5],
        "ponderation_menage": [1.0, 1.0, 1.0, 1.0],
    }
)
FOUR_SPEC = Specification({f"d{n}": [f"i{n}"] for n in range(4)})
FOUR_DESIGN = SurveyDesign("ponderation_menage", "taille_menage")


def matrix_of(frame=FOUR_HOUSEHOLDS, spec=FOUR_SPEC, design=FOUR_DESIGN):
    return deprivation.build(frame, spec, design)


def linearized(k=1 / 3, frame=FOUR_HOUSEHOLDS, spec=FOUR_SPEC, design=FOUR_DESIGN):
    matrix = matrix_of(frame, spec, design)
    estimands = estimands_module.build(spec, k)
    ratios = linearization.totals(matrix.frame, estimands)
    influence = linearization.influence(matrix.frame, ratios)
    return matrix, estimands, {ratio.key: ratio for ratio in ratios}, influence


def random_frame(seed=7, rows=250, indicators=5):
    import random

    generator = random.Random(seed)
    columns = {
        f"i{j}": [generator.randint(0, 1) for _ in range(rows)] for j in range(indicators)
    }
    columns["w"] = [round(generator.uniform(0.4, 3.0), 4) for _ in range(rows)]
    columns["size"] = [generator.randint(1, 9) for _ in range(rows)]
    columns["psu"] = [generator.randint(1, 25) for _ in range(rows)]
    columns["stratum"] = [generator.randint(1, 4) for _ in range(rows)]
    spec = Specification(
        {"d1": ["i0", "i1"], "d2": ["i2"], "d3": ["i3", "i4"]}
    )
    design = SurveyDesign(weights="w", household_size="size", strata="stratum", psu="psu")
    return pl.DataFrame(columns), spec, design


# --------------------------------------------------------------------------- #
# The defining property: an influence function sums to zero
# --------------------------------------------------------------------------- #
def test_influence_values_sum_to_zero_for_every_estimand():
    _, _, ratios, influence = linearized()
    for key, column in zip(influence.columns, influence.iter_columns()):
        if ratios[key].value is None:
            continue
        assert column.sum() == pytest.approx(0.0, abs=TOLERANCE), key


def test_influence_values_sum_to_zero_on_a_larger_sample():
    frame, spec, design = random_frame()
    _, _, ratios, influence = linearized(0.25, frame, spec, design)
    for key, column in zip(influence.columns, influence.iter_columns()):
        if ratios[key].value is None:
            continue
        assert column.sum() == pytest.approx(0.0, abs=1e-9), key


# --------------------------------------------------------------------------- #
# Hand-computed values, so a wrong sign or a wrong denominator cannot pass
# --------------------------------------------------------------------------- #
def test_influence_of_H_A_and_M0_matches_hand_computation():
    # N = 20, poor population P = 10, censored total C = 9,
    # so H = 0.5, A = 0.9 and M0 = 0.45.
    _, _, ratios, influence = linearized()
    assert ratios["H"].value == pytest.approx(0.5)
    assert ratios["A"].value == pytest.approx(0.9)
    assert ratios["M0"].value == pytest.approx(0.45)

    # u_i = n_i (y_i - R x_i) / X, household by household.
    assert influence["H"].to_list() == pytest.approx([0.05, 0.20, -0.125, -0.125])
    assert influence["A"].to_list() == pytest.approx([-0.08, 0.08, 0.0, 0.0])
    assert influence["M0"].to_list() == pytest.approx([0.005, 0.22, -0.1125, -0.1125])


def test_influence_of_a_weighted_mean_is_the_centred_deviation():
    """With ``x_i = 1`` the ratio is a mean and ``u_i = n_i (y_i - R) / N``."""

    matrix, _, ratios, influence = linearized()
    weights = matrix.frame.select(pl.col(WEIGHT)).to_series().to_list()
    poor = [1.0, 1.0, 0.0, 0.0]
    expected = [n * (y - 0.5) / 20.0 for n, y in zip(weights, poor)]
    assert influence["H"].to_list() == pytest.approx(expected)


# --------------------------------------------------------------------------- #
# The linearization is a derivative: check it numerically
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("key", ["H", "A", "M0", "pctb::i0", "hdk::i2"])
def test_influence_reproduces_the_derivative_of_the_ratio(key):
    """Perturbing one weight moves the ratio by ``delta * u_i / n_i``.

    This is the property that makes the influence function the right object to
    hand to a variance estimator, and it is checked here against the estimand
    compiler itself rather than against a formula restated in the test.
    """

    frame, spec, design = random_frame(seed=13, rows=120)
    matrix = deprivation.build(frame, spec, design)
    estimands = estimands_module.build(spec, 1 / 3)
    ratios = {item.key: item for item in linearization.totals(matrix.frame, estimands)}
    influence = linearization.influence(matrix.frame, tuple(ratios.values()))
    weights = matrix.frame.select(pl.col(WEIGHT)).to_series().to_list()

    target = next(item for item in estimands if item.key == key)
    delta = 1e-6
    for row in (0, 17, 55):
        perturbed = pl.col(WEIGHT) + pl.when(
            pl.int_range(pl.len()) == row
        ).then(delta).otherwise(0.0)
        moved = linearization.totals(matrix.frame, (target,), weight=perturbed)[0].value
        observed = moved - ratios[key].value
        predicted = delta * influence[key][row] / weights[row]
        assert observed == pytest.approx(predicted, rel=1e-5, abs=1e-14)


# --------------------------------------------------------------------------- #
# Composability: the identities that make one linearization stage enough
# --------------------------------------------------------------------------- #
def test_influence_of_M0_is_the_chain_rule_on_H_and_A():
    """``M0 = H * A`` implies ``u(M0) = A * u(H) + H * u(A)``, exactly."""

    frame, spec, design = random_frame(seed=3)
    _, _, ratios, influence = linearized(0.4, frame, spec, design)
    H, A = ratios["H"].value, ratios["A"].value
    combined = A * influence["H"] + H * influence["A"]
    assert combined.to_list() == pytest.approx(influence["M0"].to_list(), abs=1e-15)


def test_absolute_contributions_add_up_to_M0_in_influence_too():
    """``sum_j actb_j = M0`` holds for the influence values, not just the point."""

    frame, spec, design = random_frame(seed=5)
    _, estimands, _, influence = linearized(1 / 3, frame, spec, design)
    keys = [item.key for item in estimands if item.measure == "actb"]
    total = sum((influence[key] for key in keys[1:]), start=influence[keys[0]])
    assert total.to_list() == pytest.approx(influence["M0"].to_list(), abs=1e-15)


def test_relative_contributions_have_zero_total_influence():
    """``sum_j pctb_j = 1`` identically, so the influences must cancel."""

    frame, spec, design = random_frame(seed=5)
    _, estimands, _, influence = linearized(1 / 3, frame, spec, design)
    keys = [item.key for item in estimands if item.measure == "pctb"]
    total = sum((influence[key] for key in keys[1:]), start=influence[keys[0]])
    assert total.to_list() == pytest.approx([0.0] * influence.height, abs=1e-15)


def test_dimension_contributions_are_the_sum_of_their_indicators():
    frame, spec, design = random_frame(seed=8)
    _, estimands, _, influence = linearized(0.3, frame, spec, design)
    for dimension, members in spec.dimensions.items():
        expected = sum(
            (influence[f"pctb::{item}"] for item in members[1:]),
            start=influence[f"pctb::{members[0]}"],
        )
        assert expected.to_list() == pytest.approx(
            influence[f"pctb_dim::{dimension}"].to_list(), abs=1e-15
        )


# --------------------------------------------------------------------------- #
# Aggregating early must not change anything (PLAN.md §7)
# --------------------------------------------------------------------------- #
def test_cluster_influence_equals_row_influence_summed_by_cluster():
    frame, spec, design = random_frame(seed=21)
    matrix = deprivation.build(frame, spec, design)
    estimands = estimands_module.build(spec, 1 / 3)
    ratios = linearization.totals(matrix.frame, estimands)
    rows = linearization.influence(matrix.frame, ratios)

    keys = [item.key for item in estimands]
    by_cluster = (
        matrix.frame.select(STRATUM, PSU)
        .hstack(rows)
        .group_by([STRATUM, PSU])
        .agg([pl.col(key).sum() for key in keys])
        .sort([STRATUM, PSU])
    )
    sums = linearization.cluster_sums(matrix.frame, estimands)
    aggregated = linearization.cluster_influence(sums, ratios).sort([STRATUM, PSU])

    for key in keys:
        assert aggregated[key].to_list() == pytest.approx(
            by_cluster[key].to_list(), abs=1e-12
        ), key


def test_totals_recovered_from_clusters_match_the_direct_totals():
    frame, spec, design = random_frame(seed=33)
    matrix = deprivation.build(frame, spec, design)
    estimands = estimands_module.build(spec, 0.2)
    direct = linearization.totals(matrix.frame, estimands)
    collapsed = linearization.totals_from_clusters(
        linearization.cluster_sums(matrix.frame, estimands), estimands
    )
    for one, other in zip(direct, collapsed):
        assert one.numerator == pytest.approx(other.numerator, rel=1e-12)
        assert one.denominator == pytest.approx(other.denominator, rel=1e-12)


# --------------------------------------------------------------------------- #
# Undefined ratios stay undefined instead of silently becoming zero
# --------------------------------------------------------------------------- #
def test_a_ratio_with_an_empty_denominator_is_none_not_zero():
    """Nobody poor: ``A`` has no denominator, and no influence either."""

    frame = pl.DataFrame({"a": [0, 0], "b": [0, 0]})
    spec = Specification({"d": ["a", "b"]})
    matrix = deprivation.build(frame, spec, SurveyDesign())
    estimands = estimands_module.build(spec, 0.5)
    ratios = {item.key: item for item in linearization.totals(matrix.frame, estimands)}
    assert ratios["A"].value is None
    assert ratios["M0"].value == pytest.approx(0.0)

    influence = linearization.influence(matrix.frame, tuple(ratios.values()))
    assert influence["A"].null_count() == 2
    assert influence["M0"].to_list() == pytest.approx([0.0, 0.0])


def test_domain_weighting_zeroes_the_influence_outside_the_domain():
    """The domain mechanism acts on the weight, before any design is involved."""

    matrix = matrix_of()
    estimands = estimands_module.build(FOUR_SPEC, 1 / 3)
    inside = pl.col(WEIGHT) * (pl.int_range(pl.len()) < 2).cast(pl.Float64)
    ratios = linearization.totals(matrix.frame, estimands, weight=inside)
    influence = linearization.influence(matrix.frame, ratios, weight=inside)
    keyed = {ratio.key: ratio for ratio in ratios}

    # Only households A and B remain: both poor, so H = 1 among the domain.
    assert keyed["H"].value == pytest.approx(1.0)
    assert influence["H"].to_list()[2:] == [0.0, 0.0]
    assert influence["M0"].to_list()[2:] == [0.0, 0.0]
