"""
Unit tests for serialise_config utility (Phase A foundation).
"""

from __future__ import annotations

import pytest

from interactly._utils._serialise import serialise_config


class TestSerialiseConfigWithPlainDicts:
    """serialise_config should return plain values unchanged."""

    def test_returns_dict_unchanged(self):
        data = {"key": "value", "nested": {"a": 1}}
        assert serialise_config(data) is data

    def test_returns_none_unchanged(self):
        assert serialise_config(None) is None

    def test_returns_string_unchanged(self):
        assert serialise_config("hello") == "hello"

    def test_returns_int_unchanged(self):
        assert serialise_config(42) == 42

    def test_returns_list_unchanged(self):
        lst = [1, 2, 3]
        assert serialise_config(lst) is lst

    def test_returns_empty_dict_unchanged(self):
        data: dict = {}
        assert serialise_config(data) is data


class TestSerialiseConfigWithPydanticModels:
    """serialise_config should call model_dump(mode='json') on Pydantic BaseModel instances."""

    def test_serialises_pydantic_model(self):
        try:
            from pydantic import BaseModel

            class _MyModel(BaseModel):
                name: str
                count: int

            obj = _MyModel(name="test", count=5)
            result = serialise_config(obj)
            assert result == {"name": "test", "count": 5}
            assert isinstance(result, dict)
        except ImportError:
            pytest.skip("pydantic not installed")

    def test_serialised_result_is_json_serialisable(self):
        """model_dump(mode='json') must produce JSON-safe types."""
        import json

        try:
            from datetime import datetime
            from pydantic import BaseModel

            class _Timed(BaseModel):
                ts: datetime

            obj = _Timed(ts=datetime(2024, 1, 15, 12, 0, 0))
            result = serialise_config(obj)
            # mode="json" should convert datetime to ISO string
            serialised = json.dumps(result)  # must not raise
            assert "2024-01-15" in serialised
        except ImportError:
            pytest.skip("pydantic not installed")

    def test_nested_pydantic_model(self):
        try:
            from pydantic import BaseModel

            class _Inner(BaseModel):
                x: int

            class _Outer(BaseModel):
                inner: _Inner

            obj = _Outer(inner=_Inner(x=99))
            result = serialise_config(obj)
            assert result == {"inner": {"x": 99}}
        except ImportError:
            pytest.skip("pydantic not installed")


class TestSerialiseConfigExcludeUnset:
    """exclude_unset=True should send only fields the caller explicitly set."""

    def test_exclude_unset_drops_defaulted_fields(self):
        try:
            from typing import Optional
            from uuid import uuid4

            from pydantic import BaseModel, Field
        except ImportError:
            pytest.skip("pydantic not installed")

        class _NodeLike(BaseModel):
            # Mirrors a config with a default_factory logical_id + optional name.
            logical_id: str = Field(default_factory=lambda: "node_" + str(uuid4()))
            name: Optional[str] = None
            prompt: Optional[str] = None

        obj = _NodeLike(prompt="hello")

        # Full dump (default): includes the generated logical_id and name=None.
        full = serialise_config(obj)
        assert "logical_id" in full
        assert "name" in full

        # Partial dump: only the field the caller set.
        partial = serialise_config(obj, exclude_unset=True)
        assert partial == {"prompt": "hello"}
        assert "logical_id" not in partial
        assert "name" not in partial

    def test_exclude_unset_ignored_for_plain_dict(self):
        # Dicts pass through unchanged regardless of exclude_unset.
        data = {"prompt": "hi"}
        assert serialise_config(data, exclude_unset=True) is data
