"""Performance, scale, and streaming tests for afmpi (PLAN.md §14.9)."""

from __future__ import annotations

import os
import re
from pathlib import Path
from unittest.mock import patch

import polars as pl
import psutil
import pytest
from polars.testing import assert_frame_equal

import afmpi.estimation as estimation_module
from afmpi import (
    CensusDesign,
    ExecutionConfig,
    PPSDesign,
    ReplicateDesign,
    Specification,
    Stage,
    SurveyDesign,
    estimate,
    from_parquet,
)
from afmpi.replicate_estimation import replicate_totals


@pytest.fixture
def sample_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "ind1": [1, 0, 1, 0, 1, 0, 1, 1, 0, 1] * 10,
            "ind2": [0, 1, 1, 0, 0, 1, 1, 0, 0, 1] * 10,
            "ind3": [1, 1, 0, 0, 1, 0, 1, 1, 1, 0] * 10,
            "weight": [1.5] * 100,
            "psu": ([1, 1, 2, 2, 3, 3, 4, 4, 5, 5] * 10),
            "region": (["North", "South", "East", "West", "Central"] * 20),
        }
    )


def test_lazy_collect_identical_to_eager(sample_df):
    spec = Specification(dimensions={"d1": ["ind1", "ind2"], "d2": ["ind3"]})
    design = SurveyDesign(weights="weight", psu="psu")

    res_eager = estimate(sample_df, spec, design, k=0.33, lazy=False)
    res_lazy = estimate(sample_df, spec, design, k=0.33, lazy=True).collect()

    df_eager = res_eager.estimates()
    df_lazy = res_lazy.estimates()

    assert_frame_equal(df_eager, df_lazy, check_exact=False, atol=1e-10)


def test_parquet_projection_pushdown(tmp_path: Path, sample_df):
    parquet_path = tmp_path / "test_data.parquet"
    extended_df = sample_df.with_columns(
        pl.lit("unused_val").alias("extra_col1"),
        pl.lit(999).alias("extra_col2"),
    )
    extended_df.write_parquet(parquet_path)

    spec = Specification(dimensions={"d1": ["ind1", "ind2"]})
    design = CensusDesign(weights="weight")
    src = from_parquet(parquet_path)

    res = src.estimate(spec, design, k=0.33, over="region")
    if hasattr(res, "collect"):
        res = res.collect()

    diag = res.diagnostics()
    proj_rows = diag.filter(pl.col("topic") == "projection_pushdown")
    assert proj_rows.height == 1
    detail = proj_rows.row(0, named=True)["detail"]
    projected = [c.strip() for c in detail.split(",")]

    expected = sorted(["ind1", "ind2", "weight", "region"])
    assert sorted(projected) == expected
    assert "extra_col1" not in projected
    assert "extra_col2" not in projected


def test_parquet_100k_matches_memory(tmp_path: Path, monkeypatch):
    from benchmarks.generate_census import generate_census_parquet

    parquet_path = tmp_path / "census_100k.parquet"
    generate_census_parquet(parquet_path, n_rows=100_000)

    spec = Specification(
        dimensions={
            "d1": ["ind1", "ind2", "ind3"],
            "d2": ["ind4", "ind5"],
        },
    )
    design = CensusDesign(weights="weight")

    # In memory
    df_mem = pl.read_parquet(parquet_path)
    res_mem = estimate(df_mem, spec, design, k=[0.2, 0.33, 0.5], over="region")

    # Instrument collect_all to verify complexity invariance (1 national plan + 1 over plan)
    original_collect_all = pl.collect_all
    captured: list[pl.LazyFrame] = []

    def spy_collect_all(plans, *args, **kwargs):
        captured.extend(plans)
        return original_collect_all(plans, *args, **kwargs)

    monkeypatch.setattr(estimation_module.pl, "collect_all", spy_collect_all)

    # From parquet
    src = from_parquet(parquet_path)
    res_parquet = src.estimate(spec, design, k=[0.2, 0.33, 0.5], over="region")
    if hasattr(res_parquet, "collect"):
        res_parquet = res_parquet.collect()

    # Complexity assertion: exactly 2 collected plans and 1 shared scan cache
    assert len(captured) == 2, f"Expected 2 plans (national + region), got {len(captured)}"
    explained = pl.explain_all(captured)
    cache_ids = set(re.findall(r"CACHE\[id: (\w+)", explained))
    assert len(cache_ids) == 1, f"Expected single shared scan cache, got {len(cache_ids)}"

    # Accuracy assertion across all cutoffs and dimensions
    assert_frame_equal(
        res_mem.estimates(), res_parquet.estimates(), check_exact=False, atol=1e-10
    )


