"""Tests for search module."""
import pytest

from src.search import KeywordSearchEngine


@pytest.fixture
def engine():
    return KeywordSearchEngine()


@pytest.fixture
def metadata():
    return {
        "https://docs.python.org": {
            "summary": "Official Python documentation covering the standard library.",
            "tags": ["python", "documentation", "stdlib"],
        },
        "https://sqlite.org/guide": {
            "summary": "Guide to using SQLite for data storage.",
            "tags": ["sqlite", "database", "tutorial"],
        },
        "https://stackoverflow.com": {
            "summary": "Q&A site for programming questions.",
            "tags": ["programming", "qa", "community"],
        },
    }


class TestBasicSearch:
    def test_finds_by_title(self, engine, sample_bookmarks):
        results = engine.search("python", sample_bookmarks)
        assert len(results) >= 1
        assert any(r["url"] == "https://docs.python.org" for r in results)

    def test_finds_by_url(self, engine, sample_bookmarks):
        results = engine.search("sqlite", sample_bookmarks)
        assert any(r["url"] == "https://sqlite.org/guide" for r in results)

    def test_empty_query_returns_empty(self, engine, sample_bookmarks):
        results = engine.search("", sample_bookmarks)
        assert results == []

    def test_no_match_returns_empty(self, engine, sample_bookmarks):
        results = engine.search("xyznonexistent", sample_bookmarks)
        assert results == []

    def test_respects_limit(self, engine, sample_bookmarks):
        results = engine.search("com", sample_bookmarks, limit=2)
        assert len(results) <= 2

    def test_ranked_by_relevance(self, engine, sample_bookmarks):
        results = engine.search("jira board", sample_bookmarks)
        assert results[0]["url"] == "https://jira.example.com/board"


class TestMetadataSearch:
    def test_finds_via_summary(self, engine, sample_bookmarks, metadata):
        results = engine.search("standard library", sample_bookmarks, metadata=metadata)
        assert any(r["url"] == "https://docs.python.org" for r in results)

    def test_finds_via_tags(self, engine, sample_bookmarks, metadata):
        results = engine.search("database", sample_bookmarks, metadata=metadata)
        assert any(r["url"] == "https://sqlite.org/guide" for r in results)

    def test_results_include_metadata(self, engine, sample_bookmarks, metadata):
        results = engine.search("python", sample_bookmarks, metadata=metadata)
        python_result = next(r for r in results if r["url"] == "https://docs.python.org")
        assert "summary" in python_result
        assert "tags" in python_result

    def test_tag_match_boosts_score(self, engine, sample_bookmarks, metadata):
        # "tutorial" is a tag on sqlite.org/guide
        results = engine.search("tutorial", sample_bookmarks, metadata=metadata)
        assert results[0]["url"] == "https://sqlite.org/guide"


class TestTagFiltering:
    def test_filter_by_tag(self, engine, sample_bookmarks, metadata):
        results = engine.search("", sample_bookmarks, tags_filter=["python"], metadata=metadata)
        assert len(results) == 1
        assert results[0]["url"] == "https://docs.python.org"

    def test_filter_with_query(self, engine, sample_bookmarks, metadata):
        results = engine.search("guide", sample_bookmarks, tags_filter=["database"], metadata=metadata)
        assert len(results) == 1
        assert results[0]["url"] == "https://sqlite.org/guide"

    def test_filter_no_match(self, engine, sample_bookmarks, metadata):
        results = engine.search("", sample_bookmarks, tags_filter=["nonexistent"], metadata=metadata)
        assert results == []

    def test_filter_and_logic(self, engine, sample_bookmarks, metadata):
        # AND logic: must have both tags
        results = engine.search("", sample_bookmarks, tags_filter=["python", "documentation"], metadata=metadata)
        assert len(results) == 1
        assert results[0]["url"] == "https://docs.python.org"
