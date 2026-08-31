"""Phase 2: one-stage design, degrees of freedom and confidence intervals.

The reference values are recomputed inside this file, in plain Python, from the
published formulas -- once as the ultimate-cluster estimator of
``PythonIPM/pipeline/05_indices_ipm.py::ratio_et_ic`` and once as its stratified
generalisation. Comparing the package against a restatement of the formula, on
random data, catches an implementation slip; the hand-computed cases below catch
a wrong formula.

No official ``mpitb`` example is replayed here (PLAN.md §9 phase 2, §11): the
reference dataset ``syn_cdta`` ships inside the ``mpitbR`` CRAN tarball as an
``.rda``, and this machine has neither R, nor Stata, nor an R-data reader, so
the published figures could not be reproduced rather than transcribed. That
comparison stays open.
"""

import math
import random

import polars as pl
import pytest
from scipy import stats

from afmpi import Specification, SurveyDesign, estimate
from afmpi.variance import confidence_interval

TOLERANCE = 1e-12

FOUR_HOUSEHOLDS = pl.DataFrame(
    {
        "i0": [1, 1, 1, 0],
        "i1": [1, 1, 0, 0],
        "i2": [0, 1, 0, 0],
        "i3": [0, 1, 0, 0],
        "taille_menage": [2, 8, 5, 5],
        "ponderation_menage": [1.0, 1.0, 1.0, 1.0],
        "grappe": [1, 2, 3, 4],
    }
)
FOUR_SPEC = Specification({f"d{n}": [f"i{n}"] for n in range(4)})


def sample(seed=101, rows=300):
    generator = random.Random(seed)
    frame = pl.DataFrame(
        {
            **{f"i{j}": [generator.randint(0, 1) for _ in range(rows)] for j in range(4)},
            "w": [round(generator.uniform(0.4, 3.0), 4) for _ in range(rows)],
            "size": [generator.randint(1, 9) for _ in range(rows)],
            "psu": [generator.randint(1, 30) for _ in range(rows)],
            "stratum": [generator.randint(1, 5) for _ in range(rows)],
        }
    )
    spec = Specification({"d1": ["i0", "i1"], "d2": ["i2", "i3"]})
    return frame, spec


def measure_inputs(frame, spec, k):
    """The ``(y, x, n)`` triples of ``H``, ``A`` and ``M0``, computed here."""

    weights = spec.indicator_weights
    scores = [
        sum(weights[name] * frame[name][row] for name in spec.indicators)
        for row in range(frame.height)
    ]
    poor = [1.0 if value >= k else 0.0 for value in scores]
    censored = [value * flag for value, flag in zip(scores, poor, strict=True)]
    n = [frame["w"][row] * frame["size"][row] for row in range(frame.height)]
    return {
        "H": (poor, [1.0] * frame.height, n),
        "A": (censored, poor, n),
        "M0": (censored, [1.0] * frame.height, n),
    }


def reference_se(y, x, n, strata, clusters):
    """Stratified ultimate-cluster standard error of ``sum(n y) / sum(n x)``.

    With a single stratum this is exactly ``ratio_et_ic`` of ``PythonIPM``:
    ``sqrt(m / (m - 1) * sum_c u_c^2)``, since the influence values sum to zero.
    """

    denominator = sum(a * b for a, b in zip(n, x, strict=True))
    ratio = sum(a * b for a, b in zip(n, y, strict=True)) / denominator
    cells: dict[tuple, float] = {}
    for index in range(len(y)):
        key = (strata[index], clusters[index])
        cells[key] = (
            cells.get(key, 0.0) + n[index] * (y[index] - ratio * x[index]) / denominator
        )

    variance = 0.0
    for stratum in {key[0] for key in cells}:
        values = [value for key, value in cells.items() if key[0] == stratum]
        size = len(values)
        if size < 2:
            return math.nan
        mean = sum(values) / size
        variance += size / (size - 1) * sum((value - mean) ** 2 for value in values)
    return math.sqrt(variance)


