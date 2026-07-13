from __future__ import annotations

import binascii
import hashlib

from werkzeug.security import check_password_hash, generate_password_hash


def hash_pass(password: str) -> bytes:
    """Hash a password for storing using Werkzeug (pbkdf2:sha256)."""
    return generate_password_hash(password).encode("utf-8")


def _legacy_verify(provided_password: str, stored_password: bytes) -> bool:
    """Fallback for hashes created by the old custom PBKDF2-SHA512 scheme."""
    try:
        stored = stored_password.decode("ascii")
        salt = stored[:64]
        pwdhash = hashlib.pbkdf2_hmac(
            "sha512",
            provided_password.encode("utf-8"),
            salt.encode("ascii"),
            100000,
        )
        return binascii.hexlify(pwdhash).decode("ascii") == stored[64:]
    except (ValueError, UnicodeDecodeError, IndexError):
        return False


def verify_pass(provided_password: str, stored_password: bytes) -> bool:
    """Verify a stored password — tries Werkzeug first, then legacy fallback."""
    try:
        if check_password_hash(stored_password.decode("utf-8"), provided_password):
            return True
    except (ValueError, TypeError):
        pass
    return _legacy_verify(provided_password, stored_password)
