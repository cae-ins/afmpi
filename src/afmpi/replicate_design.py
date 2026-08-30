"""Sampling design consumed by the replication variance path (PLAN.md §14.5a)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from .design_base import Design

_VALID_METHODS = {"JK1", "JKn", "BRR", "Fay_BRR", "bootstrap", "SDR"}


@dataclass(frozen=True, slots=True)
class ReplicateDesign(Design):
    """Replicate-weight design: the estimand is re-evaluated, never linearized.

    Methods JK1, JKn, BRR, Fay_BRR are supported. Methods bootstrap,
    SDR (phase 5c) raise NotImplementedError.
    """

    variance_path: ClassVar[str] = "replication"

    weights: str | None = None
    household_size: str | None = None
    replicate_weights: tuple[str, ...] | None = None
    method: str = "JKn"
    strata: str | None = None
    psu: str | None = None
    fay: float | None = None
    scale: float | None = None
    rscales: tuple[float, ...] | None = None
    combined_weights: bool = True
    mse: bool = True
    replicates: int | None = None
    seed: int = 0
    degf: int | None = None

    def __post_init__(self) -> None:
        if self.method not in _VALID_METHODS:
            raise ValueError(
                f"method must be one of {sorted(_VALID_METHODS)}; got {self.method!r}"
            )
        if self.method in ("bootstrap", "SDR"):
            raise NotImplementedError(
                f"method {self.method!r} is not implemented in phase 5b "
                "(scheduled for phase 5c)"
            )

        for field_name in ("weights", "household_size", "strata", "psu"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{field_name} must be a non-empty column name or None")

        if self.replicate_weights is not None:
            if isinstance(self.replicate_weights, list):
                object.__setattr__(self, "replicate_weights", tuple(self.replicate_weights))
            if not isinstance(self.replicate_weights, tuple) or len(
                self.replicate_weights
            ) == 0:
                raise ValueError("replicate_weights must be a non-empty tuple of column names")
            for name in self.replicate_weights:
                if not isinstance(name, str) or not name.strip():
                    raise ValueError("replicate_weights must contain non-empty column names")
            if len(set(self.replicate_weights)) != len(self.replicate_weights):
                raise ValueError("replicate_weights contains duplicate column names")

        if self.replicate_weights is None and self.psu is None:
            raise ValueError("either replicate_weights or psu must be provided")

        base_cols = {
            self.weights,
            self.household_size,
            self.strata,
            self.psu,
        } - {None}
        if self.replicate_weights is not None:
            overlap = set(self.replicate_weights) & base_cols
            if overlap:
                raise ValueError(
                    "replicate_weights cannot overlap with weights/household_size/strata/psu: "
                    f"{sorted(overlap)}"
                )

        if self.method == "Fay_BRR" and self.fay is None:
            object.__setattr__(self, "fay", 0.5)

        if self.fay is not None:
            if self.method != "Fay_BRR":
                raise ValueError("fay can only be specified when method='Fay_BRR'")
            if not (0 <= self.fay < 1):
                raise ValueError(f"fay must be in [0, 1); got {self.fay!r}")

        if self.rscales is not None:
            if isinstance(self.rscales, list):
                object.__setattr__(self, "rscales", tuple(self.rscales))
            if not isinstance(self.rscales, tuple):
                raise TypeError("rscales must be a tuple of floats")
            rscales_tuples = tuple(float(x) for x in self.rscales)
            object.__setattr__(self, "rscales", rscales_tuples)
            if (
                self.replicate_weights is not None
                and len(self.rscales) != len(self.replicate_weights)
            ):
                raise ValueError(
                    f"rscales length ({len(self.rscales)}) must match replicate_weights "
                    f"length ({len(self.replicate_weights)})"
                )

        if self.degf is not None and (not isinstance(self.degf, int) or self.degf < 1):
            raise ValueError(f"degf must be a positive integer or None; got {self.degf!r}")

    @property
    def required_columns(self) -> tuple[str, ...]:
        """Numeric columns multiplied together to form the population weight."""

        return tuple(
            name for name in (self.weights, self.household_size) if name is not None
        )

    @property
    def design_columns(self) -> tuple[str, ...]:
        """Columns identifying the sampling structure or replicate weights."""

        res: list[str] = []
        for name in (self.strata, self.psu):
            if name is not None and name not in res:
                res.append(name)
        if self.replicate_weights is not None:
            for name in self.replicate_weights:
                if name not in res:
                    res.append(name)
        return tuple(res)