def test_streaming_retains_no_line_level_matrix(tmp_path: Path, sample_df):
    parquet_path = tmp_path / "test_stream.parquet"
    sample_df.write_parquet(parquet_path)

    spec = Specification(dimensions={"d1": ["ind1", "ind2"]})
    design = CensusDesign(weights="weight")
    src = from_parquet(parquet_path, streaming=True)

    res = src.estimate(spec, design, k=0.33)
    if hasattr(res, "collect"):
        res = res.collect()

    assert res._matrix is None

    with pytest.raises(ValueError, match="scores\\(\\) requires an in-memory result"):
        res.scores()

    with pytest.raises(ValueError, match="domain\\(\\) requires an in-memory result"):
        res.domain("region == 'North'")


def test_resources_none_identical_to_default(sample_df):
    spec = Specification(dimensions={"d1": ["ind1", "ind2"]})
    design = SurveyDesign(weights="weight", psu="psu")

    res_default = estimate(sample_df, spec, design, k=0.33)
    res_none = estimate(sample_df, spec, design, k=0.33, resources=None)

    assert_frame_equal(
        res_default.estimates(), res_none.estimates(), check_exact=False, atol=1e-10
    )


def test_execution_config_batch_size(sample_df):
    """ExecutionConfig(batch_size=N) actually changes the batch size replicate_totals
    is called with -- spied the same way as test_over_decomposability_and_scan_count
    (test 6, phase 5a) spies replicate_totals call count."""

    spec = Specification(dimensions={"d1": ["ind1", "ind2"]})
    design = ReplicateDesign(weights="weight", psu="psu", method="bootstrap", replicates=20)

    config = ExecutionConfig(batch_size=5)
    with patch("afmpi.estimation.replicate_totals", wraps=replicate_totals) as spy:
        res = estimate(sample_df, spec, design, k=0.33, resources=config)
        assert res.M0 is not None
        assert spy.call_count >= 1
        for call in spy.call_args_list:
            assert call.kwargs.get("batch_size") == 5

    with patch("afmpi.estimation.replicate_totals", wraps=replicate_totals) as spy_default:
        estimate(sample_df, spec, design, k=0.33)
        for call in spy_default.call_args_list:
            assert call.kwargs.get("batch_size") == 64


def test_streaming_single_scan_independent_of_k_and_over(
    tmp_path: Path, sample_df, monkeypatch
):
    """The number of collected Polars plans (and hence physical parquet scans, via
    Polars' common-subplan elimination on the shared upstream plan) must not grow
    with the number of k thresholds -- only with the number of `over` variables."""

    parquet_path = tmp_path / "test_scan_count.parquet"
    sample_df.write_parquet(parquet_path)

    spec = Specification(dimensions={"d1": ["ind1", "ind2"], "d2": ["ind3"]})
    design = CensusDesign(weights="weight")
    src = from_parquet(parquet_path)

    original_collect_all = pl.collect_all
    captured: list[pl.LazyFrame] = []

    def spy_collect_all(plans, *args, **kwargs):
        captured.extend(plans)
        return original_collect_all(plans, *args, **kwargs)

    monkeypatch.setattr(estimation_module.pl, "collect_all", spy_collect_all)

    for k_values in ([0.3], [0.2, 0.25, 0.3, 0.33, 0.4]):
        captured.clear()
        res = src.estimate(spec, design, k=k_values, over="region")
        if hasattr(res, "collect"):
            res = res.collect()

        # 1 national plan + 1 plan for the single `over` variable, whatever len(k_values) is.
        assert len(captured) == 2, (
            f"expected 2 collected plans (national + 1 over-variable) independent of "
            f"{len(k_values)} k thresholds, got {len(captured)}"
        )

        explained = pl.explain_all(captured)
        cache_ids = set(re.findall(r"CACHE\[id: (\w+)", explained))
        assert len(cache_ids) == 1, (
            "expected a single shared CACHE node (one physical parquet scan reused "
            f"across all collected plans) regardless of k/over count; found "
            f"{len(cache_ids)} distinct scan caches:\n{explained}"
        )


