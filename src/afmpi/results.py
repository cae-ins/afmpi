"""Result container: estimates, intervals, degrees of freedom, contributions."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import polars as pl

from .deprivation import SCORE, WEIGHT, DeprivationMatrix
from .missing import MissingReport

InputKind = str

_AGGREGATE = ("H", "A", "M0")
_INDICATOR_NAMES = {"hd": "H_j", "hdk": "CH_j", "actb": "actb_j", "pctb": "pctb_j"}
_DIMENSION_NAMES = {"actb_dim": "actb_dim", "pctb_dim": "pctb_dim"}


@dataclass(frozen=True, slots=True)
class EstimationResult:
    """Alkire-Foster estimates with their design-based inference.

    :meth:`estimates` is the primary, always-rectangular output: one row per
    (measure, indicator, cutoff, subgroup) with ``est``, ``se``, ``lci``,
    ``uci``, ``cv`` and ``df``. The other accessors are convenience views of the
    same table.

    Those views carry the identifying columns only when they actually vary: a
    single cutoff and no ``over`` produce the compact table, and asking for
    several cutoffs or a breakdown adds the ``k``, ``over`` and ``subgroup``
    columns that tell the rows apart. Frames follow the input family: Polars in,
    Polars out; pandas in, pandas out.
    """

    _estimates: pl.DataFrame
    _decomposition: pl.DataFrame
    _matrix: DeprivationMatrix | None
    _cutoffs: tuple[float, ...]
    _over: tuple[str, ...]
    _domain: tuple[str | None, str | None] | None
    _ci_method: str
    _level: float
    _tvar: str | None = None
    _cot_year: str | None = None
    _changes: pl.DataFrame | None = None
    _overlap: str = "auto"
    _panel_id: str | None = None
    _diagnostics: pl.DataFrame | None = None
    observations: int = 0
    excluded_observations: int = 0
    _input_kind: str = "polars"
    _design: object = None
    _missing_report: MissingReport | None = None

    # ------------------------------------------------------------------ state

    @property
    def k(self) -> float | tuple[float, ...]:
        """The poverty cutoff, or the tuple of cutoffs when several were asked."""

        return self._cutoffs[0] if len(self._cutoffs) == 1 else self._cutoffs

    @property
    def population(self) -> float:
        """Weighted population of the estimated domain."""

        return float(self._national_row("M0")["population"])

    @property
    def H(self) -> float | None:
        """Incidence of multidimensional poverty."""

        return self._scalar("H")

    @property
    def A(self) -> float | None:
        """Average intensity among the poor."""

        return self._scalar("A")

    @property
    def M0(self) -> float | None:
        """Adjusted headcount ratio, ``H * A``."""

        return self._scalar("M0")

    @property
    def ci_method(self) -> str:
        return self._ci_method

    @property
    def level(self) -> float:
        return self._level

    # ------------------------------------------------------------------ views

    def estimates(self):
        """The full tidy table of estimates and inference."""

        return self._convert(self._estimates.clone())

    def coef(self):
        """Point estimates only."""

        return self._convert(self._select("est"))

    def se(self):
        """Standard errors only."""

        return self._convert(self._select("se"))

    def cv(self):
        """Coefficients of variation only."""

        return self._convert(self._select("cv"))

    def confint(self):
        """Point estimates with their confidence bounds."""

        return self._convert(self._select("est", "lci", "uci", "df"))

    def degf(self):
        """Degrees of freedom of every design context (PLAN.md §6).

        ``df = psus - strata``, counted on the clusters and strata that contain
        observations of the domain, while the variance itself uses the whole
        design. A ``df`` of zero or less means the variance is not estimable and
        the intervals are missing rather than invented.
        """

        columns = ["psus", "strata", "df"]
        frame = self._estimates.select(*self._identifiers(cutoffs=False), *columns).unique(
            maintain_order=True
        )
        return self._convert(frame)

    def to_frame(self):
        """Compact ``H``/``A``/``M0`` table, one row per cutoff and subgroup."""

        index = [*self._identifiers(), "obs", "population"]
        wide = (
            self._estimates.filter(pl.col("measure").is_in(_AGGREGATE))
            .pivot(on="measure", index=index, values="est")
            .rename({"obs": "observations"})
            .with_columns(pl.lit(self.excluded_observations, dtype=pl.Int64).alias(
                "excluded_observations"
            ))
        )
        ordered = [
            *[name for name in self._identifiers() if name != "k"],
            "k",
            "observations",
            "excluded_observations",
            "population",
            *_AGGREGATE,
        ]
        if "k" not in self._identifiers():
            ordered = [
                pl.lit(self._cutoffs[0], dtype=pl.Float64).alias("k")
                if name == "k"
                else name
                for name in ordered
            ]
        return self._convert(wide.select(ordered))

    def contributions(self):
        """``H_j``, ``CH_j``, ``actb_j`` and ``pctb_j`` by indicator."""

        return self._convert(
            self._wide(
                tuple(_INDICATOR_NAMES), _INDICATOR_NAMES, ("dimension", "indicator", "weight")
            )
        )

    def dimension_contributions(self):
        """Absolute and relative contributions aggregated by dimension."""

        return self._convert(
            self._wide(tuple(_DIMENSION_NAMES), _DIMENSION_NAMES, ("dimension", "weight"))
        )

    def scores(self):
        """Row-level ``c_i``, poverty status and censored score ``c_i(k)``."""

        if self._matrix is None:
            raise ValueError(
                "scores() requires an in-memory result; re-run estimate() without lazy=True/CensusDesign streaming"
            )

        frames = []
        for cutoff in self._cutoffs:
            frame = (
                self._matrix.frame.select(
                    pl.col(SCORE).alias("score"),
                    (pl.col(SCORE) >= cutoff).alias("poor"),
                    pl.col(WEIGHT).alias("population_weight"),
                )
                .with_columns(
                    pl.when(pl.col("poor"))
                    .then(pl.col("score"))
                    .otherwise(0.0)
                    .alias("censored_score")
                )
                .select("score", "poor", "censored_score", "population_weight")
            )
            if len(self._cutoffs) > 1:
                frame = frame.with_columns(
                    pl.lit(cutoff, dtype=pl.Float64).alias("k")
                ).select("k", "score", "poor", "censored_score", "population_weight")
            frames.append(frame)
        return self._convert(pl.concat(frames))

    def decomposition(self):
        """Decomposability audit: ``sum_l phi_l * M0_l`` against ``M0``."""

        return self._convert(self._decomposition.clone())

    def changes(self):
        """Absolute, relative and annualised changes between waves (PLAN.md §14.6a)."""

        if self._changes is None:
            raise ValueError("no time variable was declared")
        return self._convert(self._changes.clone())

    def diagnostics(self):
        """Design decisions taken during estimation, one row each (PLAN.md §14.6b)."""

        if self._diagnostics is None:
            schema = {
                "topic": pl.String,
                "context": pl.String,
                "decision": pl.String,
                "detail": pl.String,
            }
            return self._convert(pl.DataFrame(schema=schema))
        return self._convert(self._diagnostics.clone())

    def missing_report(self) -> MissingReport:
        """Audit report for missing-value policy application (PLAN.md §14.8)."""

        if self._matrix is None:
            if self._missing_report is not None:
                return self._missing_report
            return MissingReport(
                policy="listwise",
                rows_in=self.observations,
                rows_out=self.observations - self.excluded_observations,
                dropped=self.excluded_observations,
                per_indicator=pl.DataFrame() if self._input_kind != "pandas" else pd.DataFrame(),
            )
        report = self._matrix.missing_report
        if self._matrix.input_kind == "pandas":
            return MissingReport(
                policy=report.policy,
                rows_in=report.rows_in,
                rows_out=report.rows_out,
                dropped=report.dropped,
                per_indicator=report.per_indicator.to_pandas(),
            )
        return report

    def domain(self, expression: str | pl.Expr):
        """Re-estimate on a subpopulation without breaking the design.

        ``result.domain("region == 'Abidjan'")`` zero-weights the rows outside
        the domain instead of dropping them, so the strata and clusters seen by
        the variance are unchanged (PLAN.md §6).
        """

        if self._matrix is None:
            raise ValueError(
                "scores() requires an in-memory result; re-run estimate() without lazy=True/CensusDesign streaming"
            )

        from .estimation import _estimate_from_matrix

        return _estimate_from_matrix(
            self._matrix,
            cutoffs=self._cutoffs,
            variables=self._over,
            tvar=self._tvar,
            cot_year=self._cot_year,
            domain=expression,
            ci_method=self._ci_method,
            level=self._level,
            check_decomposability=False,
            overlap=self._overlap,
            panel_id=self._panel_id,
        )

    def vcov(
        self,
        *,
        k: float | None = None,
        over: str | None = None,
        subgroup: str | None = None,
        measures: Sequence[str] | None = None,
    ):
        """Full variance-covariance matrix of one estimation context (PLAN.md §14.7)."""

        from .estimation import _compute_vcov

        return _compute_vcov(
            self._matrix,
            cutoffs=self._cutoffs,
            over_vars=self._over,
            k=k,
            over=over,
            subgroup=subgroup,
            measures=measures,
            convert_fn=self._convert,
            design=self._design,
        )

    def test(
        self,
        a: object,
        b: object = None,
        *,
        measure: str = "M0",
        k: float | None = None,
        dist: str = "F",
    ):
        """Wald test of a contrast between two domains, subgroups or periods (PLAN.md §14.7)."""

        design = self._matrix.design if self._matrix is not None else self._design
        if getattr(design, "variance_path", None) == "census":
            raise ValueError("a census has no sampling variance; a Wald test is not defined")

        from .estimation import _compute_test

        return _compute_test(
            self._matrix,
            cutoffs=self._cutoffs,
            a=a,
            b=b,
            measure=measure,
            k=k,
            dist=dist,
        )

    def summary(self) -> str:
        """Compact, human-readable summary."""

        excluded = (
            f" ({self.excluded_observations} excluded by missing-value policy)"
            if self.excluded_observations
            else ""
        )
        header = [
            f"Alkire-Foster estimates (k={self._format_cutoffs()})",
            f"Observations: {self.observations}{excluded}",
            f"Population weight: {self.population:.6g}",
        ]
        if self._domain is not None:
            header.insert(1, f"Domain: {self._domain[1]}")
        if len(self._cutoffs) == 1 and not self._over:
            interval = self._national_row("M0")
            header.extend(
                (
                    f"H  = {self.H:.6f}",
                    f"A  = {self.A:.6f}",
                    f"M0 = {self.M0:.6f}",
                    f"SE(M0) = {interval['se']:.6f}   "
                    f"{int(self._level * 100)}% CI ({self._ci_method}) "
                    f"[{interval['lci']:.6f} ; {interval['uci']:.6f}]   "
                    f"df = {interval['df']}",
                )
            )
            return "\n".join(header)

        table = self._estimates.filter(pl.col("measure").is_in(_AGGREGATE))
        header.append("")
        header.append(f"{'measure':>8} {'k':>6} {'subgroup':>16} {'est':>10} {'se':>10}")
        for row in table.iter_rows(named=True):
            subgroup = row["subgroup"] or "(all)"
            estimate = "." if row["est"] is None else f"{row['est']:10.6f}"
            header.append(
                f"{row['measure']:>8} {row['k']:6.3f} {subgroup:>16} {estimate} "
                f"{row['se']:10.6f}"
            )
        return "\n".join(header)

    # --------------------------------------------------------------- internals

    def _identifiers(self, *, cutoffs: bool = True) -> list[str]:
        names: list[str] = []
        if cutoffs and len(self._cutoffs) > 1:
            names.append("k")
        if self._over:
            names.extend(("over", "subgroup"))
        return names

    def _select(self, *columns: str) -> pl.DataFrame:
        identity = ["measure", "indicator", "dimension", *self._identifiers()]
        return self._estimates.select(*identity, *columns)

    def _wide(
        self,
        measures: tuple[str, ...],
        names: dict[str, str],
        index_columns: tuple[str, ...],
    ) -> pl.DataFrame:
        index = [*self._identifiers(), *index_columns]
        subset = self._estimates.filter(pl.col("measure").is_in(measures))
        estimates = subset.pivot(on="measure", index=index, values="est").rename(names)
        errors = (
            subset.pivot(on="measure", index=index, values="se")
            .rename({key: f"{value}_se" for key, value in names.items()})
            .drop(index)
        )
        return pl.concat([estimates, errors], how="horizontal")

    def _national_row(self, measure: str) -> dict:
        frame = self._estimates.filter(
            (pl.col("measure") == measure) & pl.col("over").is_null()
        )
        if frame.height == 0:  # pragma: no cover - defensive
            raise ValueError(f"no estimate for {measure!r}")
        return frame.row(0, named=True)

    def _scalar(self, measure: str) -> float | None:
        if len(self._cutoffs) > 1:
            raise ValueError(
                f"{measure} is not a single number when several cutoffs are estimated; "
                "use coef() or estimates()"
            )
        return self._national_row(measure)["est"]

    def _format_cutoffs(self) -> str:
        return ", ".join(f"{value:.6g}" for value in self._cutoffs)

    def _convert(self, frame: pl.DataFrame):
        if self._input_kind == "pandas" or (self._matrix is not None and self._matrix.input_kind == "pandas"):
            return frame.to_pandas()
        return frame
