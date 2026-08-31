"""Sampling design for census data (no sampling variance to estimate) (PLAN.md §14.9)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from .design_base import Design


@dataclass(frozen=True, slots=True)
class CensusDesign(Design):
    """The rows are the whole population: there is no sampling error to estimate.

    Standard errors are identically zero (``se=0.0``), intervals collapse to point
    estimates (``lci=uci=est``), degrees of freedom are zero (``df=0``), and ``ci_method``
    is ignored. Wald tests are undefined.
    """

    variance_path: ClassVar[str] = "census"

    weights: str | None = None
    household_size: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("weights", "household_size"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{field_name} must be a non-empty column name or None")
        if self.weights is not None and self.household_size is not None:
            if self.weights == self.household_size:
                raise ValueError("weights and household_size must refer to different columns")

    @property
    def required_columns(self) -> tuple[str, ...]:
        """Numeric columns multiplied together to form the population weight."""

        return tuple(name for name in (self.weights, self.household_size) if name is not None)

    @property
    def design_columns(self) -> tuple[str, ...]:
        """Columns identifying the sampling structure (none for a census)."""

        return ()

    def test(self, *args, **kwargs):
        """Wald tests are undefined for census data."""

        raise ValueError("a census has no sampling variance; a Wald test is not defined")
