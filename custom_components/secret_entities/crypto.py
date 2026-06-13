"""Symmetric encryption helpers.

Each secret gets its own random Fernet key. Fernet (AES-128-CBC + HMAC,
PKCS7) generates a fresh random IV on every ``encrypt`` call, so encrypting
the same plaintext twice yields two different tokens — the value is, as
required, *randomly* encrypted.

These functions are intentionally pure (no Home Assistant imports) so the
crypto behaviour can be unit-tested in isolation.
"""
from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

__all__ = ["generate_key", "encrypt", "decrypt", "InvalidToken"]


def generate_key() -> str:
    """Return a fresh, URL-safe base64 Fernet key as a string."""
    return Fernet.generate_key().decode("ascii")


def encrypt(key: str, plaintext: str) -> str:
    """Encrypt ``plaintext`` with ``key`` and return the token (ciphertext)."""
    token = Fernet(key.encode("ascii")).encrypt(plaintext.encode("utf-8"))
    return token.decode("ascii")


def decrypt(key: str, token: str) -> str:
    """Decrypt ``token`` with ``key`` and return the original plaintext.

    Raises :class:`cryptography.fernet.InvalidToken` if the key does not
    match the token or the token is malformed.
    """
    plaintext = Fernet(key.encode("ascii")).decrypt(token.encode("ascii"))
    return plaintext.decode("utf-8")
