"""Aerumentis — Unit Tests: API Key Service."""
import pytest
from datetime import datetime, timedelta, timezone

from aerumentis.services.api_key_service import (
    _hash_api_key, generate_api_key_pair,
)


class TestAPIKeyGeneration:
    def test_generate_api_key_pair_format(self):
        raw_key, key_hash, key_prefix = generate_api_key_pair()
        assert raw_key.startswith("aer_")
        assert len(raw_key) > 30
        assert len(key_hash) == 64  # SHA-256 hex
        assert key_prefix == raw_key[:12]

    def test_generate_api_key_pair_uniqueness(self):
        key1 = generate_api_key_pair()
        key2 = generate_api_key_pair()
        assert key1[0] != key2[0]
        assert key1[1] != key2[1]

    def test_hash_api_key_consistent(self):
        raw = "aer_testkey123"
        h1 = _hash_api_key(raw)
        h2 = _hash_api_key(raw)
        assert h1 == h2

    def test_hash_api_key_different_keys(self):
        assert _hash_api_key("aer_key1") != _hash_api_key("aer_key2")

    def test_hash_is_not_raw(self):
        raw = "aer_secretkey"
        assert _hash_api_key(raw) != raw
        assert len(_hash_api_key(raw)) == 64
