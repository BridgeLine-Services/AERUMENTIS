"""Aerumentis — Password Hashing (bcrypt 4.x native)."""
from __future__ import annotations

import bcrypt


def hash_password(password: str) -> str:
    """Hash a password using bcrypt with 12 rounds."""
    # bcrypt has a 72-byte max — we pre-hash with sha256 to support longer passwords
    pre_hashed = bcrypt.hashpw(
        password.encode("utf-8")[:72],
        bcrypt.gensalt(rounds=12),
    )
    return pre_hashed.decode("utf-8")


def verify_password(plaintext: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(plaintext.encode("utf-8")[:72], hashed.encode("utf-8"))
    except Exception:
        return False
