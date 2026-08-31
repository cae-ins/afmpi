"""Explicit resource budget for dataset ingestion and execution (PLAN.md §14.9)."""

from __future__ import annotations

from dataclasses import dataclass
import warnings


@dataclass(frozen=True, slots=True)
class ExecutionConfig:
    """Explicit resource constraints for afmpi execution plans.

    Parameters
    ----------
    max_threads : int | None, optional
        Maximum number of threads for thread pool execution.
        Note: Polars manages its thread pool globally per process, read once from
        ``POLARS_MAX_THREADS`` at the first Polars operation of the process. afmpi
        sets that environment variable on your behalf (via ``os.environ.setdefault``,
        so it never overrides a value already in place), but this only takes effect
        if this call happens to be the first Polars operation in the process; a
        mismatched later request emits a ``UserWarning`` instead of silently doing
        nothing. There is no per-call thread isolation -- two concurrent
        ``estimate()`` calls in the same process cannot each get their own cap.
    memory_limit : str | None, optional
        Currently a no-op in this version of afmpi. Polars does not provide a
        per-query strict memory cap API. Passing a non-None value emits a warning.
    spill_dir : str | None, optional
        Currently a no-op in this version of afmpi. Out-of-core directory configuration
        is not supported per-query. Passing a non-None value emits a warning.
    batch_size : int | None, optional
        Number of replicate weights processed per batch in replication variance routines,
        overriding default batching behavior.
    """

    max_threads: int | None = None
    memory_limit: str | None = None
    spill_dir: str | None = None
    batch_size: int | None = None

    def __post_init__(self) -> None:
        if self.memory_limit is not None:
            warnings.warn(
                f"ExecutionConfig.memory_limit={self.memory_limit!r} is currently a no-op "
                "in this version of afmpi; Polars does not expose a per-query memory cap.",
                UserWarning,
                stacklevel=2,
            )
        if self.spill_dir is not None:
            warnings.warn(
                f"ExecutionConfig.spill_dir={self.spill_dir!r} is currently a no-op "
                "in this version of afmpi; out-of-core spill directory configuration is not active.",
                UserWarning,
                stacklevel=2,
            )
