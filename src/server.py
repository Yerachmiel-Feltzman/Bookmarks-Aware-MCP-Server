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
    add_bookmark,
)
from src.search import KeywordSearchEngine, SearchEngine
from src.metadata_store import get_metadata_store
from src.enrichment import fetch_page_content, compute_content_hash
from src.change_tracker import get_change_tracker
from src.config import get_config


# Global state
_bookmarks_cache: Optional[list] = None
_search_engine: SearchEngine = KeywordSearchEngine()
_metadata_cache: Optional[Dict[str, Dict[str, Any]]] = None


def _get_bookmarks_path() -> Path:
    """Get bookmarks path using configured Chrome profile."""
    config = get_config()
    return get_chrome_bookmarks_path(profile=config.chrome_profile)


def load_bookmarks(bookmarks_path: Optional[Path] = None) -> list:
    """Load bookmarks, using cache if available."""
    global _bookmarks_cache

    if _bookmarks_cache is None:
        if bookmarks_path is None:
            bookmarks_path = _get_bookmarks_path()
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
    """Load all metadata from the store, keyed by URL."""
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


def invalidate_bookmarks_cache() -> None:
    """Invalidate the bookmarks cache (call after modifications)."""
    global _bookmarks_cache
    _bookmarks_cache = None


# ============================================================================
# Tool Handlers
# ============================================================================

async def health_check_tool() -> list[TextContent]:
    """Diagnostic health check for the MCP server."""
    report = {}

    # Chrome bookmarks
    config = get_config()
    bookmarks_path = _get_bookmarks_path()
    report["chrome_profile"] = config.chrome_profile
    report["bookmarks_path"] = str(bookmarks_path)
    report["bookmarks_file_exists"] = bookmarks_path.exists()

    bookmark_count = 0
    if bookmarks_path.exists():
        try:
            bookmarks = read_chrome_bookmarks(bookmarks_path)
            bookmark_count = len(bookmarks)
            report["bookmarks_readable"] = True
            report["bookmark_count"] = bookmark_count
        except Exception as e:
            report["bookmarks_readable"] = False
            report["bookmarks_error"] = str(e)
    else:
        report["bookmarks_readable"] = False

    # Metadata DB
    try:
        store = await get_metadata_store()
        all_meta = await store.get_all_metadata()
        enriched_count = len(all_meta)
        report["metadata_db_path"] = str(store.db_path)
        report["metadata_db_initialized"] = True
        report["enriched_bookmarks"] = enriched_count
        report["unenriched_bookmarks"] = max(0, bookmark_count - enriched_count)
    except Exception as e:
        report["metadata_db_initialized"] = False
        report["metadata_error"] = str(e)

    # Change tracker
    try:
        tracker = await get_change_tracker()
        history = await tracker.get_history(limit=1)
        report["change_tracker_initialized"] = True
        report["changes_recorded"] = len(history) > 0
    except Exception as e:
        report["change_tracker_initialized"] = False
        report["change_tracker_error"] = str(e)

    # Overall status
    issues = []
    if not report.get("bookmarks_file_exists"):
        issues.append(f"Chrome bookmarks file not found at {bookmarks_path}. Set BOOKMARKS_CHROME_PROFILE env var if using a non-default profile.")
    if not report.get("bookmarks_readable"):
        issues.append("Cannot read bookmarks file.")
    if report.get("unenriched_bookmarks", 0) > 0:
        issues.append(f"{report['unenriched_bookmarks']} bookmarks have no metadata. Use fetch_page_content + store_bookmark_metadata to enrich them.")

    report["status"] = "healthy" if not issues else "issues_found"
    report["issues"] = issues

    return [TextContent(type="text", text=json.dumps(report, indent=2))]


async def list_bookmarks_tool(folder: Optional[str] = None) -> list[TextContent]:
    """List all bookmarks, optionally filtered by folder."""
    bookmarks = load_bookmarks()

    if not bookmarks:
        return [TextContent(type="text", text="No bookmarks available.")]

    if folder:
        bookmarks = [b for b in bookmarks if b.get("folder", "").startswith(folder)]

    metadata = await load_metadata()

    results = []
    for b in bookmarks:
        entry = {
            "url": b["url"],
            "title": b["title"],
            "folder": b["folder"],
        }
        meta = metadata.get(b["url"])
        if meta:
            entry["summary"] = meta.get("summary", "")
            entry["tags"] = meta.get("tags", [])
        results.append(entry)

    return [TextContent(type="text", text=json.dumps(results, indent=2))]


