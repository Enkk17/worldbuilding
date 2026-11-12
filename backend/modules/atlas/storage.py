from __future__ import annotations

import hashlib
import os
import struct
import unicodedata
import uuid
from pathlib import Path

from backend.core.errors import ApiError
from backend.core.models import Asset, User
from backend.core.permissions import Action
from backend.modules.universes.service import check_universe_access, record_activity, record_audit

MAX_IMAGE_EDGE = 100_000
MAX_IMAGE_PIXELS = 100_000_000


def inspect_image(data: bytes) -> tuple[str, int | None, int | None]:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        if len(data) < 24 or data[12:16] != b"IHDR":
            raise ApiError(415, "invalid_image", "The uploaded image is not a valid PNG.")
        width, height = struct.unpack(">II", data[16:24])
        mime_type = "image/png"
    elif data.startswith(b"\xff\xd8\xff"):
        if len(data) < 4:
            raise ApiError(415, "invalid_image", "The uploaded image is incomplete.")
        return "image/jpeg", None, None
    elif len(data) >= 16 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", None, None
    else:
        raise ApiError(
            415,
            "unsupported_image",
            "Upload a PNG, JPEG, or WebP image.",
        )

    if (
        width < 1
        or height < 1
        or width > MAX_IMAGE_EDGE
        or height > MAX_IMAGE_EDGE
        or width * height > MAX_IMAGE_PIXELS
    ):
        raise ApiError(422, "invalid_image_dimensions", "The image dimensions are not supported.")
    return mime_type, width, height


def _safe_filename(filename: str | None) -> str:
    basename = (filename or "map-image").replace("\\", "/").split("/")[-1]
    normalized = unicodedata.normalize("NFC", basename).strip()
    if not normalized or normalized in {".", ".."}:
        normalized = "map-image"
    return normalized[:255]


def create_asset(
    *,
    db,
    user: User,
    universe_id: uuid.UUID,
    payload: bytes,
    filename: str | None,
    media_root: str,
    max_bytes: int,
    request_id: str | None = None,
) -> Asset:
    check_universe_access(db, universe_id, user, Action.MAP_CREATE)
    if not payload:
        raise ApiError(422, "empty_upload", "The uploaded file is empty.")
    if len(payload) > max_bytes:
        raise ApiError(413, "asset_too_large", "The uploaded image exceeds the configured size limit.")

    mime_type, width, height = inspect_image(payload)
    asset_id = uuid.uuid4()
    storage_key = asset_id.hex
    root = Path(media_root).expanduser()
    if not root.is_absolute():
        root = Path.cwd() / root
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination = (root / storage_key).resolve()
    if destination.parent != root:
        raise ApiError(500, "storage_error", "The asset could not be stored.")
    temporary = root / f".{storage_key}.tmp"
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
        temporary.replace(destination)

        asset = Asset(
            id=asset_id,
            universe_id=universe_id,
            storage_key=storage_key,
            original_filename=_safe_filename(filename),
            mime_type=mime_type,
            byte_size=len(payload),
            checksum_sha256=hashlib.sha256(payload).hexdigest(),
            width=width,
            height=height,
            uploaded_by=user.id,
        )
        db.add(asset)
        record_audit(
            db,
            universe_id,
            user.id,
            "asset.uploaded",
            "asset",
            asset_id,
            request_id=request_id,
        )
        record_activity(
            db,
            universe_id,
            user.id,
            "asset.uploaded",
            "asset",
            asset_id,
            {"mime_type": mime_type, "byte_size": len(payload)},
        )
        db.commit()
        db.refresh(asset)
        return asset
    except Exception:
        db.rollback()
        temporary.unlink(missing_ok=True)
        destination.unlink(missing_ok=True)
        raise


def get_asset_for_download(
    db, asset_id: uuid.UUID, user: User, media_root: str
) -> tuple[Asset, Path]:
    asset = db.get(Asset, asset_id)
    if asset is None or asset.deleted_at is not None:
        raise ApiError(404, "asset_not_found", "The requested asset does not exist.")
    check_universe_access(db, asset.universe_id, user, Action.MAP_READ)
    root = Path(media_root).expanduser()
    if not root.is_absolute():
        root = Path.cwd() / root
    root = root.resolve()
    path = (root / asset.storage_key).resolve()
    if path.parent != root or not path.is_file():
        raise ApiError(404, "asset_not_found", "The requested asset does not exist.")
    return asset, path
