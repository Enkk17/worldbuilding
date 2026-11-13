"""Portable export bundle format helpers (M8).

A bundle is a ZIP archive holding a manifest, canonical JSON records, and
Obsidian-compatible Markdown. Archives are untrusted input, so reading rejects
path traversal, symlinks, duplicate entries, and zip bombs before any content is
parsed.
"""

from __future__ import annotations

import hashlib
import io
import posixpath
import stat
import zipfile
from typing import Any

import yaml

from backend.core.errors import ApiError

FORMAT_NAME = "worldweave-export"
SCHEMA_VERSION = 1
MANIFEST_NAME = "manifest.json"
UNIVERSE_NAME = "universe.json"
CHECKSUMS_NAME = "checksums.sha256"

MAX_ARCHIVE_ENTRIES = 5_000
MAX_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def render_frontmatter(metadata: dict[str, Any], body: str) -> str:
    frontmatter = yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True).strip()
    return f"---\n{frontmatter}\n---\n\n{body.strip()}\n"


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split a Markdown file into YAML frontmatter metadata and body text."""

    if not text.startswith("---"):
        return {}, text
    lines = text.splitlines()
    closing = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            closing = index
            break
    if closing is None:
        return {}, text
    raw_metadata = "\n".join(lines[1:closing])
    try:
        metadata = yaml.safe_load(raw_metadata) or {}
    except yaml.YAMLError as exc:
        raise ApiError(
            422, "invalid_frontmatter", "A Markdown file has unreadable frontmatter."
        ) from exc
    if not isinstance(metadata, dict):
        raise ApiError(
            422, "invalid_frontmatter", "Markdown frontmatter must be a mapping."
        )
    body = "\n".join(lines[closing + 1 :]).lstrip("\n")
    return metadata, body


def render_checksums(entries: dict[str, bytes]) -> str:
    lines = [f"{sha256_hex(payload)}  {name}" for name, payload in sorted(entries.items())]
    return "\n".join(lines) + "\n"


def parse_checksums(text: str) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            raise ApiError(422, "invalid_checksums", "The checksum index is malformed.")
        digest, name = parts[0].strip().lower(), parts[1].strip()
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ApiError(422, "invalid_checksums", "The checksum index is malformed.")
        checksums[name] = digest
    return checksums


def open_archive(payload: bytes, *, max_bytes: int) -> zipfile.ZipFile:
    """Open an untrusted ZIP archive after validating its structure."""

    if not payload:
        raise ApiError(422, "empty_archive", "The import archive is empty.")
    if len(payload) > max_bytes:
        raise ApiError(413, "archive_too_large", "The import archive exceeds the configured limit.")
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as exc:
        raise ApiError(422, "invalid_archive", "The import archive is not a valid ZIP file.") from exc

    infos = archive.infolist()
    if len(infos) > MAX_ARCHIVE_ENTRIES:
        raise ApiError(422, "archive_too_many_entries", "The import archive contains too many entries.")

    seen: set[str] = set()
    total_uncompressed = 0
    for info in infos:
        name = info.filename
        if name in seen:
            raise ApiError(422, "archive_duplicate_entry", "The import archive contains duplicate entries.")
        seen.add(name)
        normalized = posixpath.normpath(name)
        if (
            name.startswith("/")
            or name.startswith("\\")
            or normalized.startswith("../")
            or normalized == ".."
            or ".." in normalized.split("/")
            or ":" in name.split("/")[0]
        ):
            raise ApiError(422, "archive_unsafe_path", "The import archive contains an unsafe path.")
        if name.endswith("/"):
            continue
        if stat.S_ISLNK(info.external_attr >> 16):
            raise ApiError(422, "archive_symlink_rejected", "The import archive contains a symbolic link.")
        total_uncompressed += info.file_size
        if total_uncompressed > MAX_UNCOMPRESSED_BYTES:
            raise ApiError(422, "archive_too_large", "The import archive expands beyond the supported size.")
        if info.compress_size > 0 and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
            raise ApiError(422, "archive_suspicious_compression", "The import archive has an unsafe compression ratio.")
    return archive


def read_member(archive: zipfile.ZipFile, name: str, *, required: bool = True) -> bytes | None:
    try:
        info = archive.getinfo(name)
    except KeyError:
        if required:
            raise ApiError(422, "archive_missing_member", f"The archive is missing required member '{name}'.")
        return None
    if info.file_size > MAX_UNCOMPRESSED_BYTES:
        raise ApiError(422, "archive_too_large", "An archive member exceeds the supported size.")
    with archive.open(name) as handle:
        return handle.read()


def list_entries(archive: zipfile.ZipFile) -> list[str]:
    return [info.filename for info in archive.infolist() if not info.filename.endswith("/")]
