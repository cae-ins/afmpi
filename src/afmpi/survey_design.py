"""Sampling design consumed by the Taylor variance path (PLAN.md §6, §14.4a-4c)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .pps import PPSDesign


@dataclass(frozen=True, slots=True)
class Stage:
    """One sampling stage: its unit identifier, its stratification, its FPC."""

    id: str
    strata: str | None = None
    fpc: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("id", "strata", "fpc"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{field_name} must be a non-empty column name or None")
        declared = [
            getattr(self, name)
            for name in ("id", "strata", "fpc")
            if getattr(self, name) is not None
        ]
        if len(set(declared)) != len(declared):
            raise ValueError("id, strata and fpc in Stage must refer to different columns")


@dataclass(frozen=True, slots=True)
class SurveyDesign:
    """Weights, strata and sampling units of a single or multi-stage design.

    For individual-level data, set ``weights`` only. For one row per household,
    set ``household_size`` as well; the effective population weight is then
    ``weights * household_size``, so that the counting unit is the person, not
    the household. Omitting ``weights`` uses one as the base weight.

    Single-stage designs can be declared using ``strata`` and ``psu``, or
    multi-stage designs using ``stages=[Stage(...)]``.
    """

    weights: str | None = None
    household_size: str | None = None
    strata: str | None = None
    psu: str | None = None
    stages: tuple[Stage, ...] | None = field(default=None, kw_only=True)
    pps: PPSDesign | None = field(default=None, kw_only=True)
    lonely_psu: str = field(default="fail", kw_only=True)

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

        if self.stages is not None and (self.strata is not None or self.psu is not None):
            raise ValueError(
                "declare either strata=/psu= (one stage) or stages=[Stage(...)], not both"
            )

        if self.stages is not None:
            if not isinstance(self.stages, (tuple, list)) or len(self.stages) == 0:
                raise ValueError("stages must be a non-empty sequence of Stage objects")
            for st in self.stages:
                if not isinstance(st, Stage):
                    raise ValueError("elements of stages must be Stage instances")
            stage_ids = [st.id for st in self.stages]
            if len(set(stage_ids)) != len(stage_ids):
                raise ValueError("stage ids must be distinct")

            stage_cols = set()
            for st in self.stages:
                stage_cols.add(st.id)
                if st.strata:
                    stage_cols.add(st.strata)
                if st.fpc:
                    stage_cols.add(st.fpc)
            base_cols = {self.weights, self.household_size} - {None}
            overlap = stage_cols & base_cols
            if overlap:
                raise ValueError(
                    f"stage columns cannot overlap with weights/household_size: {overlap}"
                )

            if isinstance(self.stages, list):
                object.__setattr__(self, "stages", tuple(self.stages))

        if self.pps is not None:
            from .pps import PPSDesign

            if not isinstance(self.pps, PPSDesign):
                raise TypeError("pps must be a PPSDesign or None")
            resolved = self.resolved_stages
            if len(resolved) > 1:
                raise ValueError("PPS is supported for one-stage designs only")
            if len(resolved) == 1 and resolved[0].fpc is not None:
                raise ValueError("PPS cannot be combined with fpc at stage 1")

        valid_lonely = {"fail", "certainty", "adjust", "average", "collapse"}
        if self.lonely_psu not in valid_lonely:
            raise ValueError(
                f"lonely_psu must be one of {sorted(valid_lonely)}; got {self.lonely_psu!r}"
            )

    @property
    def resolved_stages(self) -> tuple[Stage, ...]:
        """Canonical stage list, whichever declaration form was used."""

        if self.stages is not None:
            return self.stages
        if self.psu is not None:
            return (Stage(id=self.psu, strata=self.strata, fpc=None),)
        return ()

    @property
    def required_columns(self) -> tuple[str, ...]:
        """Numeric columns multiplied together to form the population weight."""

        return tuple(
            name for name in (self.weights, self.household_size) if name is not None
        )

    @property
    def design_columns(self) -> tuple[str, ...]:
        """Columns identifying the sampling structure."""

        if self.stages is None:
            return tuple(name for name in (self.strata, self.psu) if name is not None)
        res: list[str] = []
        for st in self.stages:
            if st.strata:
                res.append(st.strata)
        for st in self.stages:
            if st.id:
                res.append(st.id)
        for st in self.stages:
            if st.fpc:
                res.append(st.fpc)
        out: list[str] = []
        for col in res:
            if col not in out:
                out.append(col)
        return tuple(out)

    @property
    def has_clusters(self) -> bool:
        return len(self.resolved_stages) > 0 or self.psu is not None