async def get_bookmarks_tool(
    query: str,
    tags: Optional[List[str]] = None,
) -> list[TextContent]:
    """Tool handler for get_bookmarks."""
    bookmarks = load_bookmarks()

    if not bookmarks:
        return [TextContent(
            type="text",
            text="No bookmarks available. Run health_check to diagnose."
        )]

    metadata = await load_metadata()
    results = _search_engine.search(
        query, bookmarks, limit=10, tags_filter=tags, metadata=metadata,
    )

    if not results:
        msg = f"No bookmarks found matching query: {query}"
        if tags:
            msg += f" with tags: {tags}"
        return [TextContent(type="text", text=msg)]

    return [TextContent(type="text", text=json.dumps(results, indent=2))]


async def fetch_page_content_tool(url: str) -> list[TextContent]:
    """Fetch a URL and return extracted text content."""
    try:
        content = await fetch_page_content(url)
        if not content:
            return [TextContent(type="text", text=f"Could not fetch or extract content from: {url}")]

        content_hash = compute_content_hash(content)
        result = {"url": url, "content": content, "content_hash": content_hash}
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    except Exception as e:
        return [TextContent(type="text", text=f"Error fetching page content: {e}")]


async def store_bookmark_metadata_tool(
    url: str,
    summary: str,
    tags: List[str],
    title: Optional[str] = None,
    content_hash: Optional[str] = None,
) -> list[TextContent]:
    """Store agent-generated summary and tags for a bookmark."""
    try:
        store = await get_metadata_store()
        await store.upsert_metadata(
            url=url, title=title, summary=summary, tags=tags, content_hash=content_hash,
        )
        invalidate_metadata_cache()
        return [TextContent(type="text", text=json.dumps({
            "status": "stored", "url": url, "summary": summary, "tags": tags,
        }, indent=2))]
    except Exception as e:
        return [TextContent(type="text", text=f"Error storing metadata: {e}")]


async def get_bookmark_metadata_tool(url: str) -> list[TextContent]:
    """Get stored metadata for a bookmark URL."""
    try:
        store = await get_metadata_store()
        metadata = await store.get_metadata(url)
        if not metadata:
            return [TextContent(
                type="text",
                text=f"No metadata found for: {url}. Use fetch_page_content to get the page text, then store_bookmark_metadata to save your analysis."
            )]
        return [TextContent(type="text", text=json.dumps(metadata, indent=2, default=str))]
    except Exception as e:
        return [TextContent(type="text", text=f"Error getting metadata: {e}")]


async def search_by_tags_tool(tags: List[str], limit: int = 10) -> list[TextContent]:
    """Find bookmarks by tags."""
    try:
        store = await get_metadata_store()
        results = await store.search_by_tags(tags, limit=limit)
        if not results:
            return [TextContent(type="text", text=f"No bookmarks found with tags: {tags}")]
        return [TextContent(type="text", text=json.dumps(results, indent=2, default=str))]
    except Exception as e:
        return [TextContent(type="text", text=f"Error searching by tags: {e}")]


# ============================================================================
# Write Operations (with change tracking)
# ============================================================================

