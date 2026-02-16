"""MCP server for bookmarks-aware search."""
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Optional, Dict, List

# Add project root to Python path for absolute imports
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from src.bookmarks_store import (
    read_chrome_bookmarks,
    get_chrome_bookmarks_path,
    move_bookmark,
    rename_bookmark,
    delete_bookmark,
    create_folder,
    get_folder_structure,
    bulk_move_bookmarks,
)
from src.search import KeywordSearchEngine, SearchEngine
from src.metadata_store import get_metadata_store
from src.enrichment import fetch_page_content, compute_content_hash


# Global state
_bookmarks_cache: Optional[list] = None
_search_engine: SearchEngine = KeywordSearchEngine()
_metadata_cache: Optional[Dict[str, Dict[str, Any]]] = None


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


async def load_metadata() -> Dict[str, Dict[str, Any]]:
    """Load all metadata from the store, keyed by URL.
    
    Returns:
        Dict of url -> metadata
    """
    global _metadata_cache
    
    if _metadata_cache is None:
        try:
            store = await get_metadata_store()
            all_metadata = await store.get_all_metadata()
            _metadata_cache = {m['url']: m for m in all_metadata}
        except Exception as e:
            print(f"Error loading metadata: {e}", file=sys.stderr)
            _metadata_cache = {}
    
    return _metadata_cache


def invalidate_metadata_cache() -> None:
    """Invalidate the metadata cache (call after enrichment)."""
    global _metadata_cache
    _metadata_cache = None


async def get_bookmarks_tool(
    query: str,
    tags: Optional[List[str]] = None,
) -> list[TextContent]:
    """Tool handler for get_bookmarks.
    
    Args:
        query: Search query string
        tags: Optional list of tags to filter by
        
    Returns:
        List of TextContent with bookmark results
    """
    bookmarks = load_bookmarks()
    
    if not bookmarks:
        return [TextContent(
            type="text",
            text="No bookmarks available. Please ensure Chrome bookmarks file exists."
        )]
    
    # Load metadata for enhanced search
    metadata = await load_metadata()
    
    # Search for relevant bookmarks with metadata
    results = _search_engine.search(
        query,
        bookmarks,
        limit=10,
        tags_filter=tags,
        metadata=metadata,
    )
    
    if not results:
        msg = f"No bookmarks found matching query: {query}"
        if tags:
            msg += f" with tags: {tags}"
        return [TextContent(
            type="text",
            text=msg
        )]
    
    # Format results as JSON
    result_text = json.dumps(results, indent=2)
    
    return [TextContent(
        type="text",
        text=result_text
    )]


async def fetch_page_content_tool(url: str) -> list[TextContent]:
    """Tool handler for fetch_page_content.
    
    Fetches a URL and returns the extracted text content. The agent
    should then summarize the content and call store_bookmark_metadata.
    
    Args:
        url: URL to fetch
        
    Returns:
        List of TextContent with extracted page content
    """
    try:
        content = await fetch_page_content(url)
        
        if not content:
            return [TextContent(
                type="text",
                text=f"Could not fetch or extract content from: {url}"
            )]
        
        content_hash = compute_content_hash(content)
        
        result = {
            "url": url,
            "content": content,
            "content_hash": content_hash,
        }
        
        return [TextContent(
            type="text",
            text=json.dumps(result, indent=2)
        )]
    except Exception as e:
        return [TextContent(
            type="text",
            text=f"Error fetching page content: {e}"
        )]


async def store_bookmark_metadata_tool(
    url: str,
    summary: str,
    tags: List[str],
    title: Optional[str] = None,
    content_hash: Optional[str] = None,
) -> list[TextContent]:
    """Tool handler for store_bookmark_metadata.
    
    Stores agent-generated summary and tags for a bookmark URL.
    
    Args:
        url: Bookmark URL
        summary: Agent-generated summary
        tags: Agent-generated tags
        title: Optional title override
        content_hash: Optional content hash from fetch_page_content
        
    Returns:
        List of TextContent confirming storage
    """
    try:
        store = await get_metadata_store()
        
        await store.upsert_metadata(
            url=url,
            title=title,
            summary=summary,
            tags=tags,
            content_hash=content_hash,
        )
        invalidate_metadata_cache()
        
        return [TextContent(
            type="text",
            text=json.dumps({
                "status": "stored",
                "url": url,
                "summary": summary,
                "tags": tags,
            }, indent=2)
        )]
    except Exception as e:
        return [TextContent(
            type="text",
            text=f"Error storing metadata: {e}"
        )]


