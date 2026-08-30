"""Tests for Hadamard matrix construction via Sylvester's method (PLAN.md §14.5b)."""

import numpy as np
import pytest
import polars as pl

from afmpi.hadamard import sylvester


@pytest.mark.parametrize("n", [1, 2, 4, 8, 16, 32])
def test_sylvester_orthogonality(n: int) -> None:
    """Test #1: sylvester(n) @ sylvester(n).T == n * I."""
    H = sylvester(n).to_numpy()
    product = H @ H.T
    expected = n * np.eye(n, dtype=int)
    np.testing.assert_array_equal(product, expected)


@pytest.mark.parametrize("n", [1, 2, 4, 8, 16, 32])
def test_sylvester_first_row_and_column_all_ones(n: int) -> None:
    """Test #2: First row and first column all +1."""
    H = sylvester(n).to_numpy()
    np.testing.assert_array_equal(H[0, :], np.ones(n, dtype=int))
    np.testing.assert_array_equal(H[:, 0], np.ones(n, dtype=int))


@pytest.mark.parametrize("invalid_n", [0, 3, 5, 6, 7, 9, 10, -2])
def test_sylvester_invalid_order_raises(invalid_n: int) -> None:
    with pytest.raises(ValueError, match="power of 2"):
        sylvester(invalid_n)