async def add_bookmark_tool(url: str, title: str, folder: str) -> list[TextContent]:
    """Add a new bookmark."""
    try:
        success = add_bookmark(url, title, folder)
        invalidate_bookmarks_cache()

        if success:
            tracker = await get_change_tracker()
            await tracker.record_change("add", url, {
                "title": title,
                "folder": folder,
            })
            return [TextContent(type="text", text=json.dumps({
                "status": "added", "url": url, "title": title, "folder": folder,
            }, indent=2))]
        else:
            return [TextContent(type="text", text=f"Failed to add bookmark. Check that the folder '{folder}' exists. Use get_folder_structure to see available folders, or create_folder to make one.")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error adding bookmark: {e}")]


async def move_bookmark_tool(url: str, target_folder: str) -> list[TextContent]:
    """Move a bookmark to a different folder."""
    try:
        # Capture before state for undo
        bookmarks = load_bookmarks()
        bookmark = next((b for b in bookmarks if b["url"] == url), None)
        original_folder = bookmark["folder"] if bookmark else None

        success = move_bookmark(url, target_folder)
        invalidate_bookmarks_cache()

        if success:
            tracker = await get_change_tracker()
            await tracker.record_change("move", url, {
                "from_folder": original_folder,
                "to_folder": target_folder,
            })
            return [TextContent(type="text", text=f"Successfully moved bookmark to {target_folder}")]
        else:
            return [TextContent(type="text", text="Failed to move bookmark. Check that the URL and folder exist.")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error moving bookmark: {e}")]


async def rename_bookmark_tool(url: str, new_title: str) -> list[TextContent]:
    """Rename a bookmark."""
    try:
        bookmarks = load_bookmarks()
        bookmark = next((b for b in bookmarks if b["url"] == url), None)
        original_title = bookmark["title"] if bookmark else None

        success = rename_bookmark(url, new_title)
        invalidate_bookmarks_cache()

        if success:
            tracker = await get_change_tracker()
            await tracker.record_change("rename", url, {
                "old_title": original_title,
                "new_title": new_title,
            })
            return [TextContent(type="text", text=f"Successfully renamed bookmark to '{new_title}'")]
        else:
            return [TextContent(type="text", text="Failed to rename bookmark. Check that the URL exists.")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error renaming bookmark: {e}")]


async def delete_bookmark_tool(url: str) -> list[TextContent]:
    """Delete a bookmark."""
    try:
        bookmarks = load_bookmarks()
        bookmark = next((b for b in bookmarks if b["url"] == url), None)
        original_title = bookmark["title"] if bookmark else None
        original_folder = bookmark["folder"] if bookmark else None

        success = delete_bookmark(url)
        invalidate_bookmarks_cache()

        if success:
            tracker = await get_change_tracker()
            await tracker.record_change("delete", url, {
                "title": original_title,
                "folder": original_folder,
            })
            return [TextContent(type="text", text="Successfully deleted bookmark")]
        else:
            return [TextContent(type="text", text="Failed to delete bookmark. Check that the URL exists.")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error deleting bookmark: {e}")]


async def create_folder_tool(folder_name: str, parent_folder: str) -> list[TextContent]:
    """Create a new bookmark folder."""
    try:
        success = create_folder(folder_name, parent_folder)
        invalidate_bookmarks_cache()

        if success:
            tracker = await get_change_tracker()
            await tracker.record_change("create_folder", None, {
                "folder_name": folder_name,
                "parent_folder": parent_folder,
                "full_path": f"{parent_folder}/{folder_name}",
            })
            return [TextContent(type="text", text=f"Successfully created folder '{folder_name}' in {parent_folder}")]
        else:
            return [TextContent(type="text", text="Failed to create folder. Check that the parent folder exists.")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error creating folder: {e}")]


async def get_folder_structure_tool() -> list[TextContent]:
    """Get current folder structure."""
    try:
        structure = get_folder_structure()
        return [TextContent(type="text", text=json.dumps(structure, indent=2))]
    except Exception as e:
        return [TextContent(type="text", text=f"Error getting folder structure: {e}")]


async def bulk_reorganize_tool(moves: List[Dict[str, str]]) -> list[TextContent]:
    """Bulk-move bookmarks."""
    try:
        # Capture before state for undo
        bookmarks = load_bookmarks()
        before_state = []
        for move in moves:
            bm = next((b for b in bookmarks if b["url"] == move.get("url")), None)
            if bm:
                before_state.append({
                    "url": bm["url"],
                    "original_folder": bm["folder"],
                    "target_folder": move.get("target_folder"),
                })

        success_count = bulk_move_bookmarks(moves)
        invalidate_bookmarks_cache()

        if success_count > 0:
            tracker = await get_change_tracker()
            await tracker.record_change("bulk_move", None, {
                "moves": before_state,
                "success_count": success_count,
                "total_requested": len(moves),
            })

        return [TextContent(type="text", text=f"Successfully moved {success_count}/{len(moves)} bookmarks")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error bulk reorganizing bookmarks: {e}")]


# ============================================================================
# Change History and Revert
# ============================================================================

async def get_change_history_tool(limit: int = 20) -> list[TextContent]:
    """Get recent change history."""
    try:
        tracker = await get_change_tracker()
        history = await tracker.get_history(limit=limit)

        if not history:
            return [TextContent(type="text", text="No changes recorded yet.")]

        return [TextContent(type="text", text=json.dumps(history, indent=2, default=str))]
    except Exception as e:
        return [TextContent(type="text", text=f"Error getting change history: {e}")]


async def revert_last_change_tool() -> list[TextContent]:
    """Revert the most recent non-reverted change."""
    try:
        tracker = await get_change_tracker()
        change = await tracker.get_last_revertable()

        if not change:
            return [TextContent(type="text", text="Nothing to revert. All changes have already been reverted or no changes exist.")]

        action = change["action"]
        details = change["details"]
        url = change.get("url")
        success = False

        if action == "move":
            original_folder = details.get("from_folder")
            if url and original_folder:
                success = move_bookmark(url, original_folder)
                invalidate_bookmarks_cache()

        elif action == "rename":
            old_title = details.get("old_title")
            if url and old_title:
                success = rename_bookmark(url, old_title)
                invalidate_bookmarks_cache()

        elif action == "delete":
            title = details.get("title", "Untitled")
            folder = details.get("folder", "bookmark_bar")
            if url:
                success = add_bookmark(url, title, folder)
                invalidate_bookmarks_cache()

        elif action == "add":
            if url:
                success = delete_bookmark(url)
                invalidate_bookmarks_cache()

        elif action == "create_folder":
            # Cannot easily delete a folder via the current API.
            # Mark as reverted but warn.
            await tracker.mark_reverted(change["id"])
            return [TextContent(type="text", text=json.dumps({
                "status": "skipped",
                "reason": "Folder creation cannot be automatically undone. Delete the folder manually if needed.",
                "change": change,
            }, indent=2, default=str))]

        elif action == "bulk_move":
            moves_data = details.get("moves", [])
            revert_moves = [
                {"url": m["url"], "target_folder": m["original_folder"]}
                for m in moves_data
                if m.get("url") and m.get("original_folder")
            ]
            if revert_moves:
                count = bulk_move_bookmarks(revert_moves)
                success = count > 0
                invalidate_bookmarks_cache()

        if success:
            await tracker.mark_reverted(change["id"])
            return [TextContent(type="text", text=json.dumps({
                "status": "reverted",
                "action": action,
                "details": details,
            }, indent=2, default=str))]
        else:
            return [TextContent(type="text", text=json.dumps({
                "status": "failed",
                "action": action,
                "reason": "Could not apply the inverse operation. The bookmark or folder may no longer exist.",
                "details": details,
            }, indent=2, default=str))]

    except Exception as e:
        return [TextContent(type="text", text=f"Error reverting change: {e}")]


# ============================================================================
# Server Definition
# ============================================================================

def create_server() -> Server:
    """Create and configure the MCP server."""
    server = Server("bookmarks-aware-mcp")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            # --- Diagnostics ---
            Tool(
                name="health_check",
                description=(
                    "Run a diagnostic health check on the bookmarks MCP server. "
                    "Returns: Chrome profile and bookmarks file status, bookmark count, "
                    "metadata DB status, enrichment coverage, and any issues found. "
                    "Run this after first setup to verify everything works, or any time something seems wrong."
                ),
                inputSchema={"type": "object", "properties": {}},
            ),
            # --- Read / Search ---
            Tool(
                name="list_bookmarks",
                description=(
                    "List ALL bookmarks, optionally filtered by folder path. "
                    "Returns every bookmark with URL, title, folder, and metadata (if enriched). "
                    "Use get_folder_structure first to understand the layout, then list_bookmarks to see contents. "
                    "For reorganization: analyze the list, create_folder for new structure, then bulk_reorganize to move."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "folder": {
                            "type": "string",
                            "description": "Optional folder path to filter by (e.g., 'bookmark_bar/Work'). Omit to list all.",
                        },
                    },
                },
            ),
            Tool(
                name="get_bookmarks",
                description=(
                    "Search bookmarks by keyword. Searches across URL, title, description, summary, and tags. "
                    "Results include metadata (summaries/tags) if the bookmark has been enriched. "
                    "If a result looks relevant but has no summary, call fetch_page_content to get the page text, "
                    "then generate a summary and tags yourself, and store them with store_bookmark_metadata for next time."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query to find relevant bookmarks",
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional list of tags to filter by (AND logic)",
                        },
                    },
                    "required": ["query"],
                },
            ),
            # --- Enrichment ---
            Tool(
                name="fetch_page_content",
                description=(
                    "Fetch a URL and extract its text content for enrichment. "
                    "After calling this, analyze the content to generate a 2-3 sentence summary and 3-5 tags, "
                    "then call store_bookmark_metadata to save them. This makes future searches much better."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "URL to fetch and extract content from"},
                    },
                    "required": ["url"],
                },
            ),
            Tool(
                name="store_bookmark_metadata",
                description=(
                    "Store a summary and tags for a bookmark. Call this after fetching page content "
                    "and generating your own summary and tags."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "Bookmark URL to store metadata for"},
                        "summary": {"type": "string", "description": "A concise 2-3 sentence summary of the page"},
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "3-5 relevant tags/categories for the bookmark",
                        },
                        "title": {"type": "string", "description": "Optional title override"},
                        "content_hash": {"type": "string", "description": "Content hash from fetch_page_content (for change detection)"},
                    },
                    "required": ["url", "summary", "tags"],
                },
            ),
            Tool(
                name="get_bookmark_metadata",
                description="Get the stored metadata (summary, tags) for a specific bookmark URL.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "URL of the bookmark"},
                    },
                    "required": ["url"],
                },
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
                            "description": "List of tags to search for",
                        },
                        "limit": {"type": "integer", "description": "Maximum number of results", "default": 10},
                    },
                    "required": ["tags"],
                },
            ),
            # --- Write Operations ---
            Tool(
                name="add_bookmark",
                description=(
                    "Add a new bookmark to Chrome. "
                    "Use get_folder_structure to find the right folder, or create_folder to make one first. "
                    "After adding, consider enriching with fetch_page_content + store_bookmark_metadata. "
                    "All changes are tracked and can be undone with revert_last_change."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "URL of the new bookmark"},
                        "title": {"type": "string", "description": "Title/name for the bookmark"},
                        "folder": {"type": "string", "description": "Target folder path (e.g., 'bookmark_bar/Dev/Python')"},
                    },
                    "required": ["url", "title", "folder"],
                },
            ),
            Tool(
                name="move_bookmark",
                description=(
                    "Move a bookmark to a different folder. "
                    "Creates a backup and records the change for undo support."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "URL of the bookmark to move"},
                        "target_folder": {"type": "string", "description": "Target folder path (e.g., 'bookmark_bar/Work')"},
                    },
                    "required": ["url", "target_folder"],
                },
            ),
            Tool(
                name="rename_bookmark",
                description="Rename a bookmark's title. Creates a backup and records the change for undo support.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "URL of the bookmark to rename"},
                        "new_title": {"type": "string", "description": "New title for the bookmark"},
                    },
                    "required": ["url", "new_title"],
                },
            ),
            Tool(
                name="delete_bookmark",
                description=(
                    "Delete a bookmark. Creates a backup and records the change for undo support. "
                    "The bookmark can be restored with revert_last_change."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "URL of the bookmark to delete"},
                    },
                    "required": ["url"],
                },
            ),
            Tool(
                name="create_folder",
                description="Create a new bookmark folder inside a parent folder.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "folder_name": {"type": "string", "description": "Name of the new folder"},
                        "parent_folder": {"type": "string", "description": "Path to parent folder (e.g., 'bookmark_bar')"},
                    },
                    "required": ["folder_name", "parent_folder"],
                },
            ),
            Tool(
                name="get_folder_structure",
                description=(
                    "Get the current folder structure of bookmarks with bookmark and subfolder counts. "
                    "Use this to understand the layout before reorganizing or adding bookmarks."
                ),
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="bulk_reorganize",
                description=(
                    "Move multiple bookmarks at once. Useful for batch reorganization. "
                    "Creates a backup and records all moves for undo support. "
                    "Use list_bookmarks + get_folder_structure to plan the moves first."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "moves": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "url": {"type": "string"},
                                    "target_folder": {"type": "string"},
                                },
                                "required": ["url", "target_folder"],
                            },
                            "description": "List of moves, each with 'url' and 'target_folder'",
                        },
                    },
                    "required": ["moves"],
                },
            ),
            # --- History / Undo ---
            Tool(
                name="get_change_history",
                description=(
                    "View recent bookmark changes (moves, renames, deletes, adds). "
                    "Each entry shows the action, timestamp, and before/after state. "
                    "Use this to review what happened before deciding to revert."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Max number of changes to return (default 20)", "default": 20},
                    },
                },
            ),
            Tool(
                name="revert_last_change",
                description=(
                    "Undo the most recent bookmark change. Applies the inverse operation "
                    "(e.g., moves a bookmark back to its original folder, restores a deleted bookmark). "
                    "Call get_change_history first to see what will be reverted."
                ),
                inputSchema={"type": "object", "properties": {}},
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: Any) -> list[TextContent]:
        """Handle tool calls."""

        # Diagnostics
        if name == "health_check":
            return await health_check_tool()

        # Read / Search
        elif name == "list_bookmarks":
            folder = arguments.get("folder")
            return await list_bookmarks_tool(folder)

        elif name == "get_bookmarks":
            query = arguments.get("query", "")
            tags = arguments.get("tags")
            if not query and not tags:
                return [TextContent(type="text", text="Error: 'query' or 'tags' parameter is required")]
            return await get_bookmarks_tool(query, tags)

        # Enrichment
        elif name == "fetch_page_content":
            url = arguments.get("url", "")
            if not url:
                return [TextContent(type="text", text="Error: 'url' parameter is required")]
            return await fetch_page_content_tool(url)

        elif name == "store_bookmark_metadata":
            url = arguments.get("url", "")
            summary = arguments.get("summary", "")
            tags = arguments.get("tags", [])
            if not url or not summary:
                return [TextContent(type="text", text="Error: 'url', 'summary', and 'tags' parameters are required")]
            title = arguments.get("title")
            content_hash = arguments.get("content_hash")
            return await store_bookmark_metadata_tool(url, summary, tags, title, content_hash)

        elif name == "get_bookmark_metadata":
            url = arguments.get("url", "")
            if not url:
                return [TextContent(type="text", text="Error: 'url' parameter is required")]
            return await get_bookmark_metadata_tool(url)

        elif name == "search_by_tags":
            tags = arguments.get("tags", [])
            if not tags:
                return [TextContent(type="text", text="Error: 'tags' parameter is required")]
            limit = arguments.get("limit", 10)
            return await search_by_tags_tool(tags, limit)

        # Write operations
        elif name == "add_bookmark":
            url = arguments.get("url", "")
            title = arguments.get("title", "")
            folder = arguments.get("folder", "")
            if not url or not title or not folder:
                return [TextContent(type="text", text="Error: 'url', 'title', and 'folder' parameters are required")]
            return await add_bookmark_tool(url, title, folder)

        elif name == "move_bookmark":
            url = arguments.get("url", "")
            target_folder = arguments.get("target_folder", "")
            if not url or not target_folder:
                return [TextContent(type="text", text="Error: 'url' and 'target_folder' parameters are required")]
            return await move_bookmark_tool(url, target_folder)

        elif name == "rename_bookmark":
            url = arguments.get("url", "")
            new_title = arguments.get("new_title", "")
            if not url or not new_title:
                return [TextContent(type="text", text="Error: 'url' and 'new_title' parameters are required")]
            return await rename_bookmark_tool(url, new_title)

        elif name == "delete_bookmark":
            url = arguments.get("url", "")
            if not url:
                return [TextContent(type="text", text="Error: 'url' parameter is required")]
            return await delete_bookmark_tool(url)

        elif name == "create_folder":
            folder_name = arguments.get("folder_name", "")
            parent_folder = arguments.get("parent_folder", "")
            if not folder_name or not parent_folder:
                return [TextContent(type="text", text="Error: 'folder_name' and 'parent_folder' parameters are required")]
            return await create_folder_tool(folder_name, parent_folder)

        elif name == "get_folder_structure":
            return await get_folder_structure_tool()

        elif name == "bulk_reorganize":
            moves = arguments.get("moves", [])
            if not moves:
                return [TextContent(type="text", text="Error: 'moves' parameter is required")]
            return await bulk_reorganize_tool(moves)

        # History / Undo
        elif name == "get_change_history":
            limit = arguments.get("limit", 20)
            return await get_change_history_tool(limit)

        elif name == "revert_last_change":
            return await revert_last_change_tool()

        else:
            raise ValueError(f"Unknown tool: {name}")

    return server


async def main():
    """Main entry point for the MCP server."""
    server = create_server()

    async with stdio_server() as (read_stream, write_stream):
        initialization_options = server.create_initialization_options()
        await server.run(read_stream, write_stream, initialization_options)
