"""Result container for point estimates and contributions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import polars as pl

InputKind = Literal["polars", "pandas"]


@dataclass(frozen=True, slots=True)
class EstimationResult:
    """Point estimates from one Alkire-Foster poverty cutoff."""

    k: float
    observations: int
    excluded_observations: int
    population: float
    H: float
    A: float
    M0: float
    _indicator_results: pl.DataFrame
    _dimension_results: pl.DataFrame
    _scores: pl.DataFrame
    _input_kind: InputKind

    def to_frame(self):
        """Return the aggregate estimates as a one-row DataFrame.

        The returned frame matches the input family: Polars in, Polars out;
        pandas in, pandas out.
        """

        frame = pl.DataFrame(
            {
                "k": [self.k],
                "observations": [self.observations],
                "excluded_observations": [self.excluded_observations],
                "population": [self.population],
                "H": [self.H],
                "A": [self.A],
                "M0": [self.M0],
            }
        )
        return self._convert(frame)

    def contributions(self):
        """Return ``H_j``, ``CH_j``, ``actb_j``, and ``pctb_j`` by indicator."""

        return self._convert(self._indicator_results.clone())

    def dimension_contributions(self):
        """Return absolute and relative contributions by dimension."""

        return self._convert(self._dimension_results.clone())

    def scores(self):
        """Return row-level ``c_i``, poverty status, and censored ``c_i(k)``."""

        return self._convert(self._scores.clone())

    def summary(self) -> str:
        """Return a compact, human-readable summary."""

        excluded = (
            f" ({self.excluded_observations} excluded by missing-value policy)"
            if self.excluded_observations
            else ""
        )
        return "\n".join(
            (
                f"Alkire-Foster estimates (k={self.k:.6g})",
                f"Observations: {self.observations}{excluded}",
                f"Population weight: {self.population:.6g}",
                f"H  = {self.H:.6f}",
                f"A  = {self.A:.6f}",
                f"M0 = {self.M0:.6f}",
            )
        )

    def _convert(self, frame: pl.DataFrame):
        if self._input_kind == "pandas":
            return frame.to_pandas()
        return frame
