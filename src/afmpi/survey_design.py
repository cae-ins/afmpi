"""Sampling design consumed by the Taylor variance path (PLAN.md §6)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SurveyDesign:
    """Weights, strata and primary sampling units of a one-stage design.

    For individual-level data, set ``weights`` only. For one row per household,
    set ``household_size`` as well; the effective population weight is then
    ``weights * household_size``, so that the counting unit is the person, not
    the household. Omitting ``weights`` uses one as the base weight.

    ``strata`` and ``psu`` drive the variance:

    * neither declared -- every row is its own cluster inside a single stratum,
      which is the with-replacement simple random sampling variance (the same
      convention as ``ids = ~1`` in the R ``survey`` package);
    * ``psu`` only -- ultimate cluster variance over a single stratum, the
      estimator used by ``PythonIPM``;
    * both -- stratified ultimate cluster variance, with cluster identifiers
      read as nested inside their stratum.

    This is the one-stage design of PLAN.md §9 phase 2. Arbitrary stages
    (``stages=[Stage(...)]``), finite population corrections, PPS and the five
    lonely-PSU behaviours are phases 4a-4c and are deliberately not accepted
    here rather than being silently ignored.
    """

    weights: str | None = None
    household_size: str | None = None
    strata: str | None = None
    psu: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("weights", "household_size", "strata", "psu"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{field_name} must be a non-empty column name or None")
        declared = [
            getattr(self, name)
            for name in ("weights", "household_size", "strata", "psu")
            if getattr(self, name) is not None
        ]
        if len(set(declared)) != len(declared):
            raise ValueError(
                "weights, household_size, strata and psu must refer to different columns"
            )

    @property
    def required_columns(self) -> tuple[str, ...]:
        """Numeric columns multiplied together to form the population weight."""

        return tuple(
            name for name in (self.weights, self.household_size) if name is not None
        )

    @property
    def design_columns(self) -> tuple[str, ...]:
        """Columns identifying the sampling structure."""

        return tuple(name for name in (self.strata, self.psu) if name is not None)

    @property
    def has_clusters(self) -> bool:
        return self.psu is not None
