"""Canonical TipTap document validation and inspection helpers.

The Chronicle stores TipTap JSON as the canonical editor representation.  This
module is the single authority for the *accepted* node vocabulary: anything the
serializer, renderer, collaboration layer, or importer may encounter must be
validated here before persistence.  Keeping the vocabulary bounded prevents
stored XSS through link/image attributes and keeps Markdown export lossless for
every accepted node.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Iterable

MAX_NODES = 50_000
MAX_DEPTH = 32
MAX_TEXT_CHARACTERS = 1_000_000
MAX_SERIALIZED_BYTES = 5 * 1024 * 1024

INLINE_TYPES = frozenset({"text", "hardBreak", "entityMention", "wikiLink"})
LEAF_BLOCK_TYPES = frozenset({"horizontalRule", "image"})
CONTAINER_BLOCK_TYPES = frozenset(
    {
        "paragraph",
        "heading",
        "bulletList",
        "orderedList",
        "blockquote",
        "codeBlock",
    }
)
BLOCK_TYPES = INLINE_TYPES | LEAF_BLOCK_TYPES | CONTAINER_BLOCK_TYPES

ALLOWED_CHILDREN: dict[str, frozenset[str]] = {
    "doc": CONTAINER_BLOCK_TYPES | LEAF_BLOCK_TYPES,
    "paragraph": INLINE_TYPES,
    "heading": INLINE_TYPES,
    "bulletList": frozenset({"listItem"}),
    "orderedList": frozenset({"listItem"}),
    "listItem": frozenset({"paragraph"}),
    "blockquote": CONTAINER_BLOCK_TYPES | LEAF_BLOCK_TYPES,
    "codeBlock": frozenset({"text"}),
    "horizontalRule": frozenset(),
    "image": frozenset(),
    "text": frozenset(),
    "hardBreak": frozenset(),
    "entityMention": frozenset(),
    "wikiLink": frozenset(),
}

ALLOWED_ATTRS: dict[str, frozenset[str]] = {
    "heading": frozenset({"level"}),
    "orderedList": frozenset({"start"}),
    "codeBlock": frozenset({"language"}),
    "image": frozenset({"src", "alt", "title"}),
    "entityMention": frozenset({"entityId", "label"}),
    "wikiLink": frozenset({"label"}),
}

ALLOWED_MARKS: dict[str, frozenset[str]] = {
    "bold": frozenset(),
    "italic": frozenset(),
    "strike": frozenset(),
    "code": frozenset(),
    "link": frozenset({"href"}),
}


@dataclass(slots=True)
class ContentValidationError(Exception):
    code: str
    path: str
    message: str

    def __str__(self) -> str:  # pragma: no cover - diagnostics only
        return f"{self.path}: {self.message}"


@dataclass(slots=True)
class Mention:
    entity_id: uuid.UUID
    label: str
    path: str


def empty_document() -> dict[str, Any]:
    return {"type": "doc", "content": []}


def _fail(code: str, path: str, message: str) -> None:
    raise ContentValidationError(code=code, path=path, message=message)


def _safe_link(value: Any, path: str) -> str:
    if not isinstance(value, str):
        _fail("invalid_link", path, "Link targets must be strings.")
    cleaned = value.strip()
    lowered = cleaned.lower()
    if not cleaned or len(cleaned) > 2000:
        _fail("invalid_link", path, "Link targets must be between 1 and 2000 characters.")
    if lowered.startswith(("javascript:", "data:", "vbscript:", "file:")):
        _fail("unsafe_link", path, "Only http, https, and mailto links are allowed.")
    if "\\" in cleaned or any(ord(char) < 32 for char in cleaned):
        _fail("unsafe_link", path, "Link targets contain forbidden characters.")
    if not lowered.startswith(("http://", "https://", "mailto:")):
        _fail("unsafe_link", path, "Only http, https, and mailto links are allowed.")
    return cleaned


def _safe_image_source(value: Any, path: str) -> str:
    if not isinstance(value, str):
        _fail("invalid_image_source", path, "Image sources must be strings.")
    cleaned = value.strip()
    lowered = cleaned.lower()
    if not cleaned or len(cleaned) > 2000:
        _fail(
            "invalid_image_source",
            path,
            "Image sources must be between 1 and 2000 characters.",
        )
    if lowered.startswith(("javascript:", "data:", "vbscript:", "file:")):
        _fail("unsafe_image_source", path, "Unsafe image source rejected.")
    if cleaned.startswith("/"):
        return cleaned
    if lowered.startswith(("http://", "https://")):
        return cleaned
    _fail(
        "unsafe_image_source",
        path,
        "Image sources must be absolute http(s) URLs or application-relative paths.",
    )


def _normalise_text(value: Any, path: str, *, limit: int, field: str) -> str:
    if not isinstance(value, str):
        _fail(f"invalid_{field}", path, f"{field} must be a string.")
    if len(value) > limit:
        _fail(f"{field}_too_long", path, f"{field} exceeds {limit} characters.")
    return value


def _normalise_marks(marks: Any, path: str) -> list[dict[str, Any]]:
    if marks is None:
        return []
    if not isinstance(marks, list):
        _fail("invalid_marks", path, "Marks must be a list.")
    normalised: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, mark in enumerate(marks):
        mark_path = f"{path}.marks.{index}"
        if not isinstance(mark, dict):
            _fail("invalid_mark", mark_path, "Marks must be objects.")
        mark_type = mark.get("type")
        if not isinstance(mark_type, str) or mark_type not in ALLOWED_MARKS:
            _fail("unsupported_mark", mark_path, f"Unsupported mark '{mark_type}'.")
        if mark_type in seen:
            _fail("duplicate_mark", mark_path, f"Duplicate mark '{mark_type}'.")
        seen.add(mark_type)
        attrs = mark.get("attrs")
        attrs = {} if attrs is None else attrs
        if not isinstance(attrs, dict):
            _fail("invalid_mark_attributes", mark_path, "Mark attributes must be an object.")
        cleaned_attrs: dict[str, Any] = {}
        for key, value in attrs.items():
            if value is None:
                continue
            if key not in ALLOWED_MARKS[mark_type]:
                _fail(
                    "unknown_mark_attribute",
                    f"{mark_path}.attrs.{key}",
                    f"Unsupported attribute '{key}' for mark '{mark_type}'.",
                )
            if mark_type == "link" and key == "href":
                cleaned_attrs["href"] = _safe_link(value, f"{mark_path}.attrs.href")
            else:
                _fail(
                    "unknown_mark_attribute",
                    f"{mark_path}.attrs.{key}",
                    f"Unsupported attribute '{key}' for mark '{mark_type}'.",
                )
        if mark_type == "link" and "href" not in cleaned_attrs:
            _fail("missing_link_target", mark_path, "Link marks require an href.")
        payload: dict[str, Any] = {"type": mark_type}
        if cleaned_attrs:
            payload["attrs"] = cleaned_attrs
        normalised.append(payload)
    return normalised


def _normalise_attrs(
    node_type: str, attrs: Any, path: str
) -> dict[str, Any]:
    if attrs is None:
        attrs = {}
    if not isinstance(attrs, dict):
        _fail("invalid_attributes", path, "Node attributes must be an object.")
    allowed = ALLOWED_ATTRS.get(node_type, frozenset())
    cleaned: dict[str, Any] = {}
    for key, value in attrs.items():
        if value is None:
            continue
        attr_path = f"{path}.attrs.{key}"
        if key not in allowed:
            _fail(
                "unknown_attribute",
                attr_path,
                f"Unsupported attribute '{key}' for node '{node_type}'.",
            )
        if node_type == "heading" and key == "level":
            if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 6:
                _fail("invalid_heading_level", attr_path, "Heading levels must be 1-6.")
            cleaned[key] = value
        elif node_type == "orderedList" and key == "start":
            if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 1_000_000:
                _fail("invalid_list_start", attr_path, "List start must be a positive integer.")
            cleaned[key] = value
        elif node_type == "codeBlock" and key == "language":
            language = _normalise_text(value, attr_path, limit=64, field="language")
            if language and not all(char.isalnum() or char in "_-+" for char in language):
                _fail("invalid_language", attr_path, "Code block languages use alphanumerics, _, - or +.")
            cleaned[key] = language or None
        elif node_type == "image" and key == "src":
            cleaned["src"] = _safe_image_source(value, attr_path)
        elif node_type == "image" and key in {"alt", "title"}:
            cleaned[key] = _normalise_text(value, attr_path, limit=500, field=key)
        elif node_type == "entityMention" and key == "entityId":
            try:
                cleaned["entityId"] = str(uuid.UUID(str(value)))
            except (ValueError, AttributeError, TypeError):
                _fail("invalid_entity_id", attr_path, "Entity mentions require a UUID.")
        elif node_type in {"entityMention", "wikiLink"} and key == "label":
            label = _normalise_text(value, attr_path, limit=200, field="label").strip()
            if not label:
                _fail("invalid_label", attr_path, "Labels cannot be empty.")
            cleaned["label"] = label
        else:
            _fail(
                "unknown_attribute",
                attr_path,
                f"Unsupported attribute '{key}' for node '{node_type}'.",
            )
    if node_type == "image" and not cleaned.get("src"):
        _fail("missing_image_source", path, "Image nodes require a src attribute.")
    if node_type == "entityMention" and not cleaned.get("entityId"):
        _fail("missing_entity_id", path, "Entity mention nodes require an entityId.")
    if node_type in {"entityMention", "wikiLink"} and not cleaned.get("label"):
        _fail("missing_label", path, f"Node '{node_type}' requires a label.")
    return cleaned


def _walk(
    node: Any,
    path: str,
    depth: int,
    state: dict[str, int],
    *,
    parent: str | None,
) -> dict[str, Any]:
    if depth > MAX_DEPTH:
        _fail("max_depth_exceeded", path, f"Document nesting exceeds {MAX_DEPTH} levels.")
    state["nodes"] += 1
    if state["nodes"] > MAX_NODES:
        _fail("too_many_nodes", path, f"Document exceeds {MAX_NODES} nodes.")
    if not isinstance(node, dict):
        _fail("invalid_node", path, "Nodes must be objects.")
    node_type = node.get("type")
    if not isinstance(node_type, str) or not node_type:
        _fail("missing_node_type", path, "Every node requires a type.")
    if node_type not in BLOCK_TYPES and node_type != "doc" and node_type != "listItem":
        _fail("unsupported_node", path, f"Unsupported node type '{node_type}'.")
    if parent is not None and node_type not in ALLOWED_CHILDREN.get(parent, frozenset()):
        _fail(
            "invalid_child_node",
            path,
            f"Node '{node_type}' is not allowed inside '{parent}'.",
        )

    content = node.get("content")
    if content is None:
        content = []
    if not isinstance(content, list):
        _fail("invalid_content", path, "Node content must be a list.")

    allowed_children = ALLOWED_CHILDREN.get(node_type, frozenset())
    if not allowed_children and content:
        _fail("unexpected_content", path, f"Node '{node_type}' cannot have children.")
    if allowed_children and node_type != "doc" and len(content) > 10_000:
        _fail("too_many_children", path, "A node has too many children.")

    normalised_content = [
        _walk(child, f"{path}.content.{index}", depth + 1, state, parent=node_type)
        for index, child in enumerate(content)
    ]

    payload: dict[str, Any] = {"type": node_type}
    attrs = _normalise_attrs(node_type, node.get("attrs"), path)
    if attrs:
        payload["attrs"] = attrs
    if node_type == "text":
        text = _normalise_text(node.get("text", ""), path, limit=100_000, field="text")
        state["characters"] += len(text)
        if state["characters"] > MAX_TEXT_CHARACTERS:
            _fail(
                "too_much_text",
                path,
                f"Document text exceeds {MAX_TEXT_CHARACTERS} characters.",
            )
        payload["text"] = text
        marks = _normalise_marks(node.get("marks"), path)
        if marks:
            payload["marks"] = marks
    elif "text" in node:
        _fail("unexpected_text", path, "Only text nodes may contain text.")
    if normalised_content:
        payload["content"] = normalised_content
    elif node_type == "doc":
        payload["content"] = []
    return payload


def normalize_document_content(value: Any) -> dict[str, Any]:
    """Validate and canonicalise a TipTap document.

    Raises :class:`ContentValidationError` with a stable machine-readable code.
    """

    if value is None:
        return empty_document()
    if not isinstance(value, dict):
        raise ContentValidationError(
            code="invalid_document", path="$", message="Content must be a JSON object."
        )
    if value.get("type") != "doc":
        raise ContentValidationError(
            code="invalid_document", path="$.type", message="Root node must be a 'doc'."
        )
    try:
        serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ContentValidationError(
            code="invalid_document", path="$", message="Content is not JSON serialisable."
        ) from exc
    if len(serialized.encode("utf-8")) > MAX_SERIALIZED_BYTES:
        raise ContentValidationError(
            code="document_too_large",
            path="$",
            message=f"Document exceeds {MAX_SERIALIZED_BYTES} bytes.",
        )
    state = {"nodes": 0, "characters": 0}
    return _walk(value, "$", 0, state, parent=None)


def extract_mentions(document: dict[str, Any]) -> list[Mention]:
    """Return every entity mention occurrence in document order."""

    mentions: list[Mention] = []

    def visit(node: dict[str, Any], path: str) -> None:
        if node.get("type") == "entityMention":
            attrs = node.get("attrs") or {}
            entity_id = attrs.get("entityId")
            if entity_id:
                try:
                    mentions.append(
                        Mention(
                            entity_id=uuid.UUID(str(entity_id)),
                            label=str(attrs.get("label") or "Entity"),
                            path=path,
                        )
                    )
                except (ValueError, TypeError):
                    pass
        for index, child in enumerate(node.get("content") or []):
            if isinstance(child, dict):
                visit(child, f"{path}.content.{index}")

    visit(document, "$")
    return mentions


def _iter_text_nodes(node: dict[str, Any]) -> Iterable[str]:
    node_type = node.get("type")
    if node_type == "text":
        yield str(node.get("text") or "")
    elif node_type in {"entityMention", "wikiLink"}:
        yield str((node.get("attrs") or {}).get("label") or "")
    elif node_type == "hardBreak":
        yield " "
    for child in node.get("content") or []:
        if isinstance(child, dict):
            yield from _iter_text_nodes(child)
    if node_type in CONTAINER_BLOCK_TYPES or node_type in {"doc", "listItem"}:
        yield " "


def content_preview(document: dict[str, Any], limit: int = 280) -> str:
    plain = "".join(_iter_text_nodes(document))
    plain = " ".join(plain.split())
    if len(plain) <= limit:
        return plain
    return plain[: max(0, limit - 1)].rstrip() + "…"
