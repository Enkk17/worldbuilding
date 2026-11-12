from __future__ import annotations

import uuid
from datetime import date
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.errors import ApiError
from backend.core.models import Entity, EntityType

SUPPORTED_FIELD_TYPES = frozenset(
    {
        "text",
        "long_text",
        "number",
        "boolean",
        "date",
        "enum",
        "multi_enum",
        "url",
        "entity_reference",
    }
)

_ALLOWED_DEFINITION_KEYS = frozenset(
    {
        "key",
        "label",
        "type",
        "required",
        "options",
        "default_value",
        "target_entity_type_key",
    }
)


def _validation_error(fields: list[dict[str, Any]], message: str = "Custom field validation failed.") -> ApiError:
    return ApiError(422, "validation_error", message, details={"fields": fields})


def normalize_custom_field_schema(raw: Any) -> dict[str, dict[str, Any]]:
    """Validate and canonicalise an entity-type custom field schema.

    Accepts the canonical mapping ``{field_key: definition}`` and the
    convenience form ``{"fields": [definition, ...]}``. Unknown definition
    attributes are rejected so schemas remain portable and safe to render.
    """

    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise _validation_error(
            [{"field": "schema_json", "code": "object_required"}],
            "The custom field schema must be an object.",
        )

    definitions: list[dict[str, Any]] = []
    if "fields" in raw:
        raw_fields = raw["fields"]
        if not isinstance(raw_fields, list):
            raise _validation_error(
                [{"field": "schema_json.fields", "code": "array_required"}]
            )
        for index, definition in enumerate(raw_fields):
            if not isinstance(definition, dict):
                raise _validation_error(
                    [{"field": f"schema_json.fields.{index}", "code": "object_required"}]
                )
            definitions.append(dict(definition))
    else:
        for key, definition in raw.items():
            if not isinstance(definition, dict):
                raise _validation_error(
                    [{"field": f"schema_json.{key}", "code": "object_required"}]
                )
            candidate = dict(definition)
            candidate.setdefault("key", key)
            definitions.append(candidate)

    normalized: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, Any]] = []

    for index, definition in enumerate(definitions):
        path = f"schema_json.fields.{index}"
        unknown = set(definition) - _ALLOWED_DEFINITION_KEYS
        if unknown:
            errors.append(
                {
                    "field": path,
                    "code": "unknown_attributes",
                    "attributes": sorted(unknown),
                }
            )
            continue

        key = definition.get("key")
        if not isinstance(key, str) or not key.strip():
            errors.append({"field": f"{path}.key", "code": "required"})
            continue
        key = key.strip()
        if key in normalized:
            errors.append({"field": f"{path}.key", "code": "duplicate"})
            continue

        field_type = definition.get("type")
        if field_type not in SUPPORTED_FIELD_TYPES:
            errors.append(
                {
                    "field": f"{path}.type",
                    "code": "unsupported_type",
                    "allowed": sorted(SUPPORTED_FIELD_TYPES),
                }
            )
            continue

        label = definition.get("label") or key.replace("_", " ").title()
        if not isinstance(label, str) or not label.strip() or len(label.strip()) > 80:
            errors.append({"field": f"{path}.label", "code": "invalid"})
            continue

        required = definition.get("required", False)
        if not isinstance(required, bool):
            errors.append({"field": f"{path}.required", "code": "boolean_required"})
            continue

        options = definition.get("options", [])
        if not isinstance(options, list) or any(
            not isinstance(option, str) or not option.strip() for option in options
        ):
            errors.append({"field": f"{path}.options", "code": "string_array_required"})
            continue
        options = [option.strip() for option in options]
        if len(set(options)) != len(options):
            errors.append({"field": f"{path}.options", "code": "duplicate"})
            continue

        if field_type in {"enum", "multi_enum"} and not options:
            errors.append({"field": f"{path}.options", "code": "options_required"})
            continue
        if field_type not in {"enum", "multi_enum"} and options:
            errors.append({"field": f"{path}.options", "code": "options_not_allowed"})
            continue

        target_entity_type_key = definition.get("target_entity_type_key")
        if target_entity_type_key is not None and (
            not isinstance(target_entity_type_key, str) or not target_entity_type_key.strip()
        ):
            errors.append(
                {"field": f"{path}.target_entity_type_key", "code": "invalid"}
            )
            continue
        if field_type != "entity_reference" and target_entity_type_key:
            errors.append(
                {
                    "field": f"{path}.target_entity_type_key",
                    "code": "not_allowed",
                }
            )
            continue

        normalized[key] = {
            "key": key,
            "label": label.strip(),
            "type": field_type,
            "required": required,
            "options": options,
            "default_value": definition.get("default_value"),
            "target_entity_type_key": (
                target_entity_type_key.strip() if target_entity_type_key else None
            ),
        }

    if errors:
        raise _validation_error(errors)

    return normalized