async def get_bookmark_metadata_tool(url: str) -> list[TextContent]:
    """Tool handler for get_bookmark_metadata.
    
    Args:
        url: Bookmark URL
        
    Returns:
        List of TextContent with metadata
    """
    try:
        store = await get_metadata_store()
        metadata = await store.get_metadata(url)
        
        if not metadata:
            return [TextContent(
                type="text",
                text=f"No metadata found for: {url}. Use fetch_page_content to get the page text, then store_bookmark_metadata to save your analysis."
            )]
        
        return [TextContent(
            type="text",
            text=json.dumps(metadata, indent=2, default=str)
        )]
    except Exception as e:
        return [TextContent(
            type="text",
            text=f"Error getting metadata: {e}"
        )]


async def search_by_tags_tool(tags: List[str], limit: int = 10) -> list[TextContent]:
    """Tool handler for search_by_tags.
    
    Args:
        tags: List of tags to search for
        limit: Maximum results
        
    Returns:
        List of TextContent with matching bookmarks
    """
    try:
        store = await get_metadata_store()
        results = await store.search_by_tags(tags, limit=limit)
        
        if not results:
            return [TextContent(
                type="text",
                text=f"No bookmarks found with tags: {tags}"
            )]
        
        return [TextContent(
            type="text",
            text=json.dumps(results, indent=2, default=str)
        )]
    except Exception as e:
        return [TextContent(
            type="text",
            text=f"Error searching by tags: {e}"
        )]


# ============================================================================
# Write Operations
# ============================================================================

def invalidate_bookmarks_cache() -> None:
    """Invalidate the bookmarks cache (call after modifications)."""
    global _bookmarks_cache
    _bookmarks_cache = None


async def move_bookmark_tool(url: str, target_folder: str) -> list[TextContent]:
    """Tool handler for move_bookmark.
    
    Args:
        url: URL of bookmark to move
        target_folder: Target folder path
        
    Returns:
        List of TextContent with result
    """
    try:
        success = move_bookmark(url, target_folder)
        invalidate_bookmarks_cache()
        
        if success:
            return [TextContent(
                type="text",
                text=f"Successfully moved bookmark to {target_folder}"
            )]
        else:
            return [TextContent(
                type="text",
                text=f"Failed to move bookmark. Check that the URL and folder exist."
            )]
    except Exception as e:
        return [TextContent(
            type="text",
            text=f"Error moving bookmark: {e}"
        )]


async def rename_bookmark_tool(url: str, new_title: str) -> list[TextContent]:
    """Tool handler for rename_bookmark.
    
    Args:
        url: URL of bookmark to rename
        new_title: New title
        
    Returns:
        List of TextContent with result
    """
    try:
        success = rename_bookmark(url, new_title)
        invalidate_bookmarks_cache()
        
        if success:
            return [TextContent(
                type="text",
                text=f"Successfully renamed bookmark to '{new_title}'"
            )]
        else:
            return [TextContent(
                type="text",
                text=f"Failed to rename bookmark. Check that the URL exists."
            )]
    except Exception as e:
        return [TextContent(
            type="text",
            text=f"Error renaming bookmark: {e}"
        )]


async def delete_bookmark_tool(url: str) -> list[TextContent]:
    """Tool handler for delete_bookmark.
    
    Args:
        url: URL of bookmark to delete
        
    Returns:
        List of TextContent with result
    """
    try:
        success = delete_bookmark(url)
        invalidate_bookmarks_cache()
        
        if success:
            return [TextContent(
                type="text",
                text=f"Successfully deleted bookmark"
            )]
        else:
            return [TextContent(
                type="text",
                text=f"Failed to delete bookmark. Check that the URL exists."
            )]
    except Exception as e:
        return [TextContent(
            type="text",
            text=f"Error deleting bookmark: {e}"
        )]


