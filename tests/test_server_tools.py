"""Tests for server tool registration and tool count."""
import pytest
import asyncio

from src.server import create_server


class TestServerTools:
    def test_server_creates(self):
        server = create_server()
        assert server.name == "bookmarks-aware-mcp"

    def test_all_tools_registered(self):
        from mcp.types import ListToolsRequest

        server = create_server()

        async def check():
            result = await server.request_handlers[ListToolsRequest](None)
            return result.root.tools

        tools = asyncio.run(check())
        tool_names = [t.name for t in tools]

        expected = [
            "health_check",
            "list_bookmarks",
            "get_bookmarks",
            "fetch_page_content",
            "store_bookmark_metadata",
            "get_bookmark_metadata",
            "search_by_tags",
            "add_bookmark",
            "move_bookmark",
            "rename_bookmark",
            "delete_bookmark",
            "create_folder",
            "get_folder_structure",
            "bulk_reorganize",
            "get_change_history",
            "revert_last_change",
        ]

        assert len(tools) == 16
        for name in expected:
            assert name in tool_names, f"Missing tool: {name}"
