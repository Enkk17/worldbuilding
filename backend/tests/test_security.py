from __future__ import annotations

from backend.core.rate_limit import SlidingWindowLimiter
from backend.core.security import hash_password, token_hash, verify_password


def test_passwords_are_argon2id_hashed_and_verified():
    password = "a-long-password-for-testing-123"
    password_hash = hash_password(password)

    assert password_hash.startswith("$argon2id$")
    assert password_hash != password
    assert verify_password(password, password_hash)
    assert not verify_password("wrong-password", password_hash)
    assert not verify_password(password, None)


def test_session_token_hash_is_one_way_sha256():
    token = "opaque-session-token"

    assert token_hash(token) != token
    assert len(token_hash(token)) == 64


def test_sliding_window_rate_limit_expires_attempts():
    limiter = SlidingWindowLimiter()

    assert limiter.allow("login:test", limit=2, window_seconds=10, now=1)
    assert limiter.allow("login:test", limit=2, window_seconds=10, now=2)
    assert not limiter.allow("login:test", limit=2, window_seconds=10, now=3)
    assert limiter.allow("login:test", limit=2, window_seconds=10, now=12)
