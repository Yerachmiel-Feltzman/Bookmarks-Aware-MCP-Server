"""Tests for config module."""
import os
import pytest

from src.config import Config, EnrichmentConfig, get_config


class TestConfig:
    def test_default_values(self):
        config = Config()
        assert config.enrichment.requests_per_second == 2.0
        assert config.enrichment.max_concurrent_requests == 5
        assert config.enrichment.max_content_length == 50000
        assert config.enrichment.request_timeout == 30.0
        assert config.enrichment.max_age_days == 30
        assert config.metadata_db_path is None
        assert config.chrome_profile == "Default"

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("BOOKMARKS_RATE_LIMIT", "5.0")
        monkeypatch.setenv("BOOKMARKS_MAX_CONTENT", "10000")
        monkeypatch.setenv("BOOKMARKS_METADATA_DB", "/tmp/test.db")

        config = Config.from_env()
        assert config.enrichment.requests_per_second == 5.0
        assert config.enrichment.max_content_length == 10000
        assert str(config.metadata_db_path) == "/tmp/test.db"

    def test_chrome_profile_from_env(self, monkeypatch):
        monkeypatch.setenv("BOOKMARKS_CHROME_PROFILE", "Profile 1")
        config = Config.from_env()
        assert config.chrome_profile == "Profile 1"

    def test_chrome_profile_default(self, monkeypatch):
        monkeypatch.delenv("BOOKMARKS_CHROME_PROFILE", raising=False)
        config = Config.from_env()
        assert config.chrome_profile == "Default"

    def test_bridge_port_default(self):
        config = Config()
        assert config.bridge_port == 8765

    def test_bridge_port_from_env(self, monkeypatch):
        monkeypatch.setenv("BOOKMARKS_BRIDGE_PORT", "9999")
        config = Config.from_env()
        assert config.bridge_port == 9999
