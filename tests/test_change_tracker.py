"""Tests for change_tracker module."""
import pytest
import pytest_asyncio

from src.change_tracker import ChangeTracker


@pytest_asyncio.fixture
async def tracker(tmp_path):
    """Create and initialize a test change tracker."""
    db_path = tmp_path / "test_changes.db"
    t = ChangeTracker(db_path)
    await t.initialize()
    yield t
    await t.close()


@pytest.mark.asyncio
class TestChangeTracker:
    async def test_initialize_creates_db(self, tmp_path):
        db_path = tmp_path / "test.db"
        tracker = ChangeTracker(db_path)
        await tracker.initialize()
        assert db_path.exists()
        await tracker.close()

    async def test_record_change(self, tracker):
        change_id = await tracker.record_change(
            action="move",
            url="https://example.com",
            details={"from_folder": "bookmark_bar", "to_folder": "bookmark_bar/Work"},
        )
        assert isinstance(change_id, int)
        assert change_id > 0

    async def test_get_history(self, tracker):
        await tracker.record_change("move", "https://a.com", {"from": "A", "to": "B"})
        await tracker.record_change("rename", "https://b.com", {"old": "Old", "new": "New"})
        await tracker.record_change("delete", "https://c.com", {"title": "Deleted"})

        history = await tracker.get_history(limit=10)
        assert len(history) == 3
        # Newest first
        assert history[0]["action"] == "delete"
        assert history[1]["action"] == "rename"
        assert history[2]["action"] == "move"

    async def test_get_history_respects_limit(self, tracker):
        for i in range(5):
            await tracker.record_change("move", f"https://{i}.com", {"i": i})

        history = await tracker.get_history(limit=2)
        assert len(history) == 2

    async def test_get_last_revertable(self, tracker):
        await tracker.record_change("move", "https://a.com", {"from": "A", "to": "B"})
        await tracker.record_change("rename", "https://b.com", {"old": "O", "new": "N"})

        last = await tracker.get_last_revertable()
        assert last is not None
        assert last["action"] == "rename"

    async def test_get_last_revertable_skips_reverted(self, tracker):
        await tracker.record_change("move", "https://a.com", {"test": 1})
        id2 = await tracker.record_change("rename", "https://b.com", {"test": 2})
        await tracker.mark_reverted(id2)

        last = await tracker.get_last_revertable()
        assert last["action"] == "move"

    async def test_get_last_revertable_none_when_all_reverted(self, tracker):
        id1 = await tracker.record_change("move", "https://a.com", {"test": 1})
        await tracker.mark_reverted(id1)

        last = await tracker.get_last_revertable()
        assert last is None

    async def test_mark_reverted(self, tracker):
        change_id = await tracker.record_change("delete", "https://a.com", {"title": "X"})
        ok = await tracker.mark_reverted(change_id)
        assert ok is True

        history = await tracker.get_history()
        assert history[0]["reverted"] == 1

    async def test_mark_reverted_nonexistent(self, tracker):
        ok = await tracker.mark_reverted(9999)
        assert ok is False

    async def test_details_parsed_as_dict(self, tracker):
        await tracker.record_change("move", "https://a.com", {
            "from_folder": "bookmark_bar",
            "to_folder": "bookmark_bar/Work",
        })
        history = await tracker.get_history()
        details = history[0]["details"]
        assert isinstance(details, dict)
        assert details["from_folder"] == "bookmark_bar"

    async def test_empty_history(self, tracker):
        history = await tracker.get_history()
        assert history == []

    async def test_null_url_for_folder_ops(self, tracker):
        await tracker.record_change("create_folder", None, {
            "folder_name": "Test",
            "parent_folder": "bookmark_bar",
        })
        history = await tracker.get_history()
        assert history[0]["url"] is None
        assert history[0]["action"] == "create_folder"
