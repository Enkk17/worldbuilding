"""Bidirectional conversion between TipTap JSON and Yjs XML fragments.

The wire format is the one produced by ``y-prosemirror`` (re-exported by
``@tiptap/y-tiptap``): block and inline nodes are ``Y.XmlElement`` instances
whose tag is the TipTap node name, while text runs are ``Y.XmlText`` instances
whose formatting attributes are keyed by mark name.  Overlapping marks of the
same type use a ``markName--hash`` key; the hash is not part of the TipTap
schema, so it is stripped when materialising JSON.

Keeping this translation in one module is important: it is the bridge between
the op-based collaborative state and the canonical JSON consumed by revision
history, Markdown export, search and the REST API.
"""

from __future__ import annotations

import math
from typing import Any

from pycrdt import Doc, XmlElement, XmlFragment, XmlText

COLLABORATION_FIELD = "content"


class YDocConversionError(ValueError):
    """Raised when a Yjs fragment cannot be represented as TipTap JSON."""


def get_fragment(document: Doc) -> XmlFragment:
    return document.get(COLLABORATION_FIELD, type=XmlFragment)


def _clean_attributes(attrs: dict[str, Any] | None) -> dict[str, Any]:
    if not attrs:
        return {}
    cleaned: dict[str, Any] = {}
    for key, value in attrs.items():
        if value is None:
            continue
        if isinstance(value, dict):
            cleaned[key] = _clean_attributes(value)
        elif isinstance(value, list):
            cleaned[key] = [
                _clean_attributes(item)
                if isinstance(item, dict)
                else _normalise_number(item)
                for item in value
            ]
        else:
            cleaned[key] = _normalise_number(value)
    return cleaned


def _normalise_number(value: Any) -> Any:
    # Yjs stores JavaScript numbers as IEEE-754 doubles; JSON schema fields
    # such as heading levels and list starts are integers.
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return int(value)
    return value


def _append_tiptap_node(children: Any, node: dict[str, Any]) -> None:
    node_type = node.get("type")
    if not isinstance(node_type, str) or not node_type:
        raise YDocConversionError("TipTap nodes require a type.")
    if node_type == "text":
        return

    element = XmlElement(
        node_type, _clean_attributes(node.get("attrs") or {})
    )
    children.append(element)

    for child in node.get("content") or []:
        if not isinstance(child, dict):
            raise YDocConversionError("TipTap node content must contain objects.")
        if child.get("type") == "text":
            text = child.get("text")
            if not isinstance(text, str):
                raise YDocConversionError("Text nodes require a string value.")
            if not text:
                continue
            text_node = XmlText()
            element.children.append(text_node)
            marks: dict[str, Any] = {}
            for mark in child.get("marks") or []:
                mark_type = mark.get("type")
                if not isinstance(mark_type, str) or not mark_type:
                    raise YDocConversionError("Marks require a type.")
                marks[mark_type] = _clean_attributes(mark.get("attrs") or {})
            if marks:
                text_node.insert(0, text, attrs=marks)
            else:
                text_node.insert(0, text)
        else:
            _append_tiptap_node(element.children, child)


def tiptap_to_ydoc(content: dict[str, Any] | None) -> Doc:
    """Build a fresh Y.Doc whose ``content`` fragment mirrors ``content``."""

    document = Doc()
    fragment = get_fragment(document)
    root = content or {}
    for node in root.get("content") or []:
        if isinstance(node, dict):
            _append_tiptap_node(fragment.children, node)
    return document


def _mark_attrs(value: Any) -> dict[str, Any]:
    if value is None or value is True:
        return {}
    if not isinstance(value, dict):
        raise YDocConversionError("Yjs mark attributes must be objects.")
    return _clean_attributes(value)


def _serialise_item(item: Any) -> list[dict[str, Any]]:
    if isinstance(item, XmlText):
        nodes: list[dict[str, Any]] = []
        for value, attributes in item.diff():
            if not isinstance(value, str):
                raise YDocConversionError(
                    "Embedded content is not supported by the Chronicle schema."
                )
            if not value:
                continue
            node: dict[str, Any] = {"type": "text", "text": value}
            marks: list[dict[str, Any]] = []
            for raw_name, raw_attrs in (attributes or {}).items():
                mark_type = str(raw_name).split("--", 1)[0]
                mark: dict[str, Any] = {"type": mark_type}
                attrs = _mark_attrs(raw_attrs)
                if attrs:
                    mark["attrs"] = attrs
                marks.append(mark)
            if marks:
                node["marks"] = marks
            nodes.append(node)
        return nodes

    if isinstance(item, XmlElement):
        node = {"type": item.tag}  # type: ignore[dict-item]
        attrs = _clean_attributes(dict(item.attributes))
        if attrs:
            node["attrs"] = attrs  # type: ignore[assignment]
        children: list[dict[str, Any]] = []
        for child in item.children:
            children.extend(_serialise_item(child))
        if children:
            node["content"] = children  # type: ignore[assignment]
        return [node]

    raise YDocConversionError(
        f"Unsupported Yjs item type: {type(item).__name__}"
    )


def ydoc_to_tiptap(
    document: Doc, *, fragment: XmlFragment | None = None
) -> dict[str, Any]:
    """Materialise the current collaborative state as TipTap JSON."""

    source = fragment if fragment is not None else get_fragment(document)
    content: list[dict[str, Any]] = []
    for item in source.children:
        content.extend(_serialise_item(item))
    return {"type": "doc", "content": content}


def snapshot_is_consistent(document: Doc, snapshot: bytes) -> bool:
    """Verify a snapshot reproduces the room state vector before pruning logs."""

    probe = Doc()
    probe.apply_update(snapshot)
    return probe.get_state() == document.get_state()
