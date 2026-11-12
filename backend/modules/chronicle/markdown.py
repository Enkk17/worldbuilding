from __future__ import annotations

import html
import re
import uuid
from typing import Any

WIKILINK_PATTERN = re.compile(
    r"\[\[(?P<label>[^\]|\n]+?)(?:\|ww:(?P<entity>[0-9a-fA-F-]{36}))?\]\]"
)
LINK_PATTERN = re.compile(r"\[(?P<label>[^\]]+)\]\((?P<href>[^)\s]+)\)")
INLINE_CODE_PATTERN = re.compile(r"`([^`\n]+)`")
BOLD_PATTERN = re.compile(r"\*\*(.+?)\*\*")
ITALIC_PATTERN = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")
STRIKE_PATTERN = re.compile(r"~~(.+?)~~")

_MARKDOWN_ESCAPE = re.compile(r"([\\`*_\[\]~])")


def empty_document() -> dict[str, Any]:
    return {"type": "doc", "content": []}


def _escape_text(value: str) -> str:
    return _MARKDOWN_ESCAPE.sub(r"\\\1", value)


def _safe_url(value: str) -> str | None:
    lowered = value.strip().lower()
    if lowered.startswith(("http://", "https://", "mailto:")):
        return value.strip()
    return None


def _inline_markdown(nodes: list[dict[str, Any]] | None) -> str:
    if not nodes:
        return ""
    parts: list[str] = []
    for node in nodes:
        node_type = node.get("type")
        if node_type == "hardBreak":
            parts.append("  \n")
            continue
        if node_type == "text":
            text = _escape_text(str(node.get("text", "")))
            marks = node.get("marks") or []
            link_href: str | None = None
            for mark in marks:
                mark_type = mark.get("type")
                if mark_type == "bold":
                    text = f"**{text}**"
                elif mark_type == "italic":
                    text = f"*{text}*"
                elif mark_type == "strike":
                    text = f"~~{text}~~"
                elif mark_type == "code":
                    text = f"`{str(node.get('text', ''))}`"
                elif mark_type == "link":
                    attrs = mark.get("attrs") or {}
                    link_href = _safe_url(str(attrs.get("href", "")))
            if link_href:
                text = f"[{text}]({link_href})"
            parts.append(text)
            continue
        if node_type in {"entityMention", "wikiLink"}:
            attrs = node.get("attrs") or {}
            label = str(attrs.get("label") or attrs.get("title") or "Entity").strip()
            entity_id = attrs.get("entityId") or attrs.get("entity_id")
            if entity_id:
                try:
                    canonical = str(uuid.UUID(str(entity_id)))
                except ValueError:
                    canonical = ""
                if canonical:
                    parts.append(f"[[{label}|ww:{canonical}]]")
                    continue
            parts.append(f"[[{label}]]")
            continue
        if node_type == "image":
            attrs = node.get("attrs") or {}
            src = _safe_url(str(attrs.get("src", "")))
            if src:
                alt = str(attrs.get("alt") or "").replace("]", "")
                parts.append(f"![{alt}]({src})")
            continue
        parts.append(_inline_markdown(node.get("content")))
    return "".join(parts)


def tiptap_to_markdown(document: dict[str, Any]) -> str:
    """Serialise the supported TipTap subset to portable Markdown.

    Unknown block nodes are traversed rather than discarded so exported content
    is never silently lost. The caller validates the node vocabulary before
    persistence.
    """

    def render_block(
        target: list[str], node: dict[str, Any], depth: int = 0
    ) -> None:
        node_type = node.get("type")
        children = node.get("content") or []
        attrs = node.get("attrs") or {}

        if node_type == "paragraph":
            target.append(_inline_markdown(children))
            return
        if node_type == "heading":
            level = attrs.get("level", 1)
            try:
                level = max(1, min(int(level), 6))
            except (TypeError, ValueError):
                level = 1
            target.append(f"{'#' * level} {_inline_markdown(children)}")
            return
        if node_type == "bulletList":
            items = []
            for item in children:
                text = _inline_markdown(
                    [
                        child
                        for child in (item.get("content") or [])
                        if child.get("type") == "paragraph"
                        for child in (child.get("content") or [])
                    ]
                )
                items.append(f"- {text}")
            target.append("\n".join(items))
            return
        if node_type == "orderedList":
            items = []
            for index, item in enumerate(children, start=1):
                text = _inline_markdown(
                    [
                        child
                        for child in (item.get("content") or [])
                        if child.get("type") == "paragraph"
                        for child in (child.get("content") or [])
                    ]
                )
                items.append(f"{index}. {text}")
            target.append("\n".join(items))
            return
        if node_type == "blockquote":
            inner: list[str] = []
            for child in children:
                buffer: list[str] = []
                render_block(buffer, child, depth + 1)
                inner.append("\n".join(buffer))
            quoted = "\n\n".join(inner)
            target.append("\n".join(f"> {line}" for line in quoted.splitlines()))
            return
        if node_type == "codeBlock":
            language = str(attrs.get("language") or "")
            code = "".join(
                str(child.get("text", ""))
                for child in children
                if child.get("type") == "text"
            )
            target.append(f"```{language}\n{code}\n```")
            return
        if node_type == "horizontalRule":
            target.append("---")
            return
        if node_type == "image":
            target.append(_inline_markdown([node]))
            return
        if node_type in {"bulletListItem", "orderedListItem"}:
            return
        for child in children:
            render_block(target, child, depth + 1)

    blocks: list[str] = []
    if document.get("type") == "doc":
        for child in document.get("content") or []:
            render_block(blocks, child)
    else:
        render_block(blocks, document)

    return "\n\n".join(block for block in blocks if block != "").strip() + "\n"


