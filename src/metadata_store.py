"""SQLite metadata store for bookmark enrichment data."""
import json
import aiosqlite
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any


# Default database location
DEFAULT_DB_PATH = Path.home() / ".bookmarks-mcp" / "metadata.db"


class MetadataStore:
    """Async SQLite store for bookmark metadata (summaries, tags)."""
    
    def __init__(self, db_path: Optional[Path] = None):
        """Initialize the metadata store.
        
        Args:
            db_path: Path to SQLite database. Defaults to ~/.bookmarks-mcp/metadata.db
        """
        self.db_path = db_path or DEFAULT_DB_PATH
        self._connection: Optional[aiosqlite.Connection] = None
    
    async def initialize(self) -> None:
        """Initialize the database, creating tables if needed."""
        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self._connection = await aiosqlite.connect(self.db_path)
        self._connection.row_factory = aiosqlite.Row
        
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS bookmark_metadata (
                url TEXT PRIMARY KEY,
                title TEXT,
                summary TEXT,
                tags TEXT,
                content_hash TEXT,
                last_fetched TIMESTAMP,
                last_updated TIMESTAMP
            )
        """)
        
        # Create index for tag searches
        await self._connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_tags ON bookmark_metadata(tags)
        """)
        
        await self._connection.commit()
    
    async def close(self) -> None:
        """Close the database connection."""
        if self._connection:
            await self._connection.close()
            self._connection = None
    
    async def get_metadata(self, url: str) -> Optional[Dict[str, Any]]:
        """Get metadata for a bookmark URL.
        
        Args:
            url: The bookmark URL
            
        Returns:
            Metadata dict or None if not found
        """
        if not self._connection:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        
        cursor = await self._connection.execute(
            "SELECT * FROM bookmark_metadata WHERE url = ?",
            (url,)
        )
        row = await cursor.fetchone()
        
        if row is None:
            return None
        
        return self._row_to_dict(row)
    
    async def upsert_metadata(
        self,
        url: str,
        title: Optional[str] = None,
        summary: Optional[str] = None,
        tags: Optional[List[str]] = None,
        content_hash: Optional[str] = None,
    ) -> None:
        """Insert or update metadata for a bookmark.
        
        Args:
            url: The bookmark URL (primary key)
            title: Bookmark title
            summary: AI-generated summary
            tags: List of auto-generated tags
            content_hash: Hash of page content (for change detection)
        """
        if not self._connection:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        
        now = datetime.utcnow().isoformat()
        tags_json = json.dumps(tags) if tags else None
        
        await self._connection.execute("""
            INSERT INTO bookmark_metadata (url, title, summary, tags, content_hash, last_fetched, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                title = COALESCE(excluded.title, title),
                summary = COALESCE(excluded.summary, summary),
                tags = COALESCE(excluded.tags, tags),
                content_hash = COALESCE(excluded.content_hash, content_hash),
                last_fetched = COALESCE(excluded.last_fetched, last_fetched),
                last_updated = excluded.last_updated
        """, (url, title, summary, tags_json, content_hash, now, now))
        
        await self._connection.commit()
    
    async def search_by_tags(self, tags: List[str], limit: int = 10) -> List[Dict[str, Any]]:
        """Find bookmarks that have any of the specified tags.
        
        Args:
            tags: List of tags to search for
            limit: Maximum results to return
            
        Returns:
            List of metadata dicts matching the tags
        """
        if not self._connection:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        
        # Build query to match any tag (using LIKE for JSON array search)
        conditions = " OR ".join(["tags LIKE ?" for _ in tags])
        params = [f'%"{tag}"%' for tag in tags]
        params.append(limit)
        
        cursor = await self._connection.execute(
            f"SELECT * FROM bookmark_metadata WHERE {conditions} LIMIT ?",
            params
        )
        rows = await cursor.fetchall()
        
        return [self._row_to_dict(row) for row in rows]
    
    async def get_all_metadata(self, limit: int = 1000) -> List[Dict[str, Any]]:
        """Get all stored metadata.
        
        Args:
            limit: Maximum results to return
            
        Returns:
            List of all metadata dicts
        """
        if not self._connection:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        
        cursor = await self._connection.execute(
            "SELECT * FROM bookmark_metadata ORDER BY last_updated DESC LIMIT ?",
            (limit,)
        )
        rows = await cursor.fetchall()
        
        return [self._row_to_dict(row) for row in rows]
    
    async def get_urls_needing_enrichment(
        self,
        bookmark_urls: List[str],
        max_age_days: int = 30
    ) -> List[str]:
        """Get URLs that need enrichment (not enriched or stale).
        
        Args:
            bookmark_urls: List of all current bookmark URLs
            max_age_days: Consider metadata stale after this many days
            
        Returns:
            List of URLs needing enrichment
        """
        if not self._connection:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        
        needs_enrichment = []
        
        for url in bookmark_urls:
            cursor = await self._connection.execute(
                "SELECT last_fetched FROM bookmark_metadata WHERE url = ?",
                (url,)
            )
            row = await cursor.fetchone()
            
            if row is None:
                # Never enriched
                needs_enrichment.append(url)
            else:
                # Check if stale
                last_fetched = row["last_fetched"]
                if last_fetched:
                    fetched_date = datetime.fromisoformat(last_fetched)
                    age = (datetime.utcnow() - fetched_date).days
                    if age > max_age_days:
                        needs_enrichment.append(url)
                else:
                    needs_enrichment.append(url)
        
        return needs_enrichment
    
    async def delete_metadata(self, url: str) -> bool:
        """Delete metadata for a URL.
        
        Args:
            url: The bookmark URL
            
        Returns:
            True if deleted, False if not found
        """
        if not self._connection:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        
        cursor = await self._connection.execute(
            "DELETE FROM bookmark_metadata WHERE url = ?",
            (url,)
        )
        await self._connection.commit()
        
        return cursor.rowcount > 0
    
    def _row_to_dict(self, row: aiosqlite.Row) -> Dict[str, Any]:
        """Convert a database row to a dictionary.
        
        Args:
            row: SQLite row object
            
        Returns:
            Dictionary with parsed tags
        """
        result = dict(row)
        
        # Parse tags JSON
        if result.get("tags"):
            try:
                result["tags"] = json.loads(result["tags"])
            except json.JSONDecodeError:
                result["tags"] = []
        else:
            result["tags"] = []
        
        return result


# Global store instance
_metadata_store: Optional[MetadataStore] = None


async def get_metadata_store() -> MetadataStore:
    """Get or create the global metadata store instance.
    
    Returns:
        Initialized MetadataStore
    """
    global _metadata_store
    
    if _metadata_store is None:
        _metadata_store = MetadataStore()
        await _metadata_store.initialize()
    
    return _metadata_store
