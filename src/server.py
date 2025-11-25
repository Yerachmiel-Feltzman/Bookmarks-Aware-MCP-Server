"""MCP server for bookmarks-aware search."""
import asyncio
import sys
from pathlib import Path
from typing import Any, Optional

# Add project root to Python path for absolute imports
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from src.bookmarks_reader import read_chrome_bookmarks, get_chrome_bookmarks_path
from src.search import KeywordSearchEngine, SearchEngine


# Global state
_bookmarks_cache: Optional[list] = None
_search_engine: SearchEngine = KeywordSearchEngine()


def load_bookmarks(bookmarks_path: Optional[Path] = None) -> list:
    """Load bookmarks, using cache if available.
    
    Args:
        bookmarks_path: Optional path to bookmarks file
        
    Returns:
        List of bookmarks
    """
    global _bookmarks_cache
    
    if _bookmarks_cache is None:
        try:
            _bookmarks_cache = read_chrome_bookmarks(bookmarks_path)
        except FileNotFoundError as e:
            print(f"Warning: Could not find bookmarks file: {e}", file=sys.stderr)
            _bookmarks_cache = []
        except Exception as e:
            print(f"Error loading bookmarks: {e}", file=sys.stderr)
            _bookmarks_cache = []
    
    return _bookmarks_cache


async def get_bookmarks_tool(query: str) -> list[TextContent]:
    """Tool handler for get_bookmarks.
    
    Args:
        query: Search query string
        
    Returns:
        List of TextContent with bookmark results
    """
    bookmarks = load_bookmarks()
    
    if not bookmarks:
        return [TextContent(
            type="text",
            text="No bookmarks available. Please ensure Chrome bookmarks file exists."
        )]
    
    # Search for relevant bookmarks
    results = _search_engine.search(query, bookmarks, limit=10)
    
    if not results:
        return [TextContent(
            type="text",
            text=f"No bookmarks found matching query: {query}"
        )]
    
    # Format results as JSON
    import json
    result_text = json.dumps(results, indent=2)
    
    return [TextContent(
        type="text",
        text=result_text
    )]


def create_server() -> Server:
    """Create and configure the MCP server.
    
    Returns:
        Configured Server instance
    """
    server = Server("bookmarks-aware-mcp")
    
    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """List available tools."""
        return [
            Tool(
                name="get_bookmarks",
                description="Search and retrieve relevant bookmarks based on a query. Returns a list of bookmarks with url, title, and description.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query to find relevant bookmarks"
                        }
                    },
                    "required": ["query"]
                }
            )
        ]
    
    @server.call_tool()
    async def call_tool(name: str, arguments: Any) -> list[TextContent]:
        """Handle tool calls."""
        if name == "get_bookmarks":
            query = arguments.get("query", "")
            if not query:
                return [TextContent(
                    type="text",
                    text="Error: 'query' parameter is required"
                )]
            return await get_bookmarks_tool(query)
        else:
            raise ValueError(f"Unknown tool: {name}")
    
    return server


async def main():
    """Main entry point for the MCP server."""
    server = create_server()
    
    async with stdio_server() as (read_stream, write_stream):
        initialization_options = server.create_initialization_options()
        await server.run(read_stream, write_stream, initialization_options)


