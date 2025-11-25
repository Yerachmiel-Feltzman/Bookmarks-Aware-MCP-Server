<!-- cc71e405-8cb2-4dc4-b2cc-2bddd9ae8ce7 55b124cc-602a-41e0-9516-9331872f57b5 -->
# Bookmarks-Aware MCP Server Implementation

## Architecture Overview

Build a Python MCP server with three core modules:

1. **Bookmarks Reader** - Reads Chrome bookmarks from `~/Library/Application Support/Google/Chrome/Default/Bookmarks`
2. **Search Engine** - Simple keyword matching (extensible to embeddings later)
3. **MCP Server** - Exposes `get_bookmarks` tool

## Implementation Steps

### 1. Project Setup

- Create `requirements.txt` with dependencies: `mcp` SDK for Python
- Create project structure: `src/` directory with modular components
- Add `.gitignore` for Python projects

### 2. Chrome Bookmarks Reader (`src/bookmarks_reader.py`)

- Parse Chrome's JSON bookmarks file structure
- Recursively traverse bookmark folders (bookmark_bar, other, synced)
- Extract: URL, title (name field), and use URL as description fallback
- Handle missing/malformed bookmarks file gracefully

### 3. Simple Search Engine (`src/search.py`)

- Implement keyword matching: tokenize query and bookmark text
- Search across URL, title fields
- Return ranked results (simple scoring: count of matching keywords)
- Design interface to be replaceable with semantic search later

### 4. MCP Server Implementation (`src/server.py`)

- Initialize MCP server using Python SDK
- Define `get_bookmarks` tool:
- Input: `query` (string)
- Output: List of bookmarks with url, title, description
- Wire up bookmarks reader and search engine
- Add error handling for missing bookmarks file

### 5. Configuration & Documentation

- Create `README.md` with:
- Installation instructions
- How to configure Chrome profile path
- Example usage with MCP client
- Optional: Add config file for custom Chrome profile paths

## Key Design Decisions

- **Extensibility**: Search module uses abstract interface so keyword matching can be swapped for embeddings
- **Simple First**: Start with basic string matching, no external APIs or vector databases
- **Read-only**: No bookmark modifications, only read access
- **Error Handling**: Graceful degradation if bookmarks file not found

### To-dos

- [ ] Create project structure, requirements.txt, and .gitignore
- [ ] Implement Chrome bookmarks JSON parser in src/bookmarks_reader.py
- [ ] Build keyword-based search with extensible interface in src/search.py
- [ ] Create MCP server with get_bookmarks tool in src/server.py
- [ ] Write README with setup and usage instructions