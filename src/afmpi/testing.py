"""Hypothesis testing for Alkire-Foster estimates (PLAN.md §14.7)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HypothesisTest:
    """Wald hypothesis test of contrasts between domains or against zero (PLAN.md §14.7)."""

    terms: tuple[str, ...]
    estimate: float  # L·θ̂ (scalar if q == 1, else nan)
    se: float  # sqrt(L·V·Lᵀ) if q == 1, else nan
    statistic: float
    df1: int  # q, rank of contrast
    df2: int  # degrees of freedom of design
    p_value: float
    method: str = "Wald"
    dist: str = "F"  # "F" | "chisq"

    def __str__(self) -> str:
        if self.df1 == 1:
            return (
                f"HypothesisTest(method={self.method!r}, dist={self.dist!r}, "
                f"statistic={self.statistic:.4f}, df1={self.df1}, df2={self.df2}, "
                f"p_value={self.p_value:.4e}, estimate={self.estimate:.6g}, se={self.se:.6g})"
            )
        return (
            f"HypothesisTest(method={self.method!r}, dist={self.dist!r}, "
            f"statistic={self.statistic:.4f}, df1={self.df1}, df2={self.df2}, "
            f"p_value={self.p_value:.4e})"
        )


__all__ = ["HypothesisTest"]
