---
name: project-spec
description: Project specification for Bookmarks-Aware MCP Server. Use when starting work, adding features, or needing context about the architecture, tech stack, modules, or coding conventions.
---

# Bookmarks-Aware MCP Server - Project Specification

## Project Identity

A Python MCP (Model Context Protocol) server that provides full access to Chrome bookmarks with search, enrichment, and organization capabilities. Enables LLMs to search, enrich with AI metadata, and reorganize bookmarks via natural language.

## Tech Stack

- **Python 3.11** (see `.python-version`)
- **mcp SDK** (`mcp>=0.1.0`) - Model Context Protocol implementation
- **aiosqlite** - Async SQLite for metadata storage
- **httpx** - Async HTTP client for page fetching
- **trafilatura** - Content extraction from HTML
- **Transport**: stdio-based MCP protocol
- **Build**: Makefile (`make setup`, `make run`)

No LLM dependencies -- enrichment is agent-driven (see Enrichment Architecture below).

## Module Map

```
src/
├── main.py            # Entry point - runs asyncio.run(main())
├── server.py          # MCP server, 16 tool definitions, caches
├── bookmarks_store.py # Chrome bookmarks read/write/add (cross-platform)
├── search.py          # Search engine with metadata support
├── metadata_store.py  # SQLite store for summaries and tags
├── change_tracker.py  # Change history + undo (bookmark_changes table in same DB)
├── enrichment.py      # Page fetching + content extraction (no LLM)
├── config.py          # Configuration (enrichment settings, Chrome profile)
└── bookmarks_reader.py # (legacy, kept for compatibility)
```

### `src/bookmarks_store.py`
- `get_chrome_bookmarks_path(profile)` - Platform-specific path
- `read_chrome_bookmarks(path)` - Returns bookmarks with `id`, `url`, `title`, `folder`
- `add_bookmark(url, title, folder_path)` - Add new bookmark
- `move_bookmark(url, target_folder)` - Move bookmark to folder
- `rename_bookmark(url, new_title)` - Rename bookmark
- `delete_bookmark(url)` - Delete bookmark
- `create_folder(name, parent)` - Create folder
- `bulk_move_bookmarks(moves)` - Batch reorganization
- `backup_bookmarks()` - Creates `.bak` before writes

### `src/metadata_store.py`
- `MetadataStore` - Async SQLite wrapper for `~/.bookmarks-mcp/metadata.db`
- `get_metadata(url)` / `upsert_metadata(...)` - CRUD operations
- `search_by_tags(tags)` - Find bookmarks by tags
- `get_urls_needing_enrichment(urls)` - Find stale/missing metadata

### `src/enrichment.py`
- `fetch_page_content(url)` - HTTP fetch + trafilatura text extraction
- `compute_content_hash(content)` - SHA256 hash for change detection

### `src/change_tracker.py`
- `ChangeTracker` - Tracks bookmark changes in `bookmark_changes` SQLite table
- `record_change(action, url, details)` - Record a change with before/after state
- `get_history(limit)` - Get recent changes (newest first)
- `get_last_revertable()` - Get most recent non-reverted change
- `mark_reverted(change_id)` - Mark a change as undone

### `src/config.py`
- `EnrichmentConfig` - Rate limits, timeouts, content length limits
- `Config.from_env()` - Load from environment variables (incl. `BOOKMARKS_CHROME_PROFILE`)

### `src/search.py`
- `SearchEngine` (Protocol) - Interface with metadata support
- `KeywordSearchEngine.search(query, bookmarks, tags_filter, metadata)` - Enhanced search

## Enrichment Architecture

Enrichment uses an **agent-driven** pattern: the MCP server handles fetching/storage,
while the calling agent (the LLM) does the intelligence work.

```
Agent calls fetch_page_content(url)
  -> MCP fetches page, extracts text, returns content to agent
Agent reads content, generates summary + tags using its own model
Agent calls store_bookmark_metadata(url, summary, tags)
  -> MCP stores metadata in SQLite
```

This means:
- No LLM dependencies in the server
- Uses whatever model the agent is already running on
- No API keys or local model setup needed
- Better quality (frontier model vs local 3B)

## Current Tools (16)

