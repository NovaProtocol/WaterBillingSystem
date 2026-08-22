"""Staff password hashing: custom pbkdf2 scheme for new hashes, with
stdlib verification of legacy werkzeug formats (sha256/pbkdf2/scrypt)."""

from __future__ import annotations

import binascii
import hashlib
import os


def hash_password(password: str) -> bytes:
    """Custom scheme: 64-hex salt + hexlified pbkdf2-hmac-sha512 (100k iters).
    Matches the scheme used by the staff seeders."""
    salt = hashlib.sha256(os.urandom(60)).hexdigest().encode("ascii")
    pwdhash = hashlib.pbkdf2_hmac("sha512", password.encode("utf-8"), salt, 100000)
    return salt + binascii.hexlify(pwdhash)


def _verify_custom(stored: str, password: str) -> bool:
    try:
        salt = stored[:64]
        pwdhash = hashlib.pbkdf2_hmac(
            "sha512", password.encode("utf-8"), salt.encode("ascii"), 100000
        )
        return binascii.hexlify(pwdhash).decode("ascii") == stored[64:]
    except (ValueError, UnicodeDecodeError, IndexError):
        return False


def _verify_legacy(stored: str, password: str) -> bool:
    try:
        if stored.startswith("sha256$"):
            _, salt, h = stored.split("$")
            return hashlib.sha256((salt + password).encode("utf-8")).hexdigest() == h
        if stored.startswith("pbkdf2:"):
            # werkzeug: pbkdf2:<hashname>:<iterations>$<salt>$<hexdigest>
            spec, salt, h = stored.split("$")
            _, hashname, iterations = spec.split(":")
            if hashname not in hashlib.algorithms_guaranteed:
                return False
            dk = hashlib.pbkdf2_hmac(
                hashname,
                password.encode("utf-8"),
                salt.encode("utf-8"),
                int(iterations),
            )
            return binascii.hexlify(dk).decode("ascii") == h
        if stored.startswith("scrypt:"):
            # werkzeug: scrypt:<n>:<r>:<p>$<salt>$<hexdigest>
            spec, salt, h = stored.split("$")
            _, n, r, p = spec.split(":")
            dk = hashlib.scrypt(
                password.encode("utf-8"),
                salt=salt.encode("utf-8"),
                n=int(n),
                r=int(r),
                p=int(p),
            )
            return binascii.hexlify(dk).decode("ascii") == h
    except (ValueError, IndexError, TypeError, OverflowError):
        return False
    return False


def verify_password(stored: bytes, password: str) -> bool:
    pw_str = stored.decode("utf-8", errors="replace")
    if "$" not in pw_str:
        return _verify_custom(pw_str, password)
    return _verify_legacy(pw_str, password)
