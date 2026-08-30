"""Hadamard matrix construction using Sylvester's method (PLAN.md §14.5b)."""

from __future__ import annotations

import polars as pl


def sylvester(order: int) -> pl.DataFrame:
    """Hadamard matrix of order 2**k, entries +1/-1, first row and column all +1."""
    if not isinstance(order, int) or order < 1 or (order & (order - 1)) != 0:
        raise ValueError(f"order must be a power of 2 (2**k); got {order!r}")

    mat = [[1]]
    current = 1
    while current < order:
        top = [row + row for row in mat]
        bottom = [row + [-x for x in row] for row in mat]
        mat = top + bottom
        current *= 2

    return pl.DataFrame(mat)