@pytest.mark.slow
def test_full_10m_census_benchmark(tmp_path: Path):
    """Full 10,000,000 row census performance benchmark."""
    import time

    from benchmarks.generate_census import generate_census_parquet

    parquet_path = tmp_path / "census_10m.parquet"
    print("\n[BENCHMARK] Generating 10M synthetic census dataset...")
    generate_census_parquet(parquet_path, n_rows=10_000_000)

    spec = Specification(
        dimensions={
            f"d{i}": [f"ind{i * 3 + 1}", f"ind{i * 3 + 2}", f"ind{i * 3 + 3}"]
            for i in range(10)
        },
    )
    design = CensusDesign(weights="weight")
    resources = ExecutionConfig(max_threads=8)

    process = psutil.Process(os.getpid())
    mem_before = process.memory_info().rss

    t0 = time.perf_counter()
    src = from_parquet(parquet_path)
    res = src.estimate(
        spec,
        design,
        k=[0.2, 0.25, 0.3, 0.33, 0.4, 0.5, 0.6, 0.7],
        over=["region", "department", "subprefecture"],
        resources=resources,
    )
    if hasattr(res, "collect"):
        res = res.collect()

    t_elapsed = time.perf_counter() - t0
    mem_after = process.memory_info().rss
    peak_ram_gb = (mem_after - mem_before) / (1024**3)
    threads_observed = pl.thread_pool_size()

    print(
        f"\n[BENCHMARK 10M RESULT] Time: {t_elapsed:.2f}s | "
        f"Peak RAM: {peak_ram_gb:.3f} GB | Threads: {threads_observed}"
    )

    assert t_elapsed < 300.0, f"Benchmark elapsed time {t_elapsed:.2f}s exceeded 300s target"


_MIN_RAM_30M_BYTES = 20 * (1024**3)  # 20 GB
_MIN_RAM_50M_BYTES = 28 * (1024**3)  # 28 GB
_has_enough_ram_30m = psutil.virtual_memory().total >= _MIN_RAM_30M_BYTES
_has_enough_ram_50m = psutil.virtual_memory().total >= _MIN_RAM_50M_BYTES


@pytest.mark.slow
@pytest.mark.skipif(
    not _has_enough_ram_30m,
    reason="Full 30M benchmark requires at least 20 GB of RAM",
)
def test_full_30m_census_benchmark(tmp_path: Path):
    """Full 30,000,000 row census performance benchmark."""
    import time

    from benchmarks.generate_census import generate_census_parquet

    parquet_path = tmp_path / "census_30m.parquet"
    print("\n[BENCHMARK] Generating 30M synthetic census dataset...")
    generate_census_parquet(parquet_path, n_rows=30_000_000)

    spec = Specification(
        dimensions={
            f"d{i}": [f"ind{i * 3 + 1}", f"ind{i * 3 + 2}", f"ind{i * 3 + 3}"]
            for i in range(10)
        },
    )
    design = CensusDesign(weights="weight")
    resources = ExecutionConfig(max_threads=8, isolated_process=True)

    process = psutil.Process(os.getpid())
    mem_before = process.memory_info().rss

    t0 = time.perf_counter()
    src = from_parquet(parquet_path)
    res = src.estimate(
        spec,
        design,
        k=[0.2, 0.25, 0.3, 0.33, 0.4, 0.5, 0.6, 0.7],
        over=["region", "department", "subprefecture"],
        resources=resources,
    )
    if hasattr(res, "collect"):
        res = res.collect()

    t_elapsed = time.perf_counter() - t0
    mem_after = process.memory_info().rss
    peak_ram_gb = (mem_after - mem_before) / (1024**3)

    print(f"\n[BENCHMARK 30M RESULT] Time: {t_elapsed:.2f}s | Peak RAM: {peak_ram_gb:.3f} GB")

    assert t_elapsed < 600.0, f"Benchmark elapsed time {t_elapsed:.2f}s exceeded 600s target"


