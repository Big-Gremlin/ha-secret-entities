"""Unit tests for the pure crypto helpers."""
from __future__ import annotations

import pytest

from custom_components.secret_entities import crypto


def test_roundtrip():
    key = crypto.generate_key()
    token = crypto.encrypt(key, "hunter2")
    assert crypto.decrypt(key, token) == "hunter2"


def test_token_is_not_plaintext():
    key = crypto.generate_key()
    token = crypto.encrypt(key, "hunter2")
    assert "hunter2" not in token


def test_encryption_is_randomised():
    """Same plaintext + key -> different tokens, both decrypt correctly."""
    key = crypto.generate_key()
    a = crypto.encrypt(key, "same value")
    b = crypto.encrypt(key, "same value")
    assert a != b
    assert crypto.decrypt(key, a) == "same value"
    assert crypto.decrypt(key, b) == "same value"


def test_keys_are_unique():
    assert crypto.generate_key() != crypto.generate_key()


def test_wrong_key_cannot_decrypt():
    token = crypto.encrypt(crypto.generate_key(), "secret")
    with pytest.raises(crypto.InvalidToken):
        crypto.decrypt(crypto.generate_key(), token)


def test_unicode_roundtrip():
    key = crypto.generate_key()
    value = "pässwörd-🔐-ünïcode"
    assert crypto.decrypt(key, crypto.encrypt(key, value)) == value
