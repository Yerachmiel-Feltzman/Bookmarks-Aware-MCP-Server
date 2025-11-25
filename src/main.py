"""Main entry point for the bookmarks-aware MCP server."""
import sys
from pathlib import Path

# Add project root to Python path for absolute imports
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import asyncio
from src.server import main

if __name__ == "__main__":
    asyncio.run(main())