@pytest.mark.slow
@pytest.mark.skipif(
    not _has_enough_ram_50m,
    reason="Full 50M benchmark requires at least 28 GB of RAM",
)
def test_full_50m_census_benchmark(tmp_path: Path):
    """Full 50,000,000 row census performance benchmark."""
    import time

    from benchmarks.generate_census import generate_census_parquet

    parquet_path = tmp_path / "census_50m.parquet"
    print("\n[BENCHMARK] Generating 50M synthetic census dataset...")
    generate_census_parquet(parquet_path, n_rows=50_000_000)

    spec = Specification(
        dimensions={
            f"d{i}": [f"ind{i * 3 + 1}", f"ind{i * 3 + 2}", f"ind{i * 3 + 3}"]
            for i in range(10)
        },
    )
    design = CensusDesign(weights="weight")
    resources = ExecutionConfig(max_threads=8, isolated_process=True)

    process = psutil.Process(os.getpid())
    mem_before = process.memory_info().rss

    t0 = time.perf_counter()
    src = from_parquet(parquet_path)
    res = src.estimate(
        spec,
        design,
        k=[0.2, 0.25, 0.3, 0.33, 0.4, 0.5, 0.6, 0.7],
        over=["region", "department", "subprefecture"],
        resources=resources,
    )
    if hasattr(res, "collect"):
        res = res.collect()

    t_elapsed = time.perf_counter() - t0
    mem_after = process.memory_info().rss
    peak_ram_gb = (mem_after - mem_before) / (1024**3)

    print(f"\n[BENCHMARK 50M RESULT] Time: {t_elapsed:.2f}s | Peak RAM: {peak_ram_gb:.3f} GB")

    assert t_elapsed < 900.0, f"Benchmark elapsed time {t_elapsed:.2f}s exceeded 900s target"


# -----------------------------------------------------------------------------
# Parity tests between eager and lazy/streaming paths (PLAN.md §14.9, STAMP13)
# -----------------------------------------------------------------------------


def test_lazy_parity_all_missing_policies() -> None:
    df_missing = pl.DataFrame(
        {
            "ind1": [1, 0, None, 0, 1, 0, 1, None, 0, 1] * 10,
            "ind2": [0, 1, 1, 0, None, 1, 1, 0, 0, 1] * 10,
            "ind3": [1, 1, 0, 0, 1, None, 1, 1, 1, 0] * 10,
            "weight": [1.5] * 100,
            "psu": ([1, 1, 2, 2, 3, 3, 4, 4, 5, 5] * 10),
            "region": (["North", "South", "East", "West", "Central"] * 20),
        }
    )
    design = SurveyDesign(weights="weight", psu="psu")

    for policy in ("listwise_deletion", "reweighting", "treat_as_nondeprived"):
        spec = Specification(
            dimensions={"d1": ["ind1", "ind2"], "d2": ["ind3"]},
            missing_policy=policy,
        )
        res_eager = estimate(df_missing, spec, design, k=0.33, lazy=False)
        res_lazy = estimate(df_missing, spec, design, k=0.33, lazy=True).collect()
        assert_frame_equal(
            res_eager.estimates(), res_lazy.estimates(), check_exact=False, atol=1e-10
        )

    # Custom callable policy (treat_as_deprived)
    def custom_policy(df, spec):
        weights = spec.indicator_weights
        indicators = spec.indicators
        g_cols = [
            pl.col(item).cast(pl.Float64).fill_null(1.0).alias(f"__afmpi_g{idx}")
            for idx, item in enumerate(indicators)
        ]
        obs_cols = [
            pl.lit(1.0, dtype=pl.Float64).alias(f"__afmpi_obs{idx}")
            for idx in range(len(indicators))
        ]
        wc_cols = [
            (pl.col(f"__afmpi_g{idx}") * weights[item]).alias(f"__afmpi_wc{idx}")
            for idx, item in enumerate(indicators)
        ]
        return df.with_columns(*g_cols, *obs_cols).with_columns(*wc_cols)

    spec_custom = Specification(
        dimensions={"d1": ["ind1", "ind2"], "d2": ["ind3"]},
        missing_policy=custom_policy,
    )
    res_eager = estimate(df_missing, spec_custom, design, k=0.33, lazy=False)
    res_lazy = estimate(df_missing, spec_custom, design, k=0.33, lazy=True).collect()
    assert_frame_equal(
        res_eager.estimates(), res_lazy.estimates(), check_exact=False, atol=1e-10
    )


