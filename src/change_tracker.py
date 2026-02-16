"""Change tracking for bookmark modifications with undo support."""
import json
import aiosqlite
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any


class ChangeTracker:
    """Tracks bookmark changes in SQLite for history and undo support.
    
    Shares the same database as MetadataStore (default: ~/.bookmarks-mcp/metadata.db).
    Each write operation records a change with before/after state so it can be reverted.
    """
    
    def __init__(self, db_path: Optional[Path] = None):
        from src.metadata_store import DEFAULT_DB_PATH
        self.db_path = db_path or DEFAULT_DB_PATH
        self._connection: Optional[aiosqlite.Connection] = None
    
    async def initialize(self) -> None:
        """Initialize the database, creating the changes table if needed."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self._connection = await aiosqlite.connect(self.db_path)
        self._connection.row_factory = aiosqlite.Row
        
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS bookmark_changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                action TEXT NOT NULL,
                url TEXT,
                details TEXT NOT NULL,
                reverted INTEGER DEFAULT 0
            )
        """)
        
        await self._connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_changes_timestamp
            ON bookmark_changes(timestamp DESC)
        """)
        
        await self._connection.commit()
    
    async def close(self) -> None:
        """Close the database connection."""
        if self._connection:
            await self._connection.close()
            self._connection = None
    
    async def record_change(
        self,
        action: str,
        url: Optional[str],
        details: Dict[str, Any],
    ) -> int:
        """Record a bookmark change.
        
        Args:
            action: Type of change ('move', 'rename', 'delete', 'add', 'create_folder', 'bulk_move')
            url: Affected bookmark URL (None for folder operations)
            details: JSON-serializable dict with before/after state
            
        Returns:
            ID of the recorded change
        """
        if not self._connection:
            raise RuntimeError("ChangeTracker not initialized. Call initialize() first.")
        
        now = datetime.utcnow().isoformat()
        
        cursor = await self._connection.execute(
            "INSERT INTO bookmark_changes (timestamp, action, url, details, reverted) VALUES (?, ?, ?, ?, 0)",
            (now, action, url, json.dumps(details)),
        )
        await self._connection.commit()
        
        return cursor.lastrowid
    
    async def get_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent change history.
        
        Args:
            limit: Maximum number of changes to return
            
        Returns:
            List of change records, newest first
        """
        if not self._connection:
            raise RuntimeError("ChangeTracker not initialized. Call initialize() first.")
        
        cursor = await self._connection.execute(
            "SELECT * FROM bookmark_changes ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        
        return [self._row_to_dict(row) for row in rows]
    
    async def get_last_revertable(self) -> Optional[Dict[str, Any]]:
        """Get the most recent non-reverted change.
        
        Returns:
            Change record or None if nothing to revert
        """
        if not self._connection:
            raise RuntimeError("ChangeTracker not initialized. Call initialize() first.")
        
        cursor = await self._connection.execute(
            "SELECT * FROM bookmark_changes WHERE reverted = 0 ORDER BY id DESC LIMIT 1"
        )
        row = await cursor.fetchone()
        
        if row is None:
            return None
        
        return self._row_to_dict(row)
    
    async def mark_reverted(self, change_id: int) -> bool:
        """Mark a change as reverted.
        
        Args:
            change_id: ID of the change to mark
            
        Returns:
            True if marked, False if not found
        """
        if not self._connection:
            raise RuntimeError("ChangeTracker not initialized. Call initialize() first.")
        
        cursor = await self._connection.execute(
            "UPDATE bookmark_changes SET reverted = 1 WHERE id = ?",
            (change_id,),
        )
        await self._connection.commit()
        
        return cursor.rowcount > 0
    
    def _row_to_dict(self, row: aiosqlite.Row) -> Dict[str, Any]:
        """Convert a database row to a dictionary."""
        result = dict(row)
        if result.get("details"):
            try:
                result["details"] = json.loads(result["details"])
            except json.JSONDecodeError:
                result["details"] = {}
        return result


# Global tracker instance
_change_tracker: Optional[ChangeTracker] = None


async def get_change_tracker() -> ChangeTracker:
    """Get or create the global change tracker instance.
    
    Returns:
        Initialized ChangeTracker
    """
    global _change_tracker
    
    if _change_tracker is None:
        _change_tracker = ChangeTracker()
        await _change_tracker.initialize()
    
    return _change_tracker
