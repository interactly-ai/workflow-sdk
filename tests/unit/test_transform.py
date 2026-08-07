"""
Unit tests for the transform utilities (_strip_not_given, build_body).
"""

from __future__ import annotations

from interactly._utils._transform import build_body, strip_not_given
from interactly._utils._typing import NOT_GIVEN


class TestStripNotGiven:
    def test_removes_not_given_values(self):
        # Arrange
        params = {"name": "Test", "description": NOT_GIVEN}
        # Act
        result = strip_not_given(params)
        # Assert
        assert result == {"name": "Test"}
        assert "description" not in result

    def test_keeps_none_values(self):
        # None is a legitimate value to send (explicit null in JSON).
        params = {"name": "Test", "description": None}
        result = strip_not_given(params)
        assert result == {"name": "Test", "description": None}

    def test_nested_dict_is_traversed(self):
        params = {"outer": {"inner": NOT_GIVEN, "value": 42}}
        result = strip_not_given(params)
        assert result == {"outer": {"value": 42}}

    def test_all_not_given_returns_empty_dict(self):
        result = strip_not_given({"a": NOT_GIVEN, "b": NOT_GIVEN})
        assert result == {}

    def test_empty_input_returns_empty(self):
        assert strip_not_given({}) == {}

    def test_non_dict_values_pass_through(self):
        params = {"items": [1, 2, 3], "flag": True}
        assert strip_not_given(params) == params


class TestBuildBody:
    def test_returns_none_for_none_input(self):
        assert build_body(None) is None

    def test_returns_none_for_all_not_given(self):
        # After stripping, the body is empty → return None.
        assert build_body({"field": NOT_GIVEN}) is None

    def test_returns_cleaned_dict(self):
        result = build_body({"name": "Test", "extra": NOT_GIVEN})
        assert result == {"name": "Test"}
