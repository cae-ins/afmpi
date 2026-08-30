"""Mathematical invariants, true by construction and independent of any software.

PLAN.md §8.B asks for these to run on every commit rather than only at the end
of a phase: they are the cheapest tests in the suite and the fastest to notice
that a change has broken the internal coherence of the calculation. Nothing here
depends on ``mpitb``, ``survey`` or any reference implementation -- only on the
identities of the Alkire-Foster method itself.
"""

import math
import random
from functools import lru_cache

import polars as pl
import pytest

from afmpi import Specification, SurveyDesign, estimate

SPEC = Specification(
    {
        "education": ["i0", "i1"],
        "health": ["i2", "i3", "i4"],
        "living": ["i5", "i6"],
    }
)
CUTOFFS = [0.0, 0.2, 1 / 3, 0.5, 1.0]

DESIGNS = {
    "srs": SurveyDesign(weights="w", household_size="size"),
    "clustered": SurveyDesign(weights="w", household_size="size", psu="psu"),
    "stratified": SurveyDesign(
        weights="w", household_size="size", strata="stratum", psu="psu"
    ),
    "unweighted": SurveyDesign(psu="psu"),
}


def sample(seed=1234, rows=500):
    generator = random.Random(seed)
    return pl.DataFrame(
        {
            **{
                f"i{j}": [
                    # Deliberately uneven, so that no measure is degenerate.
                    1 if generator.random() < 0.2 + 0.1 * j else 0
                    for _ in range(rows)
                ]
                for j in range(7)
            },
            "w": [round(generator.uniform(0.3, 4.0), 4) for _ in range(rows)],
            "size": [generator.randint(1, 10) for _ in range(rows)],
            "psu": [generator.randint(1, 45) for _ in range(rows)],
            "stratum": [generator.randint(1, 6) for _ in range(rows)],
            "region": [generator.choice("ABCD") for _ in range(rows)],
        }
    )


@lru_cache(maxsize=None)
def results(name):
    return estimate(
        sample(),
        SPEC,
        DESIGNS[name],
        k=CUTOFFS,
        over="region",
        ci_method="logit",
    )


def contexts(result):
    """Every (cutoff, subgroup) block of the estimate table."""

    frame = result.estimates()
    keys = frame.select("k", "over", "subgroup").unique(maintain_order=True)
    for key in keys.iter_rows(named=True):
        block = frame.filter(
            (pl.col("k") == key["k"])
            & (
                pl.col("over").is_null()
                if key["over"] is None
                else pl.col("over") == key["over"]
            )
            & (
                pl.col("subgroup").is_null()
                if key["subgroup"] is None
                else pl.col("subgroup") == key["subgroup"]
            )
        )
        values = {}
        for row in block.iter_rows(named=True):
            name = row["measure"]
            if row["indicator"] is not None:
                name = f"{name}::{row['indicator']}"
            elif row["dimension"] is not None:
                name = f"{name}::{row['dimension']}"
            values[name] = row["est"]
        yield key, values


@pytest.mark.parametrize("design", sorted(DESIGNS))
def test_M0_equals_H_times_A(design):
    for key, values in contexts(results(design)):
        if values["A"] is None:
            assert values["M0"] == pytest.approx(0.0, abs=1e-15), key
            continue
        assert values["M0"] == pytest.approx(values["H"] * values["A"], abs=1e-12), key


@pytest.mark.parametrize("design", sorted(DESIGNS))
def test_absolute_contributions_sum_to_M0(design):
    for key, values in contexts(results(design)):
        total = sum(values[f"actb::{name}"] for name in SPEC.indicators)
        assert total == pytest.approx(values["M0"], abs=1e-12), key
        by_dimension = sum(values[f"actb_dim::{name}"] for name in SPEC.dimensions)
        assert by_dimension == pytest.approx(values["M0"], abs=1e-12), key


