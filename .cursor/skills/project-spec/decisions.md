# Architecture Decisions

This document records key design decisions, the alternatives considered, and why we chose what we chose.

---

## ADR-1: Agent-Driven Enrichment (no server-side LLM)

**Status:** Accepted

**Context:** We need to generate summaries and tags for bookmarked pages. This requires an LLM.

**Options considered:**

| Option | Pros | Cons |
|--------|------|------|
| **Server-side LLM (Ollama)** | Works offline, no API key | Requires local install, 3B model quality is low, heavy RAM usage |
| **Server-side LLM (OpenAI)** | High quality | Requires API key + payment |
| **MCP Sampling** | Uses agent's model, no dependencies | Cursor doesn't support it yet (protocol exists but client doesn't implement) |
| **Agent-driven (chosen)** | Uses agent's model, zero dependencies, best quality | Agent must orchestrate 2 tool calls instead of 1 |

**Decision:** Split enrichment into two tools: `fetch_page_content` (server fetches + extracts text) and `store_bookmark_metadata` (agent sends back summary + tags). The server does the "dumb" work, the agent does the "smart" work.

**Rationale:**
- No LLM dependencies in the server at all
- Uses whatever frontier model the agent is already running (Claude, GPT, etc.)
- No API keys, no local model setup, no RAM overhead
- Better quality than any local model
- When MCP sampling becomes available in Cursor, we can revisit -- but this pattern works today and is arguably better

**Tradeoff:** The agent must make 2 tool calls per bookmark (fetch, then store) instead of 1 fire-and-forget call. For batch enrichment, this means the agent loops. This is acceptable because enrichment is not latency-critical.

---

## ADR-2: Local SQLite for Metadata Storage

**Status:** Accepted (remote sync deferred to backlog)

**Context:** We need to store summaries, tags, and content hashes for bookmarks. The store must persist across server restarts.

**Options considered:**

| Option | Pros | Cons |
|--------|------|------|
| **Sidecar JSON file** | Simple, human-readable | No indexing, slow for large collections, no query support |
| **SQLite (chosen)** | Fast queries, indexes, reliable, no server | Single-machine only |
| **Remote DB (Supabase/Firebase)** | Cross-machine sync | Auth complexity, network dependency, cost |
| **Turso (distributed SQLite)** | SQLite API + remote sync | Service dependency, setup overhead |

**Decision:** Local SQLite at `~/.bookmarks-mcp/metadata.db`.

**Rationale:**
- SQLite handles thousands of bookmarks easily
- Supports indexed tag searches (important for `search_by_tags`)
- No service dependencies or auth to configure
- Foundation for future remote sync: can migrate to Turso or sync the file via Dropbox/iCloud later
- `aiosqlite` provides async access matching the rest of the codebase

**Tradeoff:** Metadata is local to one machine. Acceptable for now. Remote sync is tracked in the backlog as a P1.

**Future path to remote:**
- Simple: Sync SQLite file via Dropbox/iCloud/Syncthing (risk: corruption on concurrent writes)
- Proper: Migrate to Turso (distributed SQLite as a service)
- Advanced: Build sync layer with CRDTs for conflict-free merging

---

## ADR-3: Direct Chrome Bookmarks File Writes

**Status:** Accepted

**Context:** We want the MCP to reorganize bookmarks (move, rename, delete, create folders). Chrome stores bookmarks in a JSON file.

**Options considered:**

| Option | Pros | Cons |
|--------|------|------|
| **Suggest-only (read-only)** | Zero risk to user data | User must manually reorganize in Chrome |
| **Export to new file** | No risk to Chrome data | Bookmarks not actually reorganized |
| **Direct file writes (chosen)** | Changes appear in Chrome immediately | Risk of corrupting bookmarks if done wrong |

**Decision:** Write directly to Chrome's Bookmarks JSON file with safety measures.

**Safety measures implemented:**
- Automatic `.bak` backup before every write operation
- Atomic writes (write to temp file, then rename)
- JSON structure preserved exactly
- Only modify specific nodes, never rewrite the whole structure

**Rationale:**
- Chrome hot-reloads the Bookmarks file, so changes appear immediately
- The JSON structure is well-understood and stable
- Backup + atomic write makes corruption extremely unlikely
- The whole point is to actually reorganize bookmarks, not just suggest

**Tradeoff:** If something goes wrong, the user's bookmarks could be corrupted. Mitigated by automatic backups (`.bak` file always exists before any write).

---

## ADR-4: Chrome Extension Deferred

**Status:** Deferred to backlog

**Context:** A Chrome extension could provide real-time bookmark sync, add bookmarks with selected text as context, or offer a quick search UI in the browser.

**Decision:** Defer. The MCP server reads the Bookmarks file directly, which is sufficient for now.

**Rationale:**
- The MCP approach already works without any browser extension
- Chrome file polling covers bookmark changes (no real-time needed yet)
- The value proposition of an extension is unclear until we use the current tools more
- Extension development is a separate skill set (JavaScript, Chrome APIs, manifest v3)

**Revisit when:** We find a clear use case that the MCP file-based approach can't handle.

---

## ADR-5: Keyword Search First, Semantic Search Later

**Status:** Accepted (semantic search in backlog)

**Context:** How should we search bookmarks?

**Options considered:**

| Option | Pros | Cons |
|--------|------|------|
| **Keyword matching (chosen)** | Zero dependencies, fast, predictable | Misses synonyms and context |
| **Semantic search (embeddings)** | Understands meaning | Requires embedding model, vector storage |
| **Full-text search (FTS5)** | SQLite native, good for content | Only helps if we index page content |

**Decision:** Start with keyword matching using a `SearchEngine` protocol interface, so we can swap in semantic search later.

**Rationale:**
- Keyword search is good enough with metadata (summaries and tags dramatically improve hit rate)
- The `SearchEngine` protocol makes the implementation swappable
- Adding semantic search later doesn't require changing any other module
- Agent-driven enrichment already gives us rich text to search across

**Future:** When search quality becomes a bottleneck, add embedding-based search. The protocol interface is ready.
