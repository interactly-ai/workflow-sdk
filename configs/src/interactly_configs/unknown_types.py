"""
Fallbacks for a config whose ``type`` this package does not know yet.

A client lags the server: a workflow can hold an LLM provider or a tool type added after this package was released.
Validated strictly, such a config fails, and so does the node holding it, which then degrades to
``UnknownNodeConfig`` with every typed field lost. Attached to a discriminated union, these keep the damage to the
config itself: an unknown ``type`` is validated as the fallback class instead, keeps every field it arrived with,
and is written back with exactly those fields, so a fetch, edit and upload round trip loses nothing.

This module has no upstream counterpart. The server always knows its own types; only a client needs this.
"""

from typing import Any, Type

from pydantic import BaseModel, ValidationError, WrapSerializer, WrapValidator


def unknown_type_validator(fallback: Type[BaseModel]) -> WrapValidator:
    """Validate through the union, and validate as ``fallback`` when the only error is an unknown ``type``.

    A known type with an invalid field, or a config with no ``type`` at all, still raises: those are mistakes in the
    config, not a type newer than this package, and turning them into an unknown would hide them.
    """

    def validate(value: Any, handler: Any) -> Any:
        if isinstance(value, fallback):
            return value
        try:
            return handler(value)
        except ValidationError as exc:
            errors = exc.errors()
            only_unknown_type = bool(errors) and all(e["type"] == "union_tag_invalid" and not e["loc"] for e in errors)
            if isinstance(value, dict) and only_unknown_type:
                return fallback.model_validate(value)
            raise

    return WrapValidator(validate)


def unknown_type_serializer(fallback: Type[BaseModel]) -> WrapSerializer:
    """Write a ``fallback`` instance back with exactly the fields it arrived with, and every other value as the union
    would.

    A fallback class may carry defaults of its own (the fields every config of its kind shares); writing those back
    would add fields the server never sent, so only the fields that were set are written. Without this serializer a
    fallback inside the union also serializes, but with a warning that it matched no member.
    """

    # No return annotation, on purpose: pydantic publishes a serializer's return annotation as the field's JSON schema,
    # in place of the union's. Left off, the published schema stays the union's, identical to upstream's.
    def serialize(value, handler, info):  # type: ignore[no-untyped-def]
        if isinstance(value, fallback):
            return value.model_dump(
                mode="json" if info.mode_is_json() else "python",
                by_alias=info.by_alias,
                exclude_unset=True,
                exclude_defaults=info.exclude_defaults,
                exclude_none=info.exclude_none,
            )
        return handler(value)

    return WrapSerializer(serialize)


def fields_that_arrived(model: BaseModel, data: Any) -> Any:
    """``model``'s serialized ``data`` without the fields it was never given.

    For a fallback class's own serializer. A fallback inherits defaults from its base (the fields every config of
    its kind shares), and writing those back would add fields the server never sent, including a ``logical_id``
    minted afresh on every read. Fields that were set, and extra fields, are kept.
    """
    if not isinstance(data, dict):
        return data
    kept = set(model.__pydantic_extra__ or {})
    for name in model.model_fields_set:
        kept.add(name)
        info = type(model).model_fields.get(name)
        if info is not None:
            kept.update(alias for alias in (info.alias, info.serialization_alias) if alias)
    return {key: value for key, value in data.items() if key in kept}
