"""Short-lived, HMAC-signed collaboration tickets.

Long-lived session cookies must never appear in a WebSocket query string: they
leak through proxy logs, browser history and crash reports.  The REST ticket
endpoint exchanges an authenticated session for a single-document credential
that expires quickly and carries only the identifiers needed to re-authorise
the connection.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any

TICKET_PREFIX = "wwc1"
MAX_TICKET_LENGTH = 4096


class TicketError(ValueError):
    """Raised for malformed, tampered, or expired collaboration tickets."""

    def __init__(self, code: str = "invalid_ticket") -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class CollaborationTicket:
    token: str
    jti: uuid.UUID
    user_id: uuid.UUID
    session_id: uuid.UUID
    universe_id: uuid.UUID
    document_id: uuid.UUID
    display_name: str
    can_write: bool
    collab_generation: int
    issued_at: int
    expires_at: int


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _signature(secret: str, body: str) -> str:
    digest = hmac.new(
        secret.encode("utf-8"),
        f"{TICKET_PREFIX}.{body}".encode("ascii"),
        hashlib.sha256,
    ).digest()
    return _b64encode(digest)


def issue_ticket(
    *,
    secret: str,
    ttl_seconds: int,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    universe_id: uuid.UUID,
    document_id: uuid.UUID,
    display_name: str,
    can_write: bool,
    collab_generation: int,
) -> CollaborationTicket:
    now = int(time.time())
    expires = now + ttl_seconds
    jti = uuid.uuid4()
    payload: dict[str, Any] = {
        "v": 1,
        "jti": str(jti),
        "sub": str(user_id),
        "sid": str(session_id),
        "uni": str(universe_id),
        "doc": str(document_id),
        "name": display_name,
        "write": bool(can_write),
        "gen": int(collab_generation),
        "iat": now,
        "exp": expires,
    }
    body = _b64encode(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
    )
    token = f"{TICKET_PREFIX}.{body}.{_signature(secret, body)}"
    return CollaborationTicket(
        token=token,
        jti=jti,
        user_id=user_id,
        session_id=session_id,
        universe_id=universe_id,
        document_id=document_id,
        display_name=display_name,
        can_write=bool(can_write),
        collab_generation=int(collab_generation),
        issued_at=now,
        expires_at=expires,
    )


def decode_ticket(
    token: str, *, secret: str, now: int | None = None
) -> CollaborationTicket:
    if not token or len(token) > MAX_TICKET_LENGTH:
        raise TicketError("invalid_ticket")
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != TICKET_PREFIX:
        raise TicketError("invalid_ticket")
    body, supplied_signature = parts[1], parts[2]
    expected_signature = _signature(secret, body)
    if not hmac.compare_digest(supplied_signature, expected_signature):
        raise TicketError("invalid_ticket")
    try:
        payload = json.loads(_b64decode(body))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TicketError("invalid_ticket") from exc
    if not isinstance(payload, dict) or payload.get("v") != 1:
        raise TicketError("invalid_ticket")

    current_time = int(time.time()) if now is None else now
    try:
        issued_at = int(payload["iat"])
        expires_at = int(payload["exp"])
        ticket = CollaborationTicket(
            token=token,
            jti=uuid.UUID(str(payload["jti"])),
            user_id=uuid.UUID(str(payload["sub"])),
            session_id=uuid.UUID(str(payload["sid"])),
            universe_id=uuid.UUID(str(payload["uni"])),
            document_id=uuid.UUID(str(payload["doc"])),
            display_name=str(payload.get("name") or "")[:80],
            can_write=bool(payload.get("write")),
            collab_generation=int(payload["gen"]),
            issued_at=issued_at,
            expires_at=expires_at,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise TicketError("invalid_ticket") from exc

    if expires_at <= current_time:
        raise TicketError("ticket_expired")
    if issued_at > current_time + 30:
        raise TicketError("invalid_ticket")
    if expires_at - issued_at > 3600:
        raise TicketError("invalid_ticket")
    if ticket.collab_generation < 0:
        raise TicketError("invalid_ticket")
    return ticket
