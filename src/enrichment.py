"""Enrichment pipeline for bookmark metadata.

This module handles fetching and extracting page content. The actual
summarization and tagging is delegated to the calling agent (the LLM
that invokes the MCP tools), not done server-side.

Flow:
  1. Agent calls fetch_page_content -> gets extracted text back
  2. Agent generates summary + tags using its own model
  3. Agent calls store_bookmark_metadata -> metadata saved to SQLite
"""
import hashlib
import sys
from typing import Optional

import httpx
import trafilatura

from src.config import get_config


async def fetch_page_content(url: str, timeout: Optional[float] = None) -> Optional[str]:
    """Fetch and extract text content from a URL.
    
    Args:
        url: URL to fetch
        timeout: Request timeout in seconds (defaults to config)
        
    Returns:
        Extracted text content or None if failed
    """
    if timeout is None:
        timeout = get_config().enrichment.request_timeout
    
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "BookmarksMCP/1.0 (bookmark enrichment)"}
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            
            html = response.text
            
            # Extract main content using trafilatura
            content = trafilatura.extract(
                html,
                include_comments=False,
                include_tables=True,
                no_fallback=False,
            )
            
            if content:
                max_len = get_config().enrichment.max_content_length
                if len(content) > max_len:
                    content = content[:max_len] + "\n\n[content truncated]"
            
            return content
            
    except httpx.HTTPError as e:
        print(f"HTTP error fetching {url}: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Error fetching {url}: {e}", file=sys.stderr)
        return None


def compute_content_hash(content: str) -> str:
    """Compute a hash of content for change detection.
    
    Args:
        content: Text content
        
    Returns:
        SHA256 hash prefix of content
    """
    return hashlib.sha256(content.encode()).hexdigest()[:16]