@pytest.mark.parametrize("design", sorted(DESIGNS))
def test_relative_contributions_sum_to_one(design):
    for key, values in contexts(results(design)):
        if values["M0"] == 0:
            continue
        total = sum(values[f"pctb::{name}"] for name in SPEC.indicators)
        assert total == pytest.approx(1.0, abs=1e-12), key
        by_dimension = sum(values[f"pctb_dim::{name}"] for name in SPEC.dimensions)
        assert by_dimension == pytest.approx(1.0, abs=1e-12), key


@pytest.mark.parametrize("design", sorted(DESIGNS))
def test_contributions_are_the_weighted_censored_headcounts(design):
    """``actb_j = w_j * CH_j`` and ``pctb_j = actb_j / M0``."""

    weights = SPEC.indicator_weights
    for key, values in contexts(results(design)):
        for name in SPEC.indicators:
            assert values[f"actb::{name}"] == pytest.approx(
                weights[name] * values[f"hdk::{name}"], abs=1e-12
            ), (key, name)
            if values["M0"]:
                assert values[f"pctb::{name}"] == pytest.approx(
                    values[f"actb::{name}"] / values["M0"], abs=1e-12
                ), (key, name)


@pytest.mark.parametrize("design", sorted(DESIGNS))
def test_censored_headcounts_never_exceed_uncensored_ones(design):
    for key, values in contexts(results(design)):
        for name in SPEC.indicators:
            assert values[f"hdk::{name}"] <= values[f"hd::{name}"] + 1e-15, (key, name)


@pytest.mark.parametrize("design", sorted(DESIGNS))
def test_every_measure_stays_inside_the_unit_interval(design):
    for row in results(design).estimates().iter_rows(named=True):
        if row["est"] is None:
            continue
        assert 0.0 - 1e-15 <= row["est"] <= 1.0 + 1e-15, row


@pytest.mark.parametrize("design", sorted(DESIGNS))
def test_subgroups_decompose_the_national_M0(design):
    audit = results(design).decomposition()
    assert audit.height == len(CUTOFFS)
    assert audit["error"].max() < 1e-12


def test_a_zero_cutoff_makes_everyone_poor_and_A_the_mean_score():
    result = estimate(sample(), SPEC, DESIGNS["stratified"], k=0.0)
    assert result.H == pytest.approx(1.0)
    # With everyone poor the intensity is the population mean of the score, and
    # M0 collapses onto it too.
    assert result.M0 == pytest.approx(result.A, abs=1e-15)
    scores = result.scores()
    mean = (
        scores.select(
            (pl.col("score") * pl.col("population_weight")).sum()
            / pl.col("population_weight").sum()
        ).item()
    )
    assert result.A == pytest.approx(mean, abs=1e-12)


def test_a_unit_cutoff_only_keeps_those_deprived_everywhere():
    frame = sample()
    result = estimate(frame, SPEC, DESIGNS["stratified"], k=1.0)
    deprived_everywhere = frame.filter(
        pl.all_horizontal([pl.col(name) == 1 for name in SPEC.indicators])
    )
    expected = (
        deprived_everywhere.select((pl.col("w") * pl.col("size")).sum()).item()
        / frame.select((pl.col("w") * pl.col("size")).sum()).item()
    )
    assert result.H == pytest.approx(expected, abs=1e-12)
    if result.H > 0:
        assert result.A == pytest.approx(1.0, abs=1e-12)


def test_standard_errors_are_reported_or_openly_missing_never_invented():
    for design in sorted(DESIGNS):
        for row in results(design).estimates().iter_rows(named=True):
            if row["est"] is None:
                assert math.isnan(row["se"]), row
                continue
            assert row["se"] >= 0 or math.isnan(row["se"]), row
            if math.isnan(row["se"]):
                assert math.isnan(row["lci"]) and math.isnan(row["uci"]), row


def test_the_alkire_foster_weights_sum_to_one():
    assert sum(SPEC.indicator_weights.values()) == pytest.approx(1.0)
    assert sum(SPEC.dimension_weights.values()) == pytest.approx(1.0)
    for dimension, members in SPEC.dimensions.items():
        assert sum(SPEC.indicator_weights[name] for name in members) == pytest.approx(
            SPEC.dimension_weights[dimension]
        )
