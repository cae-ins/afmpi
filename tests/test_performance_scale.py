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
    ReplicateDesign,
    Specification,
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

    with pytest.raises(ValueError, match="scores\\(\\) requires an in-memory result"):
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
        f"\n[BENCHMARK RESULT] Time: {t_elapsed:.2f}s | "
        f"Peak RAM: {peak_ram_gb:.3f} GB | Threads: {threads_observed}"
    )

    assert t_elapsed < 300.0, f"Benchmark elapsed time {t_elapsed:.2f}s exceeded 300s target"