def se_of(result, measure):
    frame = result.estimates().filter(pl.col("measure") == measure)
    return frame["se"][0]


# --------------------------------------------------------------------------- #
# Against an independently restated formula
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("measure", ["H", "A", "M0"])
def test_clustered_standard_error_matches_the_pythonipm_estimator(measure):
    frame, spec = sample()
    design = SurveyDesign(weights="w", household_size="size", psu="psu")
    result = estimate(frame, spec, design, k=1 / 3)

    y, x, n = measure_inputs(frame, spec, 1 / 3)[measure]
    expected = reference_se(y, x, n, [1] * frame.height, frame["psu"].to_list())
    assert se_of(result, measure) == pytest.approx(expected, rel=1e-12)


@pytest.mark.parametrize("measure", ["H", "A", "M0"])
def test_stratified_standard_error_matches_the_stratified_formula(measure):
    frame, spec = sample(seed=202)
    design = SurveyDesign(weights="w", household_size="size", strata="stratum", psu="psu")
    result = estimate(frame, spec, design, k=0.4)

    y, x, n = measure_inputs(frame, spec, 0.4)[measure]
    expected = reference_se(y, x, n, frame["stratum"].to_list(), frame["psu"].to_list())
    assert se_of(result, measure) == pytest.approx(expected, rel=1e-12)


def test_stratification_is_not_ignored():
    """A stratified design must not silently produce the unstratified answer."""

    frame, spec = sample(seed=303)
    clustered = estimate(
        frame, spec, SurveyDesign(weights="w", household_size="size", psu="psu"), k=1 / 3
    )
    stratified = estimate(
        frame,
        spec,
        SurveyDesign(weights="w", household_size="size", strata="stratum", psu="psu"),
        k=1 / 3,
    )
    assert se_of(clustered, "M0") != pytest.approx(se_of(stratified, "M0"), rel=1e-6)


# --------------------------------------------------------------------------- #
# Hand-computed cases
# --------------------------------------------------------------------------- #
def test_hand_computed_ultimate_cluster_standard_error():
    """Four households, one cluster each; influence of M0 is (0.005, 0.22, -0.1125, -0.1125)."""

    result = estimate(
        FOUR_HOUSEHOLDS,
        FOUR_SPEC,
        SurveyDesign("ponderation_menage", "taille_menage", psu="grappe"),
        k=1 / 3,
        ci_method="t",
    )
    influence = [0.005, 0.22, -0.1125, -0.1125]
    expected = math.sqrt(4 / 3 * sum(value**2 for value in influence))
    assert result.M0 == pytest.approx(0.45)
    assert se_of(result, "M0") == pytest.approx(expected, rel=1e-12)
    assert result.degf()["df"][0] == 3


def test_grouping_households_into_fewer_clusters_widens_the_interval():
    """The check of ``verifier()`` in step 05: correlation must cost precision."""

    def se_with(clusters):
        frame = FOUR_HOUSEHOLDS.with_columns(pl.Series("grappe", clusters))
        result = estimate(
            frame,
            FOUR_SPEC,
            SurveyDesign("ponderation_menage", "taille_menage", psu="grappe"),
            k=1 / 3,
        )
        return se_of(result, "M0")

    assert se_with([1, 1, 2, 2]) > se_with([1, 2, 3, 4])
    assert se_with([1, 1, 2, 2]) == pytest.approx(0.45, rel=1e-12)


def test_a_single_cluster_leaves_the_variance_unestimated():
    """One cluster: report the estimate, refuse to invent an interval."""

    frame = FOUR_HOUSEHOLDS.with_columns(pl.Series("grappe", [1, 1, 1, 1]))
    result = estimate(
        frame,
        FOUR_SPEC,
        SurveyDesign("ponderation_menage", "taille_menage", psu="grappe"),
        k=1 / 3,
    )
    assert result.M0 == pytest.approx(0.45)
    assert math.isnan(se_of(result, "M0"))
    row = result.estimates().filter(pl.col("measure") == "M0").row(0, named=True)
    assert math.isnan(row["lci"]) and math.isnan(row["uci"])
    assert result.degf()["df"][0] == 0


