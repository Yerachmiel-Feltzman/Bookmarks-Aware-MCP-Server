"""Chrome bookmarks reader module."""
import json
import os
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional


def get_chrome_bookmarks_path(profile: str = "Default") -> Path:
    """Get the path to Chrome bookmarks file.
    
    Args:
        profile: Chrome profile name (default: "Default")
        
    Returns:
        Path to the Bookmarks file
    """
    home = Path.home()
    if os.name == "nt":  # Windows
        chrome_path = home / "AppData" / "Local" / "Google" / "Chrome" / "User Data" / profile / "Bookmarks"
    elif sys.platform == "darwin":  # macOS
        chrome_path = home / "Library" / "Application Support" / "Google" / "Chrome" / profile / "Bookmarks"
    elif os.name == "posix":  # Linux
        chrome_path = home / ".config" / "google-chrome" / profile / "Bookmarks"
        # Also check for chromium
        if not chrome_path.exists():
            chrome_path = home / ".config" / "chromium" / profile / "Bookmarks"
    else:
        raise OSError(f"Unsupported operating system: {os.name}")
    
    return chrome_path


def load_bookmarks_file(bookmarks_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load Chrome bookmarks JSON file.
    
    Args:
        bookmarks_path: Optional path to bookmarks file. If None, uses default Chrome location.
        
    Returns:
        Parsed JSON bookmarks data
        
    Raises:
        FileNotFoundError: If bookmarks file doesn't exist
        json.JSONDecodeError: If bookmarks file is malformed
    """
    if bookmarks_path is None:
        bookmarks_path = get_chrome_bookmarks_path()
    
    if not bookmarks_path.exists():
        raise FileNotFoundError(f"Bookmarks file not found at {bookmarks_path}")
    
    with open(bookmarks_path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_bookmarks(node: Dict[str, Any], bookmarks: List[Dict[str, str]]) -> None:
    """Recursively extract bookmarks from Chrome bookmarks structure.
    
    Args:
        node: Current node in the bookmarks tree
        bookmarks: List to accumulate bookmarks
    """
    if node.get("type") == "url":
        # This is a bookmark
        bookmark = {
            "url": node.get("url", ""),
            "title": node.get("name", ""),
            "description": node.get("url", "")  # Use URL as description fallback
        }
        bookmarks.append(bookmark)
    elif node.get("type") == "folder":
        # This is a folder, recurse into children
        children = node.get("children", [])
        for child in children:
            extract_bookmarks(child, bookmarks)


def read_chrome_bookmarks(bookmarks_path: Optional[Path] = None) -> List[Dict[str, str]]:
    """Read all bookmarks from Chrome bookmarks file.
    
    Args:
        bookmarks_path: Optional path to bookmarks file. If None, uses default Chrome location.
        
    Returns:
        List of bookmarks, each with 'url', 'title', and 'description' keys
        
    Raises:
        FileNotFoundError: If bookmarks file doesn't exist
        json.JSONDecodeError: If bookmarks file is malformed
    """
    bookmarks_data = load_bookmarks_file(bookmarks_path)
    
    all_bookmarks = []
    
    # Chrome stores bookmarks in roots: bookmark_bar, other, synced
    roots = bookmarks_data.get("roots", {})
    
    for root_name in ["bookmark_bar", "other", "synced"]:
        if root_name in roots:
            root_node = roots[root_name]
            extract_bookmarks(root_node, all_bookmarks)
    
    return all_bookmarks

