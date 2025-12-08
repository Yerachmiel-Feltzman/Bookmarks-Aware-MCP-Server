---
name: Bookmarks-Aware MCP Server Implementation
overview: ""
todos:
  - id: 2bfe478a-3566-45b2-8a74-368c8e18b6b8
    content: Create project structure, requirements.txt, and .gitignore
    status: pending
  - id: 8cf393e7-15d4-4cd5-a380-6ff4eedd97fa
    content: Implement Chrome bookmarks JSON parser in src/bookmarks_reader.py
    status: pending
  - id: 6a793fd9-572a-4fd8-9a62-f40ec850243e
    content: Build keyword-based search with extensible interface in src/search.py
    status: pending
  - id: 7e174e5d-6c24-450b-b8ec-3662b1f0ef40
    content: Create MCP server with get_bookmarks tool in src/server.py
    status: pending
  - id: 5d4fece1-2532-45ed-accc-155a25fe611d
    content: Write README with setup and usage instructions
    status: pending
---

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