def _parse_inline(text: str) -> list[dict[str, Any]]:
    tokens: list[tuple[int, int, dict[str, Any]]] = []

    for match in WIKILINK_PATTERN.finditer(text):
        entity_id = match.group("entity")
        tokens.append(
            (
                match.start(),
                match.end(),
                {
                    "type": "entityMention" if entity_id else "wikiLink",
                    "attrs": {
                        "label": match.group("label").strip(),
                        "entityId": entity_id,
                    },
                },
            )
        )
    for match in LINK_PATTERN.finditer(text):
        href = _safe_url(match.group("href"))
        if not href:
            continue
        tokens.append(
            (
                match.start(),
                match.end(),
                {
                    "type": "text",
                    "text": match.group("label"),
                    "marks": [{"type": "link", "attrs": {"href": href}}],
                },
            )
        )
    for match in INLINE_CODE_PATTERN.finditer(text):
        tokens.append(
            (
                match.start(),
                match.end(),
                {
                    "type": "text",
                    "text": match.group(1),
                    "marks": [{"type": "code"}],
                },
            )
        )

    tokens.sort(key=lambda token: (token[0], -(token[1] - token[0])))
    filtered: list[tuple[int, int, dict[str, Any]]] = []
    cursor = 0
    for token in tokens:
        if token[0] < cursor:
            continue
        filtered.append(token)
        cursor = token[1]

    nodes: list[dict[str, Any]] = []
    position = 0

    def append_text(value: str) -> None:
        if not value:
            return
        nodes.append({"type": "text", "text": value})

    for start, end, node in filtered:
        if start > position:
            append_text(text[position:start])
        nodes.append(node)
        position = end
    if position < len(text):
        append_text(text[position:])

    # Apply simple emphasis marks to plain-text nodes, never to links/code/wiki
    # nodes. Emphasis inside WikiLink labels is intentionally not interpreted.
    emphasised: list[dict[str, Any]] = []
    for node in nodes:
        if node.get("type") != "text" or node.get("marks"):
            emphasised.append(node)
            continue
        remaining = node["text"]
        pattern = re.compile(
            r"\*\*(?P<bold>.+?)\*\*|(?<!\*)\*(?P<italic>[^*\n]+)\*(?!\*)|~~(?P<strike>.+?)~~"
        )
        cursor = 0
        for match in pattern.finditer(remaining):
            if match.start() > cursor:
                emphasised.append(
                    {"type": "text", "text": remaining[cursor : match.start()]}
                )
            if match.group("bold") is not None:
                emphasised.append(
                    {
                        "type": "text",
                        "text": match.group("bold"),
                        "marks": [{"type": "bold"}],
                    }
                )
            elif match.group("italic") is not None:
                emphasised.append(
                    {
                        "type": "text",
                        "text": match.group("italic"),
                        "marks": [{"type": "italic"}],
                    }
                )
            else:
                emphasised.append(
                    {
                        "type": "text",
                        "text": match.group("strike"),
                        "marks": [{"type": "strike"}],
                    }
                )
            cursor = match.end()
        if cursor < len(remaining):
            emphasised.append({"type": "text", "text": remaining[cursor:]})

    # Merge adjacent plain text nodes.
    merged: list[dict[str, Any]] = []
    for node in emphasised:
        if (
            merged
            and node.get("type") == "text"
            and merged[-1].get("type") == "text"
            and not merged[-1].get("marks")
            and not node.get("marks")
        ):
            merged[-1]["text"] += node["text"]
        else:
            merged.append(node)
    return merged


