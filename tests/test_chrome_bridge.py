"""Tests for the Chrome extension WebSocket bridge."""
import asyncio
import json
import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock, MagicMock

from src.chrome_bridge import ChromeBridge


class TestBridgeLifecycle:
    @pytest.mark.asyncio
    async def test_starts_and_stops(self):
        """Bridge starts a WebSocket server and stops cleanly."""
        bridge = ChromeBridge(port=0)  # port 0 = OS picks available port
        await bridge.start()
        assert bridge.is_running
        assert not bridge.is_connected
        await bridge.stop()
        assert not bridge.is_running

    @pytest.mark.asyncio
    async def test_not_connected_by_default(self):
        """Bridge reports not connected when no client is attached."""
        bridge = ChromeBridge(port=0)
        assert not bridge.is_connected
        assert not bridge.is_running

    @pytest.mark.asyncio
    async def test_start_without_websockets_library(self):
        """Bridge handles missing websockets library gracefully."""
        with patch("src.chrome_bridge.HAS_WEBSOCKETS", False):
            bridge = ChromeBridge(port=0)
            await bridge.start()
            assert not bridge.is_running


class TestBridgeCommands:
    @pytest.mark.asyncio
    async def test_send_command_not_connected_raises(self):
        """Sending a command when not connected raises ConnectionError."""
        bridge = ChromeBridge(port=0)
        with pytest.raises(ConnectionError, match="not connected"):
            await bridge.create_bookmark("https://example.com", "Test", "bookmark_bar")

    @pytest.mark.asyncio
    async def test_send_command_with_mock_ws(self):
        """Commands are sent as JSON and responses are parsed."""
        bridge = ChromeBridge(port=0)

        mock_ws = AsyncMock()
        bridge._ws = mock_ws
        bridge._connected = True

        async def fake_send(data):
            msg = json.loads(data)
            response = json.dumps({
                "id": msg["id"],
                "status": "ok",
                "result": {"id": "42", "title": "Test"},
            })
            bridge._pending[msg["id"]].set_result(json.loads(response))

        mock_ws.send = fake_send

        result = await bridge.create_bookmark("https://example.com", "Test", "bookmark_bar")
        assert result["id"] == "42"
        assert result["title"] == "Test"

    @pytest.mark.asyncio
    async def test_send_command_error_response_raises(self):
        """Extension error responses raise RuntimeError."""
        bridge = ChromeBridge(port=0)

        mock_ws = AsyncMock()
        bridge._ws = mock_ws
        bridge._connected = True

        async def fake_send(data):
            msg = json.loads(data)
            response = {
                "id": msg["id"],
                "status": "error",
                "error": "Bookmark not found",
            }
            bridge._pending[msg["id"]].set_result(response)

        mock_ws.send = fake_send

        with pytest.raises(RuntimeError, match="Bookmark not found"):
            await bridge.delete_bookmark("https://nonexistent.com")

    @pytest.mark.asyncio
    async def test_send_command_timeout(self):
        """Commands that don't get a response time out."""
        bridge = ChromeBridge(port=0)

        mock_ws = AsyncMock()
        bridge._ws = mock_ws
        bridge._connected = True

        # send does nothing, so the future never resolves
        mock_ws.send = AsyncMock()

        # Use a very short timeout
        import src.chrome_bridge as bridge_module
        original_timeout = bridge_module.RESPONSE_TIMEOUT
        bridge_module.RESPONSE_TIMEOUT = 0.1

        try:
            with pytest.raises(TimeoutError):
                await bridge.move_bookmark("https://example.com", "bookmark_bar")
        finally:
            bridge_module.RESPONSE_TIMEOUT = original_timeout

    @pytest.mark.asyncio
    async def test_bulk_move_counts_successes(self):
        """bulk_move returns the count of successful moves."""
        bridge = ChromeBridge(port=0)

        mock_ws = AsyncMock()
        bridge._ws = mock_ws
        bridge._connected = True

        call_count = 0

        async def fake_send(data):
            nonlocal call_count
            msg = json.loads(data)
            call_count += 1
            if call_count == 2:
                # Second call fails
                response = {"id": msg["id"], "status": "error", "error": "not found"}
            else:
                response = {"id": msg["id"], "status": "ok", "result": {}}
            bridge._pending[msg["id"]].set_result(response)

        mock_ws.send = fake_send

        moves = [
            {"url": "https://a.com", "target_folder": "bookmark_bar/Work"},
            {"url": "https://missing.com", "target_folder": "bookmark_bar/Work"},
            {"url": "https://b.com", "target_folder": "bookmark_bar/Work"},
        ]
        count = await bridge.bulk_move(moves)
        assert count == 2  # first and third succeed


class TestBridgeHighLevelMethods:
    """Test that high-level methods send the right actions."""

    @pytest.mark.asyncio
    async def test_create_bookmark_sends_create(self):
        bridge = ChromeBridge(port=0)
        bridge._send_command = AsyncMock(return_value={"id": "1"})
        await bridge.create_bookmark("https://x.com", "X", "bookmark_bar")
        bridge._send_command.assert_called_once_with("create", {
            "url": "https://x.com", "title": "X", "folderPath": "bookmark_bar",
        })

    @pytest.mark.asyncio
    async def test_create_folder_sends_create_no_url(self):
        bridge = ChromeBridge(port=0)
        bridge._send_command = AsyncMock(return_value={"id": "2"})
        await bridge.create_folder("Work", "bookmark_bar")
        bridge._send_command.assert_called_once_with("create", {
            "title": "Work", "folderPath": "bookmark_bar",
        })

    @pytest.mark.asyncio
    async def test_move_sends_move(self):
        bridge = ChromeBridge(port=0)
        bridge._send_command = AsyncMock(return_value={})
        await bridge.move_bookmark("https://x.com", "bookmark_bar/Work")
        bridge._send_command.assert_called_once_with("move", {
            "url": "https://x.com", "targetFolder": "bookmark_bar/Work",
        })

    @pytest.mark.asyncio
    async def test_rename_sends_update(self):
        bridge = ChromeBridge(port=0)
        bridge._send_command = AsyncMock(return_value={})
        await bridge.rename_bookmark("https://x.com", "New Title")
        bridge._send_command.assert_called_once_with("update", {
            "url": "https://x.com", "title": "New Title",
        })

    @pytest.mark.asyncio
    async def test_delete_sends_remove(self):
        bridge = ChromeBridge(port=0)
        bridge._send_command = AsyncMock(return_value={"removed": True})
        await bridge.delete_bookmark("https://x.com")
        bridge._send_command.assert_called_once_with("remove", {
            "url": "https://x.com",
        })

    @pytest.mark.asyncio
    async def test_get_tree_sends_getTree(self):
        bridge = ChromeBridge(port=0)
        bridge._send_command = AsyncMock(return_value=[])
        await bridge.get_tree()
        bridge._send_command.assert_called_once_with("getTree", {})
