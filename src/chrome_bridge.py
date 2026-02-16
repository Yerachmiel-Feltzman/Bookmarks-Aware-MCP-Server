"""WebSocket bridge to Chrome extension for live bookmark editing.

When the companion Chrome extension is connected, bookmark write operations
are routed through Chrome's native chrome.bookmarks API instead of editing
the JSON file directly.  This avoids the race condition where Chrome
overwrites file-level changes from its in-memory state.

Protocol:
  Server -> Extension:  {"id": "<uuid>", "action": "<cmd>", "params": {...}}
  Extension -> Server:  {"id": "<uuid>", "status": "ok"|"error", "result"|"error": ...}
"""
import asyncio
import json
import sys
import uuid
from typing import Any, Dict, Optional

try:
    import websockets
    from websockets.asyncio.server import serve as ws_serve
    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False

DEFAULT_PORT = 8765
RESPONSE_TIMEOUT = 15.0  # seconds to wait for extension response


class ChromeBridge:
    """Async WebSocket server that proxies commands to the Chrome extension."""

    def __init__(self, port: int = DEFAULT_PORT):
        self.port = port
        self._ws: Optional[Any] = None
        self._server: Optional[Any] = None
        self._pending: Dict[str, asyncio.Future] = {}
        self._running = False
        self._connected = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the WebSocket server (non-blocking)."""
        if not HAS_WEBSOCKETS:
            print(
                "[ChromeBridge] websockets library not installed. "
                "Bridge disabled. Install with: pip install websockets",
                file=sys.stderr,
            )
            return

        try:
            self._server = await ws_serve(
                self._handler,
                "localhost",
                self.port,
            )
            self._running = True
            print(
                f"[ChromeBridge] WebSocket server listening on ws://localhost:{self.port}",
                file=sys.stderr,
            )
        except OSError as e:
            print(
                f"[ChromeBridge] Could not start WebSocket server on port {self.port}: {e}",
                file=sys.stderr,
            )

    async def stop(self) -> None:
        """Shut down the WebSocket server."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        self._running = False
        self._connected = False
        self._ws = None

    @property
    def is_connected(self) -> bool:
        """True if the Chrome extension is currently connected."""
        return self._ws is not None and self._connected

    @property
    def is_running(self) -> bool:
        """True if the WebSocket server is up (even if no client connected)."""
        return self._running

    # ------------------------------------------------------------------
    # WebSocket handler
    # ------------------------------------------------------------------

    async def _handler(self, websocket: Any) -> None:
        """Handle a single extension connection."""
        self._ws = websocket
        self._connected = True
        print("[ChromeBridge] Chrome extension connected", file=sys.stderr)

        try:
            async for raw in websocket:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                # Keepalive / pong
                msg_type = msg.get("type")
                if msg_type in ("keepalive", "pong"):
                    continue

                # Response to a pending command
                msg_id = msg.get("id")
                if msg_id and msg_id in self._pending:
                    self._pending[msg_id].set_result(msg)
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            print("[ChromeBridge] Chrome extension disconnected", file=sys.stderr)
            self._connected = False
            self._ws = None

    # ------------------------------------------------------------------
    # Send commands
    # ------------------------------------------------------------------

    async def _send_command(self, action: str, params: dict) -> dict:
        """Send a command to the extension and wait for the response.

        Raises:
            ConnectionError: Extension not connected.
            TimeoutError: Extension did not respond in time.
            RuntimeError: Extension returned an error.
        """
        if not self.is_connected:
            raise ConnectionError("Chrome extension is not connected")

        cmd_id = str(uuid.uuid4())
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[cmd_id] = future

        try:
            await self._ws.send(json.dumps({
                "id": cmd_id,
                "action": action,
                "params": params,
            }))

            response = await asyncio.wait_for(future, timeout=RESPONSE_TIMEOUT)

            if response.get("status") == "error":
                raise RuntimeError(response.get("error", "Unknown extension error"))

            return response.get("result", {})
        except asyncio.TimeoutError:
            raise TimeoutError(
                f"Chrome extension did not respond to '{action}' within {RESPONSE_TIMEOUT}s"
            )
        finally:
            self._pending.pop(cmd_id, None)

    # ------------------------------------------------------------------
    # High-level bookmark operations
    # ------------------------------------------------------------------

    async def create_bookmark(self, url: str, title: str, folder_path: str) -> dict:
        """Create a bookmark via Chrome API."""
        return await self._send_command("create", {
            "url": url, "title": title, "folderPath": folder_path,
        })

    async def create_folder(self, folder_name: str, parent_path: str) -> dict:
        """Create a folder via Chrome API."""
        return await self._send_command("create", {
            "title": folder_name, "folderPath": parent_path,
        })

    async def move_bookmark(self, url: str, target_folder: str) -> dict:
        """Move a bookmark via Chrome API."""
        return await self._send_command("move", {
            "url": url, "targetFolder": target_folder,
        })

    async def rename_bookmark(self, url: str, new_title: str) -> dict:
        """Rename a bookmark via Chrome API."""
        return await self._send_command("update", {
            "url": url, "title": new_title,
        })

    async def delete_bookmark(self, url: str) -> dict:
        """Delete a bookmark via Chrome API."""
        return await self._send_command("remove", {"url": url})

    async def bulk_move(self, moves: list) -> int:
        """Move multiple bookmarks. Returns success count."""
        success = 0
        for move in moves:
            try:
                await self.move_bookmark(move["url"], move["target_folder"])
                success += 1
            except Exception as e:
                print(
                    f"[ChromeBridge] Failed to move {move.get('url')}: {e}",
                    file=sys.stderr,
                )
        return success

    async def get_tree(self) -> dict:
        """Get full bookmark tree from Chrome."""
        return await self._send_command("getTree", {})


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_bridge: Optional[ChromeBridge] = None


def get_bridge() -> ChromeBridge:
    """Get or create the global bridge instance."""
    global _bridge
    if _bridge is None:
        from src.config import get_config
        port = get_config().bridge_port
        _bridge = ChromeBridge(port=port)
    return _bridge