def test_lazy_parity_domain_survey_design(sample_df: pl.DataFrame) -> None:
    spec = Specification(dimensions={"d1": ["ind1", "ind2"], "d2": ["ind3"]})
    design = SurveyDesign(weights="weight", psu="psu")

    res_eager = estimate(
        sample_df, spec, design, k=0.33, domain="region == 'North'", lazy=False
    )
    res_lazy = estimate(
        sample_df, spec, design, k=0.33, domain="region == 'North'", lazy=True
    ).collect()

    assert_frame_equal(
        res_eager.estimates(), res_lazy.estimates(), check_exact=False, atol=1e-10
    )


def test_lazy_parity_stage_fpc(sample_df: pl.DataFrame) -> None:
    spec = Specification(dimensions={"d1": ["ind1", "ind2"], "d2": ["ind3"]})
    # Sampling fraction
    df_fpc = sample_df.with_columns(pl.lit(0.2).alias("fpc1"))
    design_fpc = SurveyDesign(
        weights="weight", stages=[Stage(id="psu", strata="region", fpc="fpc1")]
    )
    res_eager = estimate(df_fpc, spec, design_fpc, k=0.33, lazy=False)
    res_lazy = estimate(df_fpc, spec, design_fpc, k=0.33, lazy=True).collect()
    assert_frame_equal(
        res_eager.estimates(), res_lazy.estimates(), check_exact=False, atol=1e-10
    )

    # Population counts N_h
    df_fpc_pop = sample_df.with_columns(pl.lit(100.0).alias("N_h"))
    design_pop = SurveyDesign(
        weights="weight", stages=[Stage(id="psu", strata="region", fpc="N_h")]
    )
    res_eager2 = estimate(df_fpc_pop, spec, design_pop, k=0.33, lazy=False)
    res_lazy2 = estimate(df_fpc_pop, spec, design_pop, k=0.33, lazy=True).collect()
    assert_frame_equal(
        res_eager2.estimates(), res_lazy2.estimates(), check_exact=False, atol=1e-10
    )


def test_lazy_parity_pps_design(sample_df: pl.DataFrame) -> None:
    spec = Specification(dimensions={"d1": ["ind1", "ind2"], "d2": ["ind3"]})
    df_pps = sample_df.with_columns((pl.col("psu").cast(pl.Float64) / 10.0).alias("pi"))

    for method, variance in [
        ("with_replacement", "auto"),
        ("without_replacement", "hajek"),
    ]:
        pps_conf = PPSDesign(method=method, variance=variance, inclusion_probability="pi")
        design_pps = SurveyDesign(weights="weight", psu="psu", pps=pps_conf)
        res_eager = estimate(df_pps, spec, design_pps, k=0.33, lazy=False)
        res_lazy = estimate(df_pps, spec, design_pps, k=0.33, lazy=True).collect()
        assert_frame_equal(
            res_eager.estimates(), res_lazy.estimates(), check_exact=False, atol=1e-10
        )
        design_pps = SurveyDesign(weights="weight", psu="psu", pps=pps_conf)
        res_eager = estimate(df_pps, spec, design_pps, k=0.33, lazy=False)
        res_lazy = estimate(df_pps, spec, design_pps, k=0.33, lazy=True).collect()
        assert_frame_equal(
            res_eager.estimates(), res_lazy.estimates(), check_exact=False, atol=1e-10
        )


