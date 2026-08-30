"""Definition and weighting of deprivation indicators."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from math import isclose, isfinite
from numbers import Real

_WEIGHT_TOLERANCE = 1e-9
_MISSING_POLICIES = frozenset({"listwise_deletion", "reweighting"})


class Specification:
    """Indicators, dimensions, weights, and missing-value policy.

    ``equal_nested`` gives every dimension the same weight, then divides each
    dimension's weight equally among its indicators. A custom mapping may be
    keyed either by every dimension or by every indicator and must sum to one.
    """

    def __init__(
        self,
        dimensions: Mapping[str, Sequence[str]] | None = None,
        weights: str | Mapping[str, float] = "equal_nested",
        *,
        missing_policy: str = "listwise_deletion",
    ) -> None:
        self._dimensions: dict[str, tuple[str, ...]] = {}
        self._indicator_weights: dict[str, float] = {}
        self._dimension_weights: dict[str, float] = {}
        self._missing_policy = self._validate_missing_policy(missing_policy)
        if dimensions is not None:
            self.set(dimensions=dimensions, weights=weights)

    def set(
        self,
        dimensions: Mapping[str, Sequence[str]],
        weights: str | Mapping[str, float] = "equal_nested",
        *,
        missing_policy: str | None = None,
    ) -> Specification:
        """Set the dimensions and return ``self`` for fluent construction."""

        parsed = self._validate_dimensions(dimensions)
        if missing_policy is not None:
            self._missing_policy = self._validate_missing_policy(missing_policy)
        self._dimensions = parsed
        self.set_weights(weights)
        return self

    def set_weights(self, weights: str | Mapping[str, float]) -> Specification:
        """Set equal-nested, dimension-level, or indicator-level weights."""

        self._require_configured()
        dimensions = tuple(self._dimensions)
        indicators = self.indicators

        if isinstance(weights, str):
            if weights != "equal_nested":
                raise ValueError("weights must be 'equal_nested' or a complete mapping")
            dimension_weights = {name: 1.0 / len(dimensions) for name in dimensions}
            indicator_weights = {
                indicator: dimension_weights[dimension] / len(members)
                for dimension, members in self._dimensions.items()
                for indicator in members
            }
        elif isinstance(weights, Mapping):
            numeric_weights = self._validate_weight_mapping(weights)
            keys = set(numeric_weights)
            if keys == set(dimensions):
                dimension_weights = dict(numeric_weights)
                indicator_weights = {
                    indicator: dimension_weights[dimension] / len(members)
                    for dimension, members in self._dimensions.items()
                    for indicator in members
                }
            elif keys == set(indicators):
                indicator_weights = dict(numeric_weights)
                dimension_weights = {
                    dimension: sum(indicator_weights[item] for item in members)
                    for dimension, members in self._dimensions.items()
                }
            else:
                missing_dimensions = sorted(set(dimensions) - keys)
                missing_indicators = sorted(set(indicators) - keys)
                raise ValueError(
                    "custom weights must contain exactly all dimensions or all indicators; "
                    f"missing dimensions={missing_dimensions}, "
                    f"missing indicators={missing_indicators}"
                )
        else:
            raise TypeError("weights must be 'equal_nested' or a mapping")

        self._dimension_weights = dimension_weights
        self._indicator_weights = indicator_weights
        return self

    @property
    def dimensions(self) -> dict[str, tuple[str, ...]]:
        self._require_configured()
        return dict(self._dimensions)

    @property
    def indicators(self) -> tuple[str, ...]:
        self._require_configured()
        return tuple(item for members in self._dimensions.values() for item in members)

    @property
    def indicator_weights(self) -> dict[str, float]:
        self._require_configured()
        return dict(self._indicator_weights)

    @property
    def dimension_weights(self) -> dict[str, float]:
        self._require_configured()
        return dict(self._dimension_weights)

    @property
    def missing_policy(self) -> str:
        return self._missing_policy

    def dimension_of(self, indicator: str) -> str:
        self._require_configured()
        for dimension, members in self._dimensions.items():
            if indicator in members:
                return dimension
        raise KeyError(indicator)

    def _require_configured(self) -> None:
        if not self._dimensions:
            raise ValueError("Specification is empty; call set() before estimate()")

    @staticmethod
    def _validate_dimensions(
        dimensions: Mapping[str, Sequence[str]],
    ) -> dict[str, tuple[str, ...]]:
        if not isinstance(dimensions, Mapping) or not dimensions:
            raise ValueError("dimensions must be a non-empty mapping")

        parsed: dict[str, tuple[str, ...]] = {}
        seen: set[str] = set()
        for dimension, indicators in dimensions.items():
            if not isinstance(dimension, str) or not dimension.strip():
                raise ValueError("dimension names must be non-empty strings")
            if isinstance(indicators, (str, bytes)) or not isinstance(indicators, Sequence):
                raise TypeError(f"indicators for dimension {dimension!r} must be a sequence")
            members = tuple(indicators)
            if not members:
                raise ValueError(f"dimension {dimension!r} has no indicators")
            if any(not isinstance(item, str) or not item.strip() for item in members):
                raise ValueError("indicator names must be non-empty strings")
            duplicates = seen.intersection(members)
            if duplicates or len(set(members)) != len(members):
                repeated = sorted(duplicates or {x for x in members if members.count(x) > 1})
                raise ValueError(f"indicators may belong to only one dimension: {repeated}")
            seen.update(members)
            parsed[dimension] = members
        return parsed

    @staticmethod
    def _validate_weight_mapping(weights: Mapping[str, float]) -> dict[str, float]:
        parsed: dict[str, float] = {}
        for name, value in weights.items():
            if not isinstance(name, str):
                raise TypeError("weight keys must be strings")
            if isinstance(value, bool) or not isinstance(value, Real):
                raise TypeError(f"weight for {name!r} must be a real number")
            number = float(value)
            if not isfinite(number) or number < 0:
                raise ValueError(f"weight for {name!r} must be finite and non-negative")
            parsed[name] = number
        total = sum(parsed.values())
        if not isclose(total, 1.0, abs_tol=_WEIGHT_TOLERANCE, rel_tol=0.0):
            raise ValueError(f"weights must sum to 1; got {total}")
        return parsed

    @staticmethod
    def _validate_missing_policy(policy: str) -> str:
        if policy not in _MISSING_POLICIES:
            choices = ", ".join(sorted(_MISSING_POLICIES))
            raise ValueError(f"missing_policy must be one of: {choices}")
        return policy