async def create_folder_tool(folder_name: str, parent_folder: str) -> list[TextContent]:
    """Tool handler for create_folder.
    
    Args:
        folder_name: Name of new folder
        parent_folder: Path to parent folder
        
    Returns:
        List of TextContent with result
    """
    try:
        success = create_folder(folder_name, parent_folder)
        invalidate_bookmarks_cache()
        
        if success:
            return [TextContent(
                type="text",
                text=f"Successfully created folder '{folder_name}' in {parent_folder}"
            )]
        else:
            return [TextContent(
                type="text",
                text=f"Failed to create folder. Check that the parent folder exists."
            )]
    except Exception as e:
        return [TextContent(
            type="text",
            text=f"Error creating folder: {e}"
        )]


async def get_folder_structure_tool() -> list[TextContent]:
    """Tool handler for get_folder_structure.
    
    Returns:
        List of TextContent with folder structure
    """
    try:
        structure = get_folder_structure()
        
        return [TextContent(
            type="text",
            text=json.dumps(structure, indent=2)
        )]
    except Exception as e:
        return [TextContent(
            type="text",
            text=f"Error getting folder structure: {e}"
        )]


async def bulk_reorganize_tool(moves: List[Dict[str, str]]) -> list[TextContent]:
    """Tool handler for bulk_reorganize.
    
    Args:
        moves: List of moves with 'url' and 'target_folder' keys
        
    Returns:
        List of TextContent with result
    """
    try:
        success_count = bulk_move_bookmarks(moves)
        invalidate_bookmarks_cache()
        
        return [TextContent(
            type="text",
            text=f"Successfully moved {success_count}/{len(moves)} bookmarks"
        )]
    except Exception as e:
        return [TextContent(
            type="text",
            text=f"Error bulk reorganizing bookmarks: {e}"
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
                description="Search and retrieve relevant bookmarks based on a query. Searches across URL, title, description, and enriched metadata (summaries, tags). Returns bookmarks with url, title, description, and any available metadata.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query to find relevant bookmarks"
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional list of tags to filter by (AND logic)"
                        }
                    },
                    "required": ["query"]
                }
            ),
            Tool(
                name="fetch_page_content",
                description="Fetch a URL and extract its text content. Use this to get the page text for a bookmark, then analyze the content yourself to generate a summary and tags, and store them with store_bookmark_metadata.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "URL to fetch and extract content from"
                        }
                    },
                    "required": ["url"]
                }
            ),
            Tool(
                name="store_bookmark_metadata",
                description="Store a summary and tags for a bookmark. Call this after fetching page content and generating your own summary and tags for the bookmark.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "Bookmark URL to store metadata for"
                        },
                        "summary": {
                            "type": "string",
                            "description": "A concise 2-3 sentence summary of the page"
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "3-5 relevant tags/categories for the bookmark"
                        },
                        "title": {
                            "type": "string",
                            "description": "Optional title override"
                        },
                        "content_hash": {
                            "type": "string",
                            "description": "Content hash from fetch_page_content (for change detection)"
                        }
                    },
                    "required": ["url", "summary", "tags"]
                }
            ),
            Tool(
                name="get_bookmark_metadata",
                description="Get the stored metadata (summary, tags) for a specific bookmark URL.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "URL of the bookmark"
                        }
                    },
                    "required": ["url"]
                }
            ),
            Tool(
                name="search_by_tags",
                description="Find bookmarks that have any of the specified tags.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of tags to search for"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of results",
                            "default": 10
                        }
                    },
                    "required": ["tags"]
                }
            ),
            # Write operations
            Tool(
                name="move_bookmark",
                description="Move a bookmark to a different folder. Creates a backup before modifying.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "URL of the bookmark to move"
                        },
                        "target_folder": {
                            "type": "string",
                            "description": "Target folder path (e.g., 'bookmark_bar/Work')"
                        }
                    },
                    "required": ["url", "target_folder"]
                }
            ),
            Tool(
                name="rename_bookmark",
                description="Rename a bookmark's title. Creates a backup before modifying.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "URL of the bookmark to rename"
                        },
                        "new_title": {
                            "type": "string",
                            "description": "New title for the bookmark"
                        }
                    },
                    "required": ["url", "new_title"]
                }
            ),
            Tool(
                name="delete_bookmark",
                description="Delete a bookmark. Creates a backup before modifying.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "URL of the bookmark to delete"
                        }
                    },
                    "required": ["url"]
                }
            ),
            Tool(
                name="create_folder",
                description="Create a new bookmark folder. Creates a backup before modifying.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "folder_name": {
                            "type": "string",
                            "description": "Name of the new folder"
                        },
                        "parent_folder": {
                            "type": "string",
                            "description": "Path to parent folder (e.g., 'bookmark_bar')"
                        }
                    },
                    "required": ["folder_name", "parent_folder"]
                }
            ),
            Tool(
                name="get_folder_structure",
                description="Get the current folder structure of bookmarks with bookmark counts.",
                inputSchema={
                    "type": "object",
                    "properties": {}
                }
            ),
            Tool(
                name="bulk_reorganize",
                description="Move multiple bookmarks at once. Useful for batch reorganization. Creates a backup before modifying.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "moves": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "url": {"type": "string"},
                                    "target_folder": {"type": "string"}
                                },
                                "required": ["url", "target_folder"]
                            },
                            "description": "List of moves, each with 'url' and 'target_folder'"
                        }
                    },
                    "required": ["moves"]
                }
            ),
        ]
    
    @server.call_tool()
    async def call_tool(name: str, arguments: Any) -> list[TextContent]:
        """Handle tool calls."""
        if name == "get_bookmarks":
            query = arguments.get("query", "")
            tags = arguments.get("tags")
            if not query and not tags:
                return [TextContent(
                    type="text",
                    text="Error: 'query' or 'tags' parameter is required"
                )]
            return await get_bookmarks_tool(query, tags)
        
        elif name == "fetch_page_content":
            url = arguments.get("url", "")
            if not url:
                return [TextContent(
                    type="text",
                    text="Error: 'url' parameter is required"
                )]
            return await fetch_page_content_tool(url)
        
        elif name == "store_bookmark_metadata":
            url = arguments.get("url", "")
            summary = arguments.get("summary", "")
            tags = arguments.get("tags", [])
            if not url or not summary:
                return [TextContent(
                    type="text",
                    text="Error: 'url', 'summary', and 'tags' parameters are required"
                )]
            title = arguments.get("title")
            content_hash = arguments.get("content_hash")
            return await store_bookmark_metadata_tool(url, summary, tags, title, content_hash)
        
        elif name == "get_bookmark_metadata":
            url = arguments.get("url", "")
            if not url:
                return [TextContent(
                    type="text",
                    text="Error: 'url' parameter is required"
                )]
            return await get_bookmark_metadata_tool(url)
        
        elif name == "search_by_tags":
            tags = arguments.get("tags", [])
            if not tags:
                return [TextContent(
                    type="text",
                    text="Error: 'tags' parameter is required"
                )]
            limit = arguments.get("limit", 10)
            return await search_by_tags_tool(tags, limit)
        
        # Write operations
        elif name == "move_bookmark":
            url = arguments.get("url", "")
            target_folder = arguments.get("target_folder", "")
            if not url or not target_folder:
                return [TextContent(
                    type="text",
                    text="Error: 'url' and 'target_folder' parameters are required"
                )]
            return await move_bookmark_tool(url, target_folder)
        
        elif name == "rename_bookmark":
            url = arguments.get("url", "")
            new_title = arguments.get("new_title", "")
            if not url or not new_title:
                return [TextContent(
                    type="text",
                    text="Error: 'url' and 'new_title' parameters are required"
                )]
            return await rename_bookmark_tool(url, new_title)
        
        elif name == "delete_bookmark":
            url = arguments.get("url", "")
            if not url:
                return [TextContent(
                    type="text",
                    text="Error: 'url' parameter is required"
                )]
            return await delete_bookmark_tool(url)
        
        elif name == "create_folder":
            folder_name = arguments.get("folder_name", "")
            parent_folder = arguments.get("parent_folder", "")
            if not folder_name or not parent_folder:
                return [TextContent(
                    type="text",
                    text="Error: 'folder_name' and 'parent_folder' parameters are required"
                )]
            return await create_folder_tool(folder_name, parent_folder)
        
        elif name == "get_folder_structure":
            return await get_folder_structure_tool()
        
        elif name == "bulk_reorganize":
            moves = arguments.get("moves", [])
            if not moves:
                return [TextContent(
                    type="text",
                    text="Error: 'moves' parameter is required"
                )]
            return await bulk_reorganize_tool(moves)
        
        else:
            raise ValueError(f"Unknown tool: {name}")
    
    return server


async def main():
    """Main entry point for the MCP server."""
    server = create_server()
    
    async with stdio_server() as (read_stream, write_stream):
        initialization_options = server.create_initialization_options()
        await server.run(read_stream, write_stream, initialization_options)