def _parse_paragraph(lines: list[str]) -> dict[str, Any]:
    content: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        content.extend(_parse_inline(line))
        if index < len(lines) - 1:
            content.append({"type": "hardBreak"})
    return {"type": "paragraph", "content": content}


def markdown_to_tiptap(markdown_text: str) -> dict[str, Any]:
    lines = markdown_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks: list[dict[str, Any]] = []
    index = 0

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped:
            index += 1
            continue

        fence = re.match(r"^```(?P<lang>[A-Za-z0-9_+-]*)\s*$", stripped)
        if fence:
            index += 1
            code_lines: list[str] = []
            while index < len(lines) and not lines[index].strip().startswith("```"):
                code_lines.append(lines[index])
                index += 1
            index += 1
            content = (
                [{"type": "text", "text": "\n".join(code_lines)}]
                if code_lines
                else []
            )
            blocks.append(
                {
                    "type": "codeBlock",
                    "attrs": {"language": fence.group("lang") or None},
                    "content": content,
                }
            )
            continue

        heading = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading:
            blocks.append(
                {
                    "type": "heading",
                    "attrs": {"level": len(heading.group(1))},
                    "content": _parse_inline(heading.group(2)),
                }
            )
            index += 1
            continue

        if stripped in {"---", "***", "___"}:
            blocks.append({"type": "horizontalRule"})
            index += 1
            continue

        if stripped.startswith(">"):
            quote_lines: list[str] = []
            while index < len(lines) and lines[index].strip().startswith(">"):
                quote_lines.append(re.sub(r"^>\s?", "", lines[index].strip()))
                index += 1
            inner = markdown_to_tiptap("\n".join(quote_lines)).get("content", [])
            blocks.append({"type": "blockquote", "content": inner})
            continue

        bullet = re.match(r"^[-*+]\s+(.*)$", stripped)
        if bullet:
            items: list[dict[str, Any]] = []
            while index < len(lines):
                current = lines[index].strip()
                match = re.match(r"^[-*+]\s+(.*)$", current)
                if not match:
                    break
                items.append(
                    {
                        "type": "listItem",
                        "content": [_parse_paragraph([match.group(1)])],
                    }
                )
                index += 1
            blocks.append({"type": "bulletList", "content": items})
            continue

        ordered = re.match(r"^\d+[.)]\s+(.*)$", stripped)
        if ordered:
            items = []
            while index < len(lines):
                current = lines[index].strip()
                match = re.match(r"^\d+[.)]\s+(.*)$", current)
                if not match:
                    break
                items.append(
                    {
                        "type": "listItem",
                        "content": [_parse_paragraph([match.group(1)])],
                    }
                )
                index += 1
            blocks.append(
                {
                    "type": "orderedList",
                    "attrs": {"start": 1},
                    "content": items,
                }
            )
            continue

        image = re.match(r"^!\[(?P<alt>[^\]]*)\]\((?P<src>[^)\s]+)\)$", stripped)
        if image and _safe_url(image.group("src")):
            blocks.append(
                {
                    "type": "image",
                    "attrs": {
                        "src": _safe_url(image.group("src")),
                        "alt": image.group("alt"),
                        "title": None,
                    },
                }
            )
            index += 1
            continue

        paragraph_lines: list[str] = []
        while index < len(lines):
            candidate = lines[index]
            candidate_stripped = candidate.strip()
            if not candidate_stripped:
                break
            if (
                candidate_stripped.startswith(("#", "```", ">"))
                or candidate_stripped in {"---", "***", "___"}
                or re.match(r"^[-*+]\s+", candidate_stripped)
                or re.match(r"^\d+[.)]\s+", candidate_stripped)
            ):
                break
            paragraph_lines.append(candidate.rstrip())
            index += 1
        if paragraph_lines:
            blocks.append(_parse_paragraph(paragraph_lines))

    return {"type": "doc", "content": blocks}


def markdown_preview(markdown_text: str, limit: int = 280) -> str:
    plain = WIKILINK_PATTERN.sub(lambda match: match.group("label"), markdown_text)
    plain = LINK_PATTERN.sub(lambda match: match.group("label"), plain)
    plain = re.sub(r"[#>*_`~\-]+", " ", plain)
    plain = re.sub(r"\s+", " ", plain).strip()
    if len(plain) <= limit:
        return plain
    return plain[: limit - 1].rstrip() + "…"


def escape_html(value: str) -> str:
    return html.escape(value, quote=True)