def test_lazy_parity_replicate_design(sample_df: pl.DataFrame) -> None:
    spec = Specification(dimensions={"d1": ["ind1", "ind2"], "d2": ["ind3"]})

    # Bootstrap
    design_boot = ReplicateDesign(
        weights="weight", psu="psu", method="bootstrap", replicates=20, seed=42
    )
    res_eager_boot = estimate(sample_df, spec, design_boot, k=0.33, lazy=False)
    res_lazy_boot = estimate(sample_df, spec, design_boot, k=0.33, lazy=True).collect()
    assert_frame_equal(
        res_eager_boot.estimates(), res_lazy_boot.estimates(), check_exact=False, atol=1e-10
    )

    # JKn
    design_jkn = ReplicateDesign(weights="weight", psu="psu", strata="region", method="JKn")
    res_eager_jkn = estimate(sample_df, spec, design_jkn, k=0.33, lazy=False)
    res_lazy_jkn = estimate(sample_df, spec, design_jkn, k=0.33, lazy=True).collect()
    assert_frame_equal(
        res_eager_jkn.estimates(), res_lazy_jkn.estimates(), check_exact=False, atol=1e-10
    )

    # BRR (with 2 PSUs per stratum)
    df_brr = sample_df.with_columns(
        pl.when(pl.col("psu") <= 2)
        .then(pl.lit("Stratum1"))
        .otherwise(pl.lit("Stratum2"))
        .alias("strata_brr"),
        pl.when(pl.col("psu") % 2 == 1)
        .then(pl.lit("PSU1"))
        .otherwise(pl.lit("PSU2"))
        .alias("psu_brr"),
    )
    design_brr = ReplicateDesign(
        weights="weight", psu="psu_brr", strata="strata_brr", method="BRR"
    )
    res_eager_brr = estimate(df_brr, spec, design_brr, k=0.33, lazy=False)
    res_lazy_brr = estimate(df_brr, spec, design_brr, k=0.33, lazy=True).collect()
    assert_frame_equal(
        res_eager_brr.estimates(), res_lazy_brr.estimates(), check_exact=False, atol=1e-10
    )


def test_isolated_process_execution(sample_df: pl.DataFrame) -> None:
    spec = Specification(dimensions={"d1": ["ind1", "ind2"], "d2": ["ind3"]})
    design = SurveyDesign(weights="weight", psu="psu")

    cfg_isolated = ExecutionConfig(max_threads=2, isolated_process=True)
    res_normal = estimate(sample_df, spec, design, k=0.33)
    res_isolated = estimate(sample_df, spec, design, k=0.33, resources=cfg_isolated)

    assert_frame_equal(
        res_normal.estimates(), res_isolated.estimates(), check_exact=False, atol=1e-10
    )


def test_first_call_max_threads_warning() -> None:
    """Point 5: max_threads emits warning on first call if actual thread pool != requested."""
    import subprocess
    import sys

    cmd = [
        sys.executable,
        "-c",
        """
import warnings, polars as pl
# Force thread pool initialization as happens in realistic usage
_ = pl.thread_pool_size()

import sys; sys.path.insert(0, 'src')
from afmpi import Specification, SurveyDesign, ExecutionConfig, estimate

data = pl.DataFrame({'ind1': [1, 0], 'ind2': [0, 1], 'w': [1.0, 1.0]})
spec = Specification({'d1': ['ind1'], 'd2': ['ind2']})
design = SurveyDesign(weights='w')
cfg = ExecutionConfig(max_threads=1)

with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter('always')
    estimate(data, spec, design, resources=cfg)
    msg_list = [str(item.message) for item in w]
    assert any('has no effect' in m for m in msg_list), f'Expected warning, got: {msg_list}'
print('OK')
""",
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True)
    assert "OK" in out.stdout
