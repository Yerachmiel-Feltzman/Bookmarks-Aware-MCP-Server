"""Shared fixtures for tests."""
import json
import pytest
from pathlib import Path


SAMPLE_BOOKMARKS = {
    "checksum": "test",
    "roots": {
        "bookmark_bar": {
            "children": [
                {
                    "id": "1",
                    "name": "Python Docs",
                    "type": "url",
                    "url": "https://docs.python.org"
                },
                {
                    "id": "2",
                    "name": "Work",
                    "type": "folder",
                    "children": [
                        {
                            "id": "3",
                            "name": "Jira Board",
                            "type": "url",
                            "url": "https://jira.example.com/board"
                        },
                        {
                            "id": "4",
                            "name": "Confluence",
                            "type": "url",
                            "url": "https://confluence.example.com"
                        }
                    ]
                },
                {
                    "id": "5",
                    "name": "Tutorials",
                    "type": "folder",
                    "children": [
                        {
                            "id": "6",
                            "name": "SQLite Guide",
                            "type": "url",
                            "url": "https://sqlite.org/guide"
                        }
                    ]
                }
            ],
            "id": "0",
            "name": "Bookmarks Bar",
            "type": "folder"
        },
        "other": {
            "children": [
                {
                    "id": "7",
                    "name": "Stack Overflow",
                    "type": "url",
                    "url": "https://stackoverflow.com"
                }
            ],
            "id": "100",
            "name": "Other Bookmarks",
            "type": "folder"
        },
        "synced": {
            "children": [],
            "id": "200",
            "name": "Mobile Bookmarks",
            "type": "folder"
        }
    },
    "version": 1
}


@pytest.fixture
def sample_bookmarks_path(tmp_path):
    """Create a temporary bookmarks file with sample data."""
    bookmarks_file = tmp_path / "Bookmarks"
    bookmarks_file.write_text(json.dumps(SAMPLE_BOOKMARKS, indent=3))
    return bookmarks_file


@pytest.fixture
def sample_bookmarks():
    """Return sample bookmarks as a list (as read_chrome_bookmarks returns)."""
    return [
        {"id": "1", "url": "https://docs.python.org", "title": "Python Docs", "description": "https://docs.python.org", "folder": "bookmark_bar"},
        {"id": "3", "url": "https://jira.example.com/board", "title": "Jira Board", "description": "https://jira.example.com/board", "folder": "bookmark_bar/Work"},
        {"id": "4", "url": "https://confluence.example.com", "title": "Confluence", "description": "https://confluence.example.com", "folder": "bookmark_bar/Work"},
        {"id": "6", "url": "https://sqlite.org/guide", "title": "SQLite Guide", "description": "https://sqlite.org/guide", "folder": "bookmark_bar/Tutorials"},
        {"id": "7", "url": "https://stackoverflow.com", "title": "Stack Overflow", "description": "https://stackoverflow.com", "folder": "other"},
    ]


@pytest.fixture
def metadata_db_path(tmp_path):
    """Return path for a temporary metadata database."""
    return tmp_path / "test_metadata.db"
