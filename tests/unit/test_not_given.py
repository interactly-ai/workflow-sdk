"""
Unit tests for the NOT_GIVEN sentinel.
"""

from __future__ import annotations

from interactly._utils._typing import NOT_GIVEN, NotGiven, is_given


class TestNotGiven:
    def test_not_given_is_falsy(self):
        # Arrange / Act / Assert
        assert not NOT_GIVEN

    def test_not_given_is_singleton(self):
        # Two constructions return the exact same instance.
        assert NotGiven() is NOT_GIVEN

    def test_is_given_returns_false_for_not_given(self):
        assert is_given(NOT_GIVEN) is False

    def test_is_given_returns_true_for_none(self):
        # None is a real value; it's not NOT_GIVEN.
        assert is_given(None) is True

    def test_is_given_returns_true_for_string(self):
        assert is_given("hello") is True

    def test_is_given_returns_true_for_zero(self):
        assert is_given(0) is True

    def test_repr_is_readable(self):
        assert repr(NOT_GIVEN) == "NOT_GIVEN"
