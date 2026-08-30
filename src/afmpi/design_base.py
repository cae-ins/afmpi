"""Base class for sampling design specifications (PLAN.md §14.5a)."""

from __future__ import annotations

import abc
from typing import ClassVar


class Design(abc.ABC):
    """What every design family must expose, whatever its variance path."""

    variance_path: ClassVar[str]

    @property
    @abc.abstractmethod
    def required_columns(self) -> tuple[str, ...]:
        """Numeric columns multiplied together to form the population weight."""

    @property
    @abc.abstractmethod
    def design_columns(self) -> tuple[str, ...]:
        """Columns identifying the sampling structure or replicate weights."""