def test_a_lonely_psu_inside_one_stratum_stops_the_variance():
    frame = FOUR_HOUSEHOLDS.with_columns(
        pl.Series("grappe", [1, 2, 3, 4]),
        pl.Series("strate", [1, 1, 1, 2]),
    )
    result = estimate(
        frame,
        FOUR_SPEC,
        SurveyDesign("ponderation_menage", "taille_menage", strata="strate", psu="grappe"),
        k=1 / 3,
    )
    assert result.M0 == pytest.approx(0.45)
    assert math.isnan(se_of(result, "M0"))
    assert result.degf().row(0, named=True) == {"psus": 4, "strata": 2, "df": 2}


# --------------------------------------------------------------------------- #
# Degrees of freedom as a first-class object (PLAN.md §6)
# --------------------------------------------------------------------------- #
def test_degrees_of_freedom_are_psus_minus_strata():
    frame, spec = sample(seed=404)
    result = estimate(
        frame,
        spec,
        SurveyDesign(weights="w", household_size="size", strata="stratum", psu="psu"),
        k=1 / 3,
    )
    degrees = result.degf().row(0, named=True)
    expected = (
        frame.select(pl.struct("stratum", "psu").n_unique()).item()
        - frame.select(pl.col("stratum").n_unique()).item()
    )
    assert degrees["df"] == expected
    assert degrees["df"] == degrees["psus"] - degrees["strata"]


def test_cluster_identifiers_are_read_as_nested_inside_their_stratum():
    """Clusters numbered 1..n_h within each stratum must not be merged."""

    frame = FOUR_HOUSEHOLDS.with_columns(
        pl.Series("grappe", [1, 2, 1, 2]),
        pl.Series("strate", [1, 1, 2, 2]),
    )
    result = estimate(
        frame,
        FOUR_SPEC,
        SurveyDesign("ponderation_menage", "taille_menage", strata="strate", psu="grappe"),
        k=1 / 3,
    )
    degrees = result.degf().row(0, named=True)
    assert degrees["psus"] == 4
    assert degrees["strata"] == 2
    assert degrees["df"] == 2


def test_without_a_declared_cluster_every_row_is_its_own_cluster():
    frame, spec = sample(seed=505, rows=60)
    result = estimate(frame, spec, SurveyDesign(weights="w", household_size="size"), k=1 / 3)
    y, x, n = measure_inputs(frame, spec, 1 / 3)["M0"]
    expected = reference_se(y, x, n, [1] * 60, list(range(60)))
    assert se_of(result, "M0") == pytest.approx(expected, rel=1e-12)
    assert result.degf()["df"][0] == 59


# --------------------------------------------------------------------------- #
# Confidence intervals: both bounding conventions of PLAN.md §4
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("method", ["normal", "t", "logit"])
def test_intervals_bracket_the_estimate_and_respect_the_bounds(method):
    frame, spec = sample(seed=606)
    result = estimate(
        frame,
        spec,
        SurveyDesign(weights="w", household_size="size", strata="stratum", psu="psu"),
        k=1 / 3,
        ci_method=method,
    )
    for row in result.estimates().iter_rows(named=True):
        if row["est"] is None or math.isnan(row["lci"]):
            continue
        assert 0.0 <= row["lci"] <= row["est"] <= row["uci"] <= 1.0, row


