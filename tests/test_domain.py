"""Phase 3: subpopulations, breakdowns, decomposability and k-robustness.

The central claim under test is the one PLAN.md §6 insists on: filtering the
rows before estimating changes the sampling design, and ``afmpi`` must not do
it. The estimates must match a naive filter; the standard errors must not.
"""

import math
import random

import polars as pl
import pytest

from afmpi import Specification, SurveyDesign, estimate

SPEC = Specification({"d1": ["i0", "i1"], "d2": ["i2", "i3"]})

# Three strata of two clusters each. In strata 1 and 3, region "A" is present in
# only one of the two clusters: filtering on region "A" leaves those strata with
# a single cluster and destroys the variance, while zero-weighting keeps them.
LAYOUT = pl.DataFrame(
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
DESIGN = SurveyDesign(weights="w", household_size="size", strata="strate", psu="grappe")


def sample(seed=91, rows=400):
    generator = random.Random(seed)
    frame = pl.DataFrame(
        {
            **{
                f"i{j}": [generator.randint(0, 1) for _ in range(rows)]
                for j in range(4)
            },
            "w": [round(generator.uniform(0.5, 2.5), 4) for _ in range(rows)],
            "size": [generator.randint(1, 9) for _ in range(rows)],
            "psu": [generator.randint(1, 40) for _ in range(rows)],
            "stratum": [generator.randint(1, 5) for _ in range(rows)],
            "region": [
                generator.choice(["north", "south", "east"]) for _ in range(rows)
            ],
            "milieu": [generator.choice(["urban", "rural"]) for _ in range(rows)],
        }
    )
    design = SurveyDesign(
        weights="w", household_size="size", strata="stratum", psu="psu"
    )
    return frame, design


def row_of(result, measure, over=None, subgroup=None):
    frame = result.estimates().filter(pl.col("measure") == measure)
    if over is None:
        frame = frame.filter(pl.col("over").is_null())
    else:
        frame = frame.filter(
            (pl.col("over") == over) & (pl.col("subgroup") == subgroup)
        )
    return frame.row(0, named=True)


# --------------------------------------------------------------------------- #
# A domain is not a filter
# --------------------------------------------------------------------------- #
def test_domain_matches_a_filter_on_the_estimate_but_not_on_the_error():
    frame, design = sample()
    whole = estimate(frame, SPEC, design, k=1 / 3)
    domain = whole.domain("region == 'north'")
    filtered = estimate(
        frame.filter(pl.col("region") == "north"), SPEC, design, k=1 / 3
    )

    for measure in ("H", "A", "M0"):
        assert row_of(domain, measure)["est"] == pytest.approx(
            row_of(filtered, measure)["est"], rel=1e-12
        )
    assert row_of(domain, "M0")["se"] != pytest.approx(
        row_of(filtered, "M0")["se"], rel=1e-9
    )


def test_filtering_can_destroy_a_variance_that_the_domain_keeps():
    """Two strata lose a cluster to the filter; zero-weighting does not."""

    whole = estimate(LAYOUT, SPEC, DESIGN, k=1 / 3)
    domain = whole.domain("region == 'A'")
    filtered = estimate(LAYOUT.filter(pl.col("region") == "A"), SPEC, DESIGN, k=1 / 3)

    assert row_of(domain, "M0")["est"] == pytest.approx(
        row_of(filtered, "M0")["est"], rel=1e-12
    )
    # The filtered design has a single cluster in strata 1 and 3.
    assert math.isnan(row_of(filtered, "M0")["se"])
    # The domain keeps all six clusters, so the variance is still identified.
    assert math.isfinite(row_of(domain, "M0")["se"])
    assert row_of(domain, "M0")["se"] > 0


def test_domain_degrees_of_freedom_count_the_clusters_it_reaches():
    """Variance over the whole design, degrees of freedom over the domain."""

    whole = estimate(LAYOUT, SPEC, DESIGN, k=1 / 3)
    assert whole.degf().row(0, named=True) == {"psus": 6, "strata": 3, "df": 3}

    domain = whole.domain("region == 'A'")
    # Region A is present in clusters 1, 3, 4 and 6, across all three strata.
    assert domain.degf().row(0, named=True) == {"psus": 4, "strata": 3, "df": 1}


def test_domain_accepts_a_polars_expression_and_rejects_an_empty_one():
    whole = estimate(LAYOUT, SPEC, DESIGN, k=1 / 3)
    written = whole.domain("region == 'B'")
    typed = whole.domain(pl.col("region") == "B")
    assert row_of(typed, "M0")["est"] == pytest.approx(row_of(written, "M0")["est"])

    with pytest.raises(ValueError, match="selects no observation"):
        whole.domain("region == 'Z'")


def test_domain_keeps_the_population_of_the_subpopulation_only():
    whole = estimate(LAYOUT, SPEC, DESIGN, k=1 / 3)
    domain = whole.domain("region == 'A'")
    expected = (
        LAYOUT.filter(pl.col("region") == "A")
        .select((pl.col("w") * pl.col("size")).sum())
        .item()
    )
    assert domain.population == pytest.approx(expected)
    assert domain.population < whole.population
    assert "Domain: region == 'A'" in domain.summary()


# --------------------------------------------------------------------------- #
# over=[...] is the same mechanism, applied to every level
# --------------------------------------------------------------------------- #
def test_over_gives_the_same_numbers_as_one_domain_call_per_level():
    frame, design = sample(seed=92)
    broken_down = estimate(frame, SPEC, design, k=1 / 3, over="region")
    whole = estimate(frame, SPEC, design, k=1 / 3)

    for level in ("north", "south", "east"):
        expected = whole.domain(f"region == '{level}'")
        for measure in ("H", "A", "M0"):
            observed = row_of(broken_down, measure, "region", level)
            reference = row_of(expected, measure)
            assert observed["est"] == pytest.approx(reference["est"], rel=1e-12)
            assert observed["se"] == pytest.approx(reference["se"], rel=1e-12)
            assert observed["df"] == reference["df"]


def test_several_over_variables_are_separate_breakdowns_not_a_crossing():
    frame, design = sample(seed=93)
    result = estimate(frame, SPEC, design, k=1 / 3, over=["region", "milieu"])
    table = result.to_frame()
    assert table.filter(pl.col("over").is_null()).height == 1
    assert table.filter(pl.col("over") == "region").height == 3
    assert table.filter(pl.col("over") == "milieu").height == 2
    assert table.height == 6


def test_subgroup_populations_add_up_to_the_whole():
    frame, design = sample(seed=94)
    result = estimate(frame, SPEC, design, k=1 / 3, over="region")
    table = result.to_frame()
    whole = table.filter(pl.col("over").is_null())["population"][0]
    parts = table.filter(pl.col("over") == "region")["population"].sum()
    assert parts == pytest.approx(whole, rel=1e-12)


def test_an_over_variable_with_missing_values_is_refused():
    frame, design = sample(seed=95, rows=60)
    frame = frame.with_columns(
        pl.when(pl.int_range(pl.len()) < 3)
        .then(None)
        .otherwise(pl.col("region"))
        .alias("region")
    )
    with pytest.raises(ValueError, match="must partition the sample"):
        estimate(frame, SPEC, design, k=1 / 3, over="region")


def test_unknown_or_duplicated_over_variables_are_refused():
    frame, design = sample(seed=96, rows=40)
    with pytest.raises(ValueError, match="columns absent"):
        estimate(frame, SPEC, design, k=1 / 3, over="province")
    with pytest.raises(ValueError, match="duplicate variables"):
        estimate(frame, SPEC, design, k=1 / 3, over=["region", "region"])


# --------------------------------------------------------------------------- #
# Decomposability
# --------------------------------------------------------------------------- #
def test_decomposability_is_verified_for_every_over_variable_and_cutoff():
    frame, design = sample(seed=97)
    result = estimate(
        frame, SPEC, design, k=[0.2, 1 / 3, 0.5], over=["region", "milieu"]
    )
    audit = result.decomposition()
    assert audit.height == 6
    assert audit["shares"].to_list() == pytest.approx([1.0] * 6, abs=1e-12)
    assert audit["error"].max() < 1e-12


def test_the_decomposition_is_computed_not_assumed():
    """Recompute ``sum_l phi_l * M0_l`` from the published table itself."""

    frame, design = sample(seed=98)
    result = estimate(frame, SPEC, design, k=1 / 3, over="milieu")
    table = result.to_frame()
    whole = table.filter(pl.col("over").is_null()).row(0, named=True)
    parts = table.filter(pl.col("over") == "milieu")
    recomposed = sum(
        row["population"] / whole["population"] * row["M0"]
        for row in parts.iter_rows(named=True)
    )
    assert recomposed == pytest.approx(whole["M0"], abs=1e-12)


# --------------------------------------------------------------------------- #
# Robustness to k
# --------------------------------------------------------------------------- #
def test_a_list_of_cutoffs_reproduces_one_call_per_cutoff():
    frame, design = sample(seed=99)
    cutoffs = [0.2, 1 / 3, 0.5]
    together = estimate(frame, SPEC, design, k=cutoffs, over="region")
    for cutoff in cutoffs:
        alone = estimate(frame, SPEC, design, k=cutoff, over="region")
        left = together.estimates().filter(pl.col("k") == cutoff)
        right = alone.estimates()
        assert left.height == right.height
        assert left["measure"].to_list() == right["measure"].to_list()
        assert left["subgroup"].to_list() == right["subgroup"].to_list()
        assert left["df"].to_list() == right["df"].to_list()
        for column in ("est", "se", "lci", "uci"):
            assert left[column].to_list() == pytest.approx(
                right[column].to_list(), rel=1e-12, nan_ok=True
            ), column


def test_incidence_and_M0_never_increase_with_the_cutoff():
    frame, design = sample(seed=100)
    result = estimate(frame, SPEC, design, k=[0.0, 0.2, 1 / 3, 0.5, 0.75, 1.0])
    def series(measure):
        return (
            result.estimates()
            .filter(pl.col("measure") == measure)
            .sort("k")["est"]
            .to_list()
        )

    # Ties are expected: with four equally weighted indicators the scores live on
    # a grid, so neighbouring cutoffs can select exactly the same people.
    for measure in ("H", "M0"):
        values = series(measure)
        assert all(
            later <= earlier + 1e-12
            for earlier, later in zip(values, values[1:])
        ), (measure, values)
    intensity = series("A")
    assert all(
        later >= earlier - 1e-12
        for earlier, later in zip(intensity, intensity[1:])
    ), intensity
    assert series("H")[0] == pytest.approx(1.0)


def test_the_cutoff_list_is_validated():
    frame, design = sample(seed=100, rows=40)
    with pytest.raises(ValueError, match="duplicate cutoffs"):
        estimate(frame, SPEC, design, k=[0.2, 0.2])
    with pytest.raises(ValueError, match="at least one cutoff"):
        estimate(frame, SPEC, design, k=[])
    with pytest.raises(ValueError, match="between 0 and 1"):
        estimate(frame, SPEC, design, k=[0.2, 1.4])


def test_several_cutoffs_make_the_scalar_shortcuts_ambiguous():
    frame, design = sample(seed=100, rows=40)
    result = estimate(frame, SPEC, design, k=[0.2, 0.5])
    assert result.k == (0.2, 0.5)
    with pytest.raises(ValueError, match="several cutoffs"):
        _ = result.M0
    assert result.to_frame().height == 2
    assert result.scores().height == 80
