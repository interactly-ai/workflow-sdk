"""Declaring which config fields hold credentials.

Upstream declares a credential on the field that holds it: ``SecretField`` for a field whose whole value is a
credential, ``SensitiveMapField`` for a free-form map (HTTP headers, a request body, JSON request text) whose
*entries* may be. Each adds a dashboard annotation to the field's ``json_schema_extra``, and the server reads
those annotations to mask the field in the editor, withhold it from the workflow copilot and clear it on export.

The mirror drops dashboard annotations, as it does everywhere, so here both are plain ``pydantic.Field``: they take
the same arguments as upstream's and declare the same field, without the annotation. The server-side readers of the
annotations (``is_secret_field``, ``sensitive_map_kind``, ``is_sensitive_key``) are not vendored: they act on markers
this package does not carry, and only the server masks, withholds or clears.
"""

from enum import Enum
from typing import Any, Optional

from pydantic import Field


class SensitiveMap(str, Enum):
    """How a map's entries are read when looking for credentials in it."""

    HEADERS = "headers"  # HTTP headers: the header name decides, case-insensitively.
    BODY = "body"  # A JSON object, at any depth: the key decides.
    JSON_TEXT = "json_text"  # The same as BODY, but stored as text and parsed to be read.


def SecretField(*args: Any, json_schema_extra: Optional[dict] = None, **kwargs: Any) -> Any:  # noqa: N802
    """``pydantic.Field`` for a field whose value is a credential. Takes the same arguments as ``Field``."""
    return Field(*args, **kwargs)


def SensitiveMapField(  # noqa: N802
    kind: SensitiveMap, *args: Any, json_schema_extra: Optional[dict] = None, **kwargs: Any
) -> Any:
    """``pydantic.Field`` for a free-form map whose entries may be credentials. See ``SensitiveMap``."""
    return Field(*args, **kwargs)
