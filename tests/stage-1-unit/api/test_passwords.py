import binascii
import hashlib

import pytest

from shared.passwords import hash_password, verify_password


class TestHashPassword:
    def test_roundtrip_valid_password(self):
        stored = hash_password("secret")
        assert verify_password(stored, "secret") is True

    def test_roundtrip_wrong_password(self):
        stored = hash_password("secret")
        assert verify_password(stored, "wrong") is False

    def test_custom_format_salt_prefix_and_no_dollar(self):
        stored = hash_password("secret").decode("ascii")
        assert "$" not in stored
        assert len(stored[:64]) == 64
        assert len(bytes.fromhex(stored[:64])) == 32

    def test_salts_are_unique(self):
        a = hash_password("secret")
        b = hash_password("secret")
        assert a != b


class TestVerifyLegacyWerkzeugHashes:
    def test_sha256_scheme(self):
        stored = f"sha256$saltsalt${hashlib.sha256(b'saltsaltpw').hexdigest()}"
        assert verify_password(stored.encode("utf-8"), "pw") is True

    def test_pbkdf2_scheme(self):
        dk = hashlib.pbkdf2_hmac("sha256", b"pw", b"salt", 1000)
        stored = f"pbkdf2:sha256:1000$salt${binascii.hexlify(dk).decode('ascii')}"
        assert verify_password(stored.encode("utf-8"), "pw") is True

    def test_scrypt_scheme(self):
        dk = hashlib.scrypt(b"pw", salt=b"salt", n=16384, r=8, p=1)
        stored = f"scrypt:16384:8:1$salt${binascii.hexlify(dk).decode('ascii')}"
        assert verify_password(stored.encode("utf-8"), "pw") is True

    def test_wrong_password_rejected(self):
        dk = hashlib.pbkdf2_hmac("sha256", b"pw", b"salt", 1000)
        stored = f"pbkdf2:sha256:1000$salt${binascii.hexlify(dk).decode('ascii')}"
        assert verify_password(stored.encode("utf-8"), "nope") is False


class TestVerifyGarbageInput:
    @pytest.mark.parametrize(
        "stored",
        [
            b"",
            b"abc",
            b"$",
            b"sha256$onlytwo",
            b"pbkdf2:sha256:1000$onlytwo",
            b"pbkdf2:notahash:1000$salt$" + b"ab" * 32,
            b"pbkdf2:sha256:notanumber$salt$" + b"ab" * 32,
            b"scrypt:16384:8:1$onlytwo",
            b"\xff\xfe invalid utf8",
        ],
    )
    def test_garbage_returns_false_without_exceptions(self, stored):
        assert verify_password(stored, "pw") is False

    def test_unknown_scheme_returns_false(self):
        stored = b"bcrypt$salt$hash"
        assert verify_password(stored, "pw") is False
