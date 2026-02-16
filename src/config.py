"""Configuration for the bookmarks MCP server."""
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class EnrichmentConfig:
    """Configuration for bookmark enrichment (page fetching)."""
    # Rate limiting
    requests_per_second: float = 2.0
    max_concurrent_requests: int = 5
    
    # Content extraction
    max_content_length: int = 50000  # Max chars to extract from page
    request_timeout: float = 30.0  # Seconds
    
    # Enrichment behavior
    max_age_days: int = 30  # Consider metadata stale after this many days
    
    @classmethod
    def from_env(cls) -> "EnrichmentConfig":
        """Create config from environment variables."""
        return cls(
            requests_per_second=float(os.environ.get("BOOKMARKS_RATE_LIMIT", "2.0")),
            max_concurrent_requests=int(os.environ.get("BOOKMARKS_MAX_CONCURRENT", "5")),
            max_content_length=int(os.environ.get("BOOKMARKS_MAX_CONTENT", "50000")),
            request_timeout=float(os.environ.get("BOOKMARKS_TIMEOUT", "30.0")),
            max_age_days=int(os.environ.get("BOOKMARKS_MAX_AGE_DAYS", "30")),
        )


@dataclass
class Config:
    """Main configuration for the bookmarks MCP server."""
    enrichment: EnrichmentConfig = field(default_factory=EnrichmentConfig.from_env)
    metadata_db_path: Optional[Path] = None  # None = use default
    chrome_profile: str = "Default"  # Chrome profile name
    bridge_port: int = 8765  # WebSocket port for Chrome extension bridge
    
    @classmethod
    def from_env(cls) -> "Config":
        """Create config from environment variables."""
        db_path_str = os.environ.get("BOOKMARKS_METADATA_DB")
        db_path = Path(db_path_str) if db_path_str else None
        
        return cls(
            enrichment=EnrichmentConfig.from_env(),
            metadata_db_path=db_path,
            chrome_profile=os.environ.get("BOOKMARKS_CHROME_PROFILE", "Default"),
            bridge_port=int(os.environ.get("BOOKMARKS_BRIDGE_PORT", "8765")),
        )


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get the global config instance.
    
    Returns:
        Config loaded from environment
    """
    global _config
    
    if _config is None:
        _config = Config.from_env()
    
    return _config