def test_logit_interval_follows_the_closed_form_and_differs_from_the_t_interval():
    frame, spec = sample(seed=707)
    design = SurveyDesign(weights="w", household_size="size", strata="stratum", psu="psu")
    logit = estimate(frame, spec, design, k=1 / 3, ci_method="logit")
    student = estimate(frame, spec, design, k=1 / 3, ci_method="t")

    row = logit.estimates().filter(pl.col("measure") == "M0").row(0, named=True)
    quantile = float(stats.t.ppf(0.975, row["df"]))
    centre = math.log(row["est"] / (1 - row["est"]))
    margin = quantile * row["se"] / (row["est"] * (1 - row["est"]))
    assert row["lci"] == pytest.approx(1 / (1 + math.exp(-(centre - margin))), rel=1e-12)
    assert row["uci"] == pytest.approx(1 / (1 + math.exp(-(centre + margin))), rel=1e-12)

    other = student.estimates().filter(pl.col("measure") == "M0").row(0, named=True)
    assert row["lci"] != pytest.approx(other["lci"], rel=1e-6)
    assert other["lci"] == pytest.approx(other["est"] - quantile * other["se"], rel=1e-12)


def test_normal_and_student_intervals_are_truncated_to_the_unit_interval():
    lower, upper = confidence_interval(0.02, 0.5, df=3, method="t")
    assert lower == 0.0 and upper == 1.0
    lower, upper = confidence_interval(0.02, 0.5, df=3, method="t", bounded=False)
    assert lower < 0.0 and upper > 1.0


def test_a_wider_level_gives_a_wider_interval():
    narrow = confidence_interval(0.4, 0.05, df=40, method="t", level=0.90)
    wide = confidence_interval(0.4, 0.05, df=40, method="t", level=0.99)
    assert wide[0] < narrow[0] and narrow[1] < wide[1]


def test_unknown_interval_methods_and_levels_are_rejected():
    with pytest.raises(ValueError, match="ci_method"):
        confidence_interval(0.5, 0.1, df=10, method="bootstrap")
    with pytest.raises(ValueError, match="level"):
        confidence_interval(0.5, 0.1, df=10, method="t", level=1.5)
    with pytest.raises(ValueError, match="ci_method"):
        estimate(FOUR_HOUSEHOLDS, FOUR_SPEC, k=1 / 3, ci_method="jackknife")


def test_summary_reports_the_standard_error_and_the_degrees_of_freedom():
    result = estimate(
        FOUR_HOUSEHOLDS,
        FOUR_SPEC,
        SurveyDesign("ponderation_menage", "taille_menage", psu="grappe"),
        k=1 / 3,
        ci_method="t",
    )
    text = result.summary()
    assert "M0 = 0.450000" in text
    assert "SE(M0) = 0.313555" in text
    assert "df = 3" in text


def test_design_columns_must_be_distinct_and_present():
    with pytest.raises(ValueError, match="different columns"):
        SurveyDesign(weights="w", psu="w")
    with pytest.raises(ValueError, match="columns absent"):
        estimate(FOUR_HOUSEHOLDS, FOUR_SPEC, SurveyDesign(psu="unknown_column"))


def test_missing_design_default_error_rejects_null_design_columns():
    """missing_design='error' (default) rejects nulls in strata/psu/fpc columns."""
    df_missing = FOUR_HOUSEHOLDS.with_columns(
        pl.when(pl.col("grappe") == 1).then(None).otherwise(pl.col("grappe")).alias("grappe")
    )

    design_default = SurveyDesign("ponderation_menage", psu="grappe")
    with pytest.raises(ValueError, match="design column 'grappe' contains 1 missing value"):
        estimate(df_missing, FOUR_SPEC, design_default)

    design_fill = SurveyDesign("ponderation_menage", psu="grappe", missing_design="fill_null")
    res = estimate(df_missing, FOUR_SPEC, design_fill)
    assert res is not None


def test_invalid_missing_design_option_is_rejected():
    with pytest.raises(ValueError, match="missing_design must be 'error' or 'fill_null'"):
        SurveyDesign(missing_design="invalid")
