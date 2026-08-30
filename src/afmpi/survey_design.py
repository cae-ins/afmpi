"""Survey weights supported by the phase-one estimator."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SurveyDesign:
    """Declare individual or household population weights.

    For individual-level data, set ``weights`` only. For one row per household,
    set ``household_size`` as well; the effective population weight is then
    ``weights * household_size``. Omitting ``weights`` represents an unweighted
    census and uses one as the base weight.

    Clusters and strata intentionally belong to phase 2 and are not accepted.
    """

    weights: str | None = None
    household_size: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("weights", "household_size"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{field_name} must be a non-empty column name or None")
        if self.weights is not None and self.weights == self.household_size:
            raise ValueError("weights and household_size must refer to different columns")

    @property
    def required_columns(self) -> tuple[str, ...]:
        return tuple(
            name for name in (self.weights, self.household_size) if name is not None
        )
