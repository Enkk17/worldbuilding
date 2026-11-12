from __future__ import annotations

import hashlib
import json
import secrets
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

_password_hasher = PasswordHasher()
_dummy_password_hash = _password_hasher.hash(secrets.token_urlsafe(32))


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    candidate = password_hash or _dummy_password_hash
    try:
        verified = _password_hasher.verify(candidate, password)
    except (InvalidHashError, VerifyMismatchError):
        return False
    return password_hash is not None and verified


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def state_hash(payload: Any) -> str:
    """Stable SHA-256 fingerprint for audit before/after snapshots.

    The payload is canonicalised so dictionary insertion order cannot change
    the recorded hash. Full document bodies must not be passed here; pass only
    the safe metadata that belongs in the audit ledger.
    """

    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
