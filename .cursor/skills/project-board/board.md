# Project Board

## Done

### Core Features
- Core Chrome bookmarks reader with cross-platform support (macOS/Windows/Linux/Chromium)
- Keyword-based search engine with token matching and scoring
- MCP server with `get_bookmarks` tool
- Global bookmark caching for performance
- Graceful error handling for missing/malformed files
- README with installation, usage, and architecture diagrams
- Makefile with setup and run targets

### Metadata & Enrichment (Agent-Driven)
- SQLite metadata store (`~/.bookmarks-mcp/metadata.db`) for summaries and tags
- `fetch_page_content` tool - fetches URL and extracts text via httpx + trafilatura
- `store_bookmark_metadata` tool - stores agent-generated summary + tags
- `get_bookmark_metadata` and `search_by_tags` tools
- Enhanced search across summaries and tags with tag filtering
- Agent-driven enrichment: no LLM in the server, the calling agent does summarization
- Configuration system for enrichment settings (rate limits, timeouts)

### Write Capabilities
- `move_bookmark` - Move bookmarks between folders
- `rename_bookmark` - Rename bookmark titles
- `delete_bookmark` - Delete bookmarks
- `create_folder` - Create new bookmark folders
- `get_folder_structure` - View folder hierarchy with counts
- `bulk_reorganize` - Batch move multiple bookmarks
- Automatic backup before any write operation

### Testing & Quality
- Unit test suite with pytest (85 tests): bookmarks_store, metadata_store, search, enrichment, config, change_tracker, add_bookmark, server_tools, enrich_all
- `make test` command
- Bug fix: folder path consistency (root key prefix instead of display name)

### User Flows (v2)
- `health_check` tool -- diagnostic report: Chrome file, bookmark count, DB status, enrichment coverage
- `list_bookmarks` tool -- list ALL bookmarks with optional folder filter (enables browsing/reorganization)
- `add_bookmark` tool -- add new bookmarks to Chrome's bookmarks file
- `BOOKMARKS_CHROME_PROFILE` env var -- support non-default Chrome profiles
- Change tracking in SQLite (`bookmark_changes` table) -- every write records before/after state
- `get_change_history` tool -- view recent changes with timestamps and details
- `revert_last_change` tool -- undo the most recent change (move back, un-rename, restore deleted)
- Improved tool descriptions guiding agents through multi-step flows (enrichment, reorganization)
- `enrich_all` tool -- batch-fetch unenriched bookmarks for agent summarization (configurable batch_size)
- `add_bookmark` auto-fetches page content for immediate enrichment
- Mandatory enrichment: tool descriptions use MUST language; health_check directs to enrich_all

## In Progress

(none)

## Todo

(none)

## Backlog

### Search Enhancements
- [backlog] P1: Semantic search - Add embedding-based search for intelligent matching
- [backlog] P2: Advanced ranking - Implement TF-IDF or BM25 for better relevance scoring

### Feature Enhancements
- [done] P1: Multiple Chrome profiles - Supported via BOOKMARKS_CHROME_PROFILE env var
- [backlog] P2: Multi-browser support - Add Firefox, Safari, Edge bookmark reading
- [backlog] P2: Chrome extension - Real-time bookmark sync, context capture, quick search UI

### Infrastructure
- [backlog] P1: Remote sync - Cross-machine metadata sync (options: Dropbox/iCloud file sync, Turso, CRDTs)

### Developer Experience
- [backlog] P1: Linting and formatting - Set up ruff for consistent code style
- [backlog] P2: CI/CD pipeline - GitHub Actions for tests, lint, and releases
