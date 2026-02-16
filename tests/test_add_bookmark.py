"""Tests for add_bookmark functionality."""
import json
import pytest

from src.bookmarks_store import add_bookmark, read_chrome_bookmarks


class TestAddBookmark:
    def test_adds_bookmark(self, sample_bookmarks_path):
        ok = add_bookmark(
            url="https://new-site.com",
            title="New Site",
            folder_path="bookmark_bar",
            bookmarks_path=sample_bookmarks_path,
        )
        assert ok is True

        bookmarks = read_chrome_bookmarks(sample_bookmarks_path)
        added = next((b for b in bookmarks if b["url"] == "https://new-site.com"), None)
        assert added is not None
        assert added["title"] == "New Site"
        assert added["folder"] == "bookmark_bar"

    def test_adds_to_subfolder(self, sample_bookmarks_path):
        ok = add_bookmark(
            url="https://new-work-tool.com",
            title="Work Tool",
            folder_path="bookmark_bar/Work",
            bookmarks_path=sample_bookmarks_path,
        )
        assert ok is True

        bookmarks = read_chrome_bookmarks(sample_bookmarks_path)
        added = next((b for b in bookmarks if b["url"] == "https://new-work-tool.com"), None)
        assert added is not None
        assert added["folder"] == "bookmark_bar/Work"

    def test_nonexistent_folder_fails(self, sample_bookmarks_path):
        ok = add_bookmark(
            url="https://orphan.com",
            title="Orphan",
            folder_path="bookmark_bar/NonExistent",
            bookmarks_path=sample_bookmarks_path,
        )
        assert ok is False

    def test_increments_total_count(self, sample_bookmarks_path):
        before = len(read_chrome_bookmarks(sample_bookmarks_path))
        add_bookmark("https://new.com", "New", "bookmark_bar", sample_bookmarks_path)
        after = len(read_chrome_bookmarks(sample_bookmarks_path))
        assert after == before + 1

    def test_json_valid_after_add(self, sample_bookmarks_path):
        add_bookmark("https://new.com", "New", "bookmark_bar", sample_bookmarks_path)
        data = json.loads(sample_bookmarks_path.read_text())
        assert "roots" in data

    def test_creates_backup_before_add(self, sample_bookmarks_path):
        add_bookmark("https://new.com", "New", "bookmark_bar", sample_bookmarks_path)
        bak = sample_bookmarks_path.with_suffix(".bak")
        assert bak.exists()
