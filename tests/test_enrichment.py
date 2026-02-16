"""Tests for enrichment module."""
import pytest

from src.enrichment import compute_content_hash


class TestContentHash:
    def test_deterministic(self):
        h1 = compute_content_hash("hello world")
        h2 = compute_content_hash("hello world")
        assert h1 == h2

    def test_different_input_different_hash(self):
        h1 = compute_content_hash("hello")
        h2 = compute_content_hash("world")
        assert h1 != h2

    def test_returns_string(self):
        h = compute_content_hash("test")
        assert isinstance(h, str)
        assert len(h) == 16  # SHA256 prefix