| Tool | Description |
|------|-------------|
| `health_check` | Diagnostic: Chrome file, bookmark count, DB status, issues |
| `list_bookmarks` | List ALL bookmarks (optional folder filter) |
| `get_bookmarks` | Search bookmarks with metadata, optional tag filtering |
| `fetch_page_content` | Fetch URL and extract text (agent then summarizes) |
| `store_bookmark_metadata` | Store agent-generated summary + tags |
| `get_bookmark_metadata` | Get stored summary/tags for a URL |
| `search_by_tags` | Find bookmarks by tag |
| `add_bookmark` | Add new bookmark to a folder |
| `move_bookmark` | Move bookmark to different folder |
| `rename_bookmark` | Rename a bookmark |
| `delete_bookmark` | Delete a bookmark |
| `create_folder` | Create new folder |
| `get_folder_structure` | View folder hierarchy |
| `bulk_reorganize` | Batch move multiple bookmarks |
| `get_change_history` | View recent changes with before/after state |
| `revert_last_change` | Undo the most recent non-reverted change |

## Design Decisions

1. **Agent-driven enrichment**: No LLM in the server; the calling agent does summarization
2. **Read and Write**: Full bookmark management (with automatic backups)
3. **Change tracking with undo**: Every write records before/after state; any change is revertable
4. **Extensible search**: `SearchEngine` protocol for swappable implementations
5. **Local-first metadata**: SQLite at `~/.bookmarks-mcp/metadata.db`
6. **Configurable Chrome profile**: `BOOKMARKS_CHROME_PROFILE` env var
7. **Graceful errors**: Missing files return safe defaults with warnings
8. **Cross-platform**: Handles Windows, macOS, Linux, and Chromium paths
9. **Rate limiting**: Configurable limits for page fetching

For full reasoning, tradeoffs, and rejected alternatives, see [decisions.md](decisions.md).

## Coding Conventions

- **Type hints**: Always use type annotations
- **Docstrings**: Google-style docstrings on all public functions
- **Protocol-based interfaces**: Use `typing.Protocol` for swappable components
- **No external LLM APIs**: Intelligence comes from the calling agent
- **Error handling**: Catch specific exceptions, log to stderr, return safe defaults

## Adding a New Tool

1. Define the tool handler in `server.py`:
   ```python
   async def my_tool(arg: str) -> list[TextContent]:
       # implementation
       return [TextContent(type="text", text=result)]
   ```

2. Register in `list_tools()`:
   ```python
   Tool(
       name="my_tool",
       description="...",
       inputSchema={"type": "object", "properties": {...}, "required": [...]}
   )
   ```

3. Add case in `call_tool()`:
   ```python
   if name == "my_tool":
       return await my_tool(arguments.get("arg"))
   ```

## Adding a New Search Implementation

1. Create a class implementing the `SearchEngine` protocol:
   ```python
   class SemanticSearchEngine:
       def search(self, query: str, bookmarks: List[Dict[str, str]], limit: int = 10) -> List[Dict[str, str]]:
           # implementation
   ```

2. Replace the global `_search_engine` in `server.py`:
   ```python
   _search_engine: SearchEngine = SemanticSearchEngine()
   ```

## Running the Server

```bash
make setup  # Install dependencies
make run    # Run the server
```

Or directly:
```bash
python src/main.py
```

## Configuration

### MCP Client Configuration

Configure in MCP client (e.g., `~/.cursor/mcp.json`):
```json
{
  "mcpServers": {
    "bookmarks-aware-mcp": {
      "command": "python3",
      "args": ["/absolute/path/to/src/main.py"]
    }
  }
}
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BOOKMARKS_RATE_LIMIT` | `2.0` | Requests per second for page fetching |
| `BOOKMARKS_MAX_CONCURRENT` | `5` | Max concurrent page fetches |
| `BOOKMARKS_MAX_CONTENT` | `50000` | Max chars to extract from a page |
| `BOOKMARKS_TIMEOUT` | `30.0` | HTTP request timeout (seconds) |
| `BOOKMARKS_METADATA_DB` | `~/.bookmarks-mcp/metadata.db` | Custom DB path |
| `BOOKMARKS_CHROME_PROFILE` | `Default` | Chrome profile name (e.g., `Profile 1`) |