def validate_entity_reference_types(
    db: Session,
    universe_id: uuid.UUID,
    schema: dict[str, dict[str, Any]],
    extra_keys: set[str] | None = None,
) -> None:
    keys = {
        definition["target_entity_type_key"]
        for definition in schema.values()
        if definition.get("target_entity_type_key")
    }
    if not keys:
        return
    existing = set(
        db.scalars(
            select(EntityType.key).where(
                EntityType.universe_id == universe_id,
                EntityType.key.in_(keys),
            )
        ).all()
    ) | (extra_keys or set())
    missing = sorted(keys - existing)
    if missing:
        raise _validation_error(
            [
                {
                    "field": "schema_json.target_entity_type_key",
                    "code": "entity_type_not_found",
                    "keys": missing,
                }
            ],
            "The custom field schema references unknown entity types.",
        )


def _single_error(field: str, code: str, **extra: Any) -> ApiError:
    return _validation_error([{"field": field, "code": code, **extra}])


def _validate_value(
    db: Session | None,
    universe_id: uuid.UUID | None,
    key: str,
    definition: dict[str, Any],
    value: Any,
) -> Any:
    field = f"custom_fields.{key}"
    field_type = definition["type"]

    if field_type in {"text", "long_text"}:
        if not isinstance(value, str):
            raise _single_error(field, "string_required")
        limit = 2000 if field_type == "text" else 50000
        if len(value) > limit:
            raise _single_error(field, "max_length", max_length=limit)
        return value.strip() if field_type == "text" else value

    if field_type == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise _single_error(field, "number_required")
        return value

    if field_type == "boolean":
        if not isinstance(value, bool):
            raise _single_error(field, "boolean_required")
        return value

    if field_type == "date":
        if not isinstance(value, str):
            raise _single_error(field, "date_required")
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise _single_error(field, "date_required") from exc
        return value

    if field_type == "enum":
        if not isinstance(value, str) or value not in definition["options"]:
            raise _single_error(field, "invalid_option", options=definition["options"])
        return value

    if field_type == "multi_enum":
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise _single_error(field, "string_array_required")
        invalid = [item for item in value if item not in definition["options"]]
        if invalid:
            raise _single_error(
                field,
                "invalid_option",
                options=definition["options"],
                invalid=invalid,
            )
        return list(dict.fromkeys(value))

    if field_type == "url":
        if not isinstance(value, str) or len(value) > 2000:
            raise _single_error(field, "url_required")
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise _single_error(field, "url_required")
        return value

    if field_type == "entity_reference":
        if not isinstance(value, str):
            raise _single_error(field, "entity_id_required")
        try:
            entity_id = uuid.UUID(value)
        except ValueError as exc:
            raise _single_error(field, "entity_id_required") from exc
        if db is None or universe_id is None:
            return value
        entity = db.scalar(
            select(Entity)
            .join(EntityType, EntityType.id == Entity.entity_type_id)
            .where(
                Entity.id == entity_id,
                Entity.universe_id == universe_id,
                Entity.deleted_at.is_(None),
            )
        )
        if entity is None:
            raise _single_error(field, "entity_not_found")
        target_key = definition.get("target_entity_type_key")
        if target_key:
            actual_key = db.scalar(
                select(EntityType.key).where(EntityType.id == entity.entity_type_id)
            )
            if actual_key != target_key:
                raise _single_error(
                    field,
                    "entity_type_mismatch",
                    expected=target_key,
                    actual=actual_key,
                )
        return value

    raise _single_error(field, "unsupported_type")


def validate_custom_field_values(
    db: Session,
    universe_id: uuid.UUID,
    schema: dict[str, dict[str, Any]],
    values: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(values, dict):
        raise _single_error("custom_fields", "object_required")
    if not schema:
        return values

    errors: list[dict[str, Any]] = []
    unknown = sorted(set(values) - set(schema))
    for key in unknown:
        errors.append({"field": f"custom_fields.{key}", "code": "unknown_field"})

    cleaned: dict[str, Any] = {}
    for key, definition in schema.items():
        if key not in values or values[key] is None:
            default_value = definition.get("default_value")
            if default_value is not None:
                try:
                    cleaned[key] = _validate_value(
                        db, universe_id, key, definition, default_value
                    )
                except ApiError as exc:
                    errors.extend(exc.details.get("fields", []))
            elif definition.get("required"):
                errors.append({"field": f"custom_fields.{key}", "code": "required"})
            continue
        try:
            cleaned[key] = _validate_value(
                db, universe_id, key, definition, values[key]
            )
        except ApiError as exc:
            errors.extend(exc.details.get("fields", []))

    if errors:
        raise _validation_error(errors)
    return cleaned
