"""Tests for bookmarks_store module."""
import json
import pytest
from pathlib import Path

from src.bookmarks_store import (
    read_chrome_bookmarks,
    get_folder_structure,
    move_bookmark,
    rename_bookmark,
    delete_bookmark,
    create_folder,
    bulk_move_bookmarks,
    backup_bookmarks,
    load_bookmarks_file,
)


class TestReadBookmarks:
    def test_reads_all_bookmarks(self, sample_bookmarks_path):
        bookmarks = read_chrome_bookmarks(sample_bookmarks_path)
        assert len(bookmarks) == 5

    def test_bookmark_fields(self, sample_bookmarks_path):
        bookmarks = read_chrome_bookmarks(sample_bookmarks_path)
        b = bookmarks[0]
        assert "url" in b
        assert "title" in b
        assert "id" in b
        assert "folder" in b
        assert "description" in b

    def test_folder_paths_use_root_key(self, sample_bookmarks_path):
        bookmarks = read_chrome_bookmarks(sample_bookmarks_path)
        folders = [b["folder"] for b in bookmarks]
        # Root key should be prefix, not folder display name
        assert "bookmark_bar" in folders
        assert "bookmark_bar/Work" in folders
        assert "other" in folders
        # Should NOT contain the folder display name as root
        assert "Bookmarks Bar" not in folders

    def test_nested_folders(self, sample_bookmarks_path):
        bookmarks = read_chrome_bookmarks(sample_bookmarks_path)
        work_bookmarks = [b for b in bookmarks if b["folder"] == "bookmark_bar/Work"]
        assert len(work_bookmarks) == 2

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            read_chrome_bookmarks(tmp_path / "nonexistent")

    def test_malformed_json_raises(self, tmp_path):
        bad_file = tmp_path / "Bookmarks"
        bad_file.write_text("not json")
        with pytest.raises(json.JSONDecodeError):
            read_chrome_bookmarks(bad_file)


class TestFolderStructure:
    def test_returns_all_folders(self, sample_bookmarks_path):
        structure = get_folder_structure(sample_bookmarks_path)
        assert "bookmark_bar" in structure
        assert "bookmark_bar/Work" in structure
        assert "bookmark_bar/Tutorials" in structure
        assert "other" in structure
        assert "synced" in structure

    def test_bookmark_counts(self, sample_bookmarks_path):
        structure = get_folder_structure(sample_bookmarks_path)
        assert structure["bookmark_bar"]["bookmarks"] == 1  # Python Docs
        assert structure["bookmark_bar/Work"]["bookmarks"] == 2
        assert structure["bookmark_bar/Tutorials"]["bookmarks"] == 1

    def test_subfolder_counts(self, sample_bookmarks_path):
        structure = get_folder_structure(sample_bookmarks_path)
        assert structure["bookmark_bar"]["subfolders"] == 2  # Work, Tutorials


class TestBackup:
    def test_creates_backup(self, sample_bookmarks_path):
        bak = backup_bookmarks(sample_bookmarks_path)
        assert bak.exists()
        assert bak.suffix == ".bak"
        assert bak.read_text() == sample_bookmarks_path.read_text()


class TestCreateFolder:
    def test_creates_folder(self, sample_bookmarks_path):
        ok = create_folder("NewFolder", "bookmark_bar", sample_bookmarks_path)
        assert ok is True
        structure = get_folder_structure(sample_bookmarks_path)
        assert "bookmark_bar/NewFolder" in structure

    def test_creates_nested_folder(self, sample_bookmarks_path):
        ok = create_folder("SubFolder", "bookmark_bar/Work", sample_bookmarks_path)
        assert ok is True
        structure = get_folder_structure(sample_bookmarks_path)
        assert "bookmark_bar/Work/SubFolder" in structure

    def test_nonexistent_parent_fails(self, sample_bookmarks_path):
        ok = create_folder("Orphan", "bookmark_bar/NoSuchFolder", sample_bookmarks_path)
        assert ok is False


class TestMoveBookmark:
    def test_moves_bookmark(self, sample_bookmarks_path):
        ok = move_bookmark("https://docs.python.org", "bookmark_bar/Work", sample_bookmarks_path)
        assert ok is True
        bookmarks = read_chrome_bookmarks(sample_bookmarks_path)
        moved = next(b for b in bookmarks if b["url"] == "https://docs.python.org")
        assert moved["folder"] == "bookmark_bar/Work"

    def test_nonexistent_url_fails(self, sample_bookmarks_path):
        ok = move_bookmark("https://no.such.url", "bookmark_bar/Work", sample_bookmarks_path)
        assert ok is False

    def test_nonexistent_target_fails(self, sample_bookmarks_path):
        ok = move_bookmark("https://docs.python.org", "bookmark_bar/NoFolder", sample_bookmarks_path)
        assert ok is False


class TestRenameBookmark:
    def test_renames_bookmark(self, sample_bookmarks_path):
        ok = rename_bookmark("https://docs.python.org", "New Title", sample_bookmarks_path)
        assert ok is True
        bookmarks = read_chrome_bookmarks(sample_bookmarks_path)
        renamed = next(b for b in bookmarks if b["url"] == "https://docs.python.org")
        assert renamed["title"] == "New Title"

    def test_nonexistent_url_fails(self, sample_bookmarks_path):
        ok = rename_bookmark("https://no.such.url", "Title", sample_bookmarks_path)
        assert ok is False


class TestDeleteBookmark:
    def test_deletes_bookmark(self, sample_bookmarks_path):
        before = len(read_chrome_bookmarks(sample_bookmarks_path))
        ok = delete_bookmark("https://docs.python.org", sample_bookmarks_path)
        after = len(read_chrome_bookmarks(sample_bookmarks_path))
        assert ok is True
        assert after == before - 1

    def test_nonexistent_url_fails(self, sample_bookmarks_path):
        ok = delete_bookmark("https://no.such.url", sample_bookmarks_path)
        assert ok is False

    def test_json_valid_after_delete(self, sample_bookmarks_path):
        delete_bookmark("https://docs.python.org", sample_bookmarks_path)
        data = json.loads(sample_bookmarks_path.read_text())
        assert "roots" in data


class TestBulkMove:
    def test_moves_multiple(self, sample_bookmarks_path):
        moves = [
            {"url": "https://docs.python.org", "target_folder": "bookmark_bar/Work"},
            {"url": "https://stackoverflow.com", "target_folder": "bookmark_bar/Work"},
        ]
        count = bulk_move_bookmarks(moves, sample_bookmarks_path)
        assert count == 2
        bookmarks = read_chrome_bookmarks(sample_bookmarks_path)
        work_bookmarks = [b for b in bookmarks if b["folder"] == "bookmark_bar/Work"]
        assert len(work_bookmarks) == 4  # 2 original + 2 moved

    def test_partial_failure(self, sample_bookmarks_path):
        moves = [
            {"url": "https://docs.python.org", "target_folder": "bookmark_bar/Work"},
            {"url": "https://no.such.url", "target_folder": "bookmark_bar/Work"},
        ]
        count = bulk_move_bookmarks(moves, sample_bookmarks_path)
        assert count == 1
