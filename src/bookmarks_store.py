"""Chrome bookmarks store with read and write capabilities."""
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple


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


def extract_bookmarks(node: Dict[str, Any], bookmarks: List[Dict[str, str]], path: str = "") -> None:
    """Recursively extract bookmarks from Chrome bookmarks structure.
    
    Args:
        node: Current node in the bookmarks tree
        bookmarks: List to accumulate bookmarks
        path: Current folder path
    """
    if node.get("type") == "url":
        # This is a bookmark
        bookmark = {
            "id": node.get("id", ""),
            "url": node.get("url", ""),
            "title": node.get("name", ""),
            "description": node.get("url", ""),  # Use URL as description fallback
            "folder": path,
        }
        bookmarks.append(bookmark)
    elif node.get("type") == "folder":
        # This is a folder, recurse into children
        folder_name = node.get("name", "")
        new_path = f"{path}/{folder_name}" if path else folder_name
        children = node.get("children", [])
        for child in children:
            extract_bookmarks(child, bookmarks, new_path)


def read_chrome_bookmarks(bookmarks_path: Optional[Path] = None) -> List[Dict[str, str]]:
    """Read all bookmarks from Chrome bookmarks file.
    
    Args:
        bookmarks_path: Optional path to bookmarks file. If None, uses default Chrome location.
        
    Returns:
        List of bookmarks, each with 'id', 'url', 'title', 'description', and 'folder' keys.
        Folder paths use root key as prefix (e.g., 'bookmark_bar/Subfolder').
        
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
            # Traverse children directly -- use root key as path prefix,
            # skipping the root folder's own name to keep paths consistent
            # with _find_folder_by_path (e.g., 'bookmark_bar/Subfolder')
            for child in root_node.get("children", []):
                extract_bookmarks(child, all_bookmarks, root_name)
    
    return all_bookmarks


# ============================================================================
# Write Operations
# ============================================================================

def backup_bookmarks(bookmarks_path: Optional[Path] = None) -> Path:
    """Create a backup of the bookmarks file.
    
    Args:
        bookmarks_path: Path to bookmarks file
        
    Returns:
        Path to the backup file
    """
    if bookmarks_path is None:
        bookmarks_path = get_chrome_bookmarks_path()
    
    backup_path = bookmarks_path.with_suffix(".bak")
    shutil.copy2(bookmarks_path, backup_path)
    
    return backup_path


def _generate_id() -> str:
    """Generate a unique ID for a new bookmark/folder.
    
    Chrome uses incrementing integer IDs stored as strings.
    We use timestamp-based IDs to avoid conflicts.
    """
    return str(int(time.time() * 1000000))


def _get_max_id(node: Dict[str, Any]) -> int:
    """Get the maximum ID in the bookmarks tree.
    
    Args:
        node: Bookmarks node
        
    Returns:
        Maximum ID found
    """
    max_id = int(node.get("id", "0"))
    
    if node.get("type") == "folder":
        for child in node.get("children", []):
            child_max = _get_max_id(child)
            max_id = max(max_id, child_max)
    
    return max_id


def _find_node_by_id(node: Dict[str, Any], target_id: str) -> Optional[Tuple[Dict[str, Any], Dict[str, Any], int]]:
    """Find a node by ID and return it with its parent.
    
    Args:
        node: Root node to search from
        target_id: ID to find
        
    Returns:
        Tuple of (found_node, parent_node, index_in_parent) or None
    """
    if node.get("id") == target_id:
        return (node, None, -1)
    
    if node.get("type") == "folder":
        children = node.get("children", [])
        for i, child in enumerate(children):
            if child.get("id") == target_id:
                return (child, node, i)
            result = _find_node_by_id(child, target_id)
            if result:
                return result
    
    return None


def _find_node_by_url(node: Dict[str, Any], url: str) -> Optional[Tuple[Dict[str, Any], Dict[str, Any], int]]:
    """Find a bookmark node by URL.
    
    Args:
        node: Root node to search from
        url: URL to find
        
    Returns:
        Tuple of (found_node, parent_node, index_in_parent) or None
    """
    if node.get("type") == "url" and node.get("url") == url:
        return (node, None, -1)
    
    if node.get("type") == "folder":
        children = node.get("children", [])
        for i, child in enumerate(children):
            if child.get("type") == "url" and child.get("url") == url:
                return (child, node, i)
            result = _find_node_by_url(child, url)
            if result:
                return result
    
    return None


def _find_folder_by_path(bookmarks_data: Dict[str, Any], folder_path: str) -> Optional[Dict[str, Any]]:
    """Find a folder by its path (e.g., 'bookmark_bar/Development/Python').
    
    Args:
        bookmarks_data: Full bookmarks data
        folder_path: Path to folder
        
    Returns:
        Folder node or None
    """
    parts = folder_path.strip("/").split("/")
    if not parts:
        return None
    
    roots = bookmarks_data.get("roots", {})
    
    # First part should be a root
    root_name = parts[0]
    if root_name not in roots:
        return None
    
    current = roots[root_name]
    
    # Navigate through remaining path
    for part in parts[1:]:
        found = False
        if current.get("type") == "folder":
            for child in current.get("children", []):
                if child.get("type") == "folder" and child.get("name") == part:
                    current = child
                    found = True
                    break
        
        if not found:
            return None
    
    return current if current.get("type") == "folder" else None


def write_bookmarks_file(bookmarks_data: Dict[str, Any], bookmarks_path: Optional[Path] = None) -> None:
    """Write bookmarks data to file atomically.
    
    Args:
        bookmarks_data: Bookmarks data to write
        bookmarks_path: Path to bookmarks file
    """
    if bookmarks_path is None:
        bookmarks_path = get_chrome_bookmarks_path()
    
    # Write to temp file first
    temp_path = bookmarks_path.with_suffix(".tmp")
    
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(bookmarks_data, f, indent=3)
    
    # Atomic rename
    temp_path.replace(bookmarks_path)


def move_bookmark(
    url: str,
    target_folder_path: str,
    bookmarks_path: Optional[Path] = None,
) -> bool:
    """Move a bookmark to a different folder.
    
    Args:
        url: URL of the bookmark to move
        target_folder_path: Path to target folder (e.g., 'bookmark_bar/Work')
        bookmarks_path: Path to bookmarks file
        
    Returns:
        True if successful
    """
    if bookmarks_path is None:
        bookmarks_path = get_chrome_bookmarks_path()
    
    # Backup first
    backup_bookmarks(bookmarks_path)
    
    bookmarks_data = load_bookmarks_file(bookmarks_path)
    roots = bookmarks_data.get("roots", {})
    
    # Find the bookmark
    for root_name in ["bookmark_bar", "other", "synced"]:
        if root_name in roots:
            result = _find_node_by_url(roots[root_name], url)
            if result:
                bookmark_node, parent_node, index = result
                
                if parent_node is None:
                    print(f"Cannot move root bookmark", file=sys.stderr)
                    return False
                
                # Find target folder
                target_folder = _find_folder_by_path(bookmarks_data, target_folder_path)
                if not target_folder:
                    print(f"Target folder not found: {target_folder_path}", file=sys.stderr)
                    return False
                
                # Remove from current parent
                parent_node["children"].pop(index)
                
                # Add to target folder
                target_folder.setdefault("children", []).append(bookmark_node)
                
                # Write changes
                write_bookmarks_file(bookmarks_data, bookmarks_path)
                return True
    
    print(f"Bookmark not found: {url}", file=sys.stderr)
    return False


def rename_bookmark(
    url: str,
    new_title: str,
    bookmarks_path: Optional[Path] = None,
) -> bool:
    """Rename a bookmark.
    
    Args:
        url: URL of the bookmark to rename
        new_title: New title for the bookmark
        bookmarks_path: Path to bookmarks file
        
    Returns:
        True if successful
    """
    if bookmarks_path is None:
        bookmarks_path = get_chrome_bookmarks_path()
    
    backup_bookmarks(bookmarks_path)
    
    bookmarks_data = load_bookmarks_file(bookmarks_path)
    roots = bookmarks_data.get("roots", {})
    
    for root_name in ["bookmark_bar", "other", "synced"]:
        if root_name in roots:
            result = _find_node_by_url(roots[root_name], url)
            if result:
                bookmark_node, _, _ = result
                bookmark_node["name"] = new_title
                write_bookmarks_file(bookmarks_data, bookmarks_path)
                return True
    
    print(f"Bookmark not found: {url}", file=sys.stderr)
    return False


def delete_bookmark(
    url: str,
    bookmarks_path: Optional[Path] = None,
) -> bool:
    """Delete a bookmark.
    
    Args:
        url: URL of the bookmark to delete
        bookmarks_path: Path to bookmarks file
        
    Returns:
        True if successful
    """
    if bookmarks_path is None:
        bookmarks_path = get_chrome_bookmarks_path()
    
    backup_bookmarks(bookmarks_path)
    
    bookmarks_data = load_bookmarks_file(bookmarks_path)
    roots = bookmarks_data.get("roots", {})
    
    for root_name in ["bookmark_bar", "other", "synced"]:
        if root_name in roots:
            result = _find_node_by_url(roots[root_name], url)
            if result:
                bookmark_node, parent_node, index = result
                
                if parent_node is None:
                    print(f"Cannot delete root bookmark", file=sys.stderr)
                    return False
                
                parent_node["children"].pop(index)
                write_bookmarks_file(bookmarks_data, bookmarks_path)
                return True
    
    print(f"Bookmark not found: {url}", file=sys.stderr)
    return False


def create_folder(
    folder_name: str,
    parent_folder_path: str,
    bookmarks_path: Optional[Path] = None,
) -> bool:
    """Create a new bookmark folder.
    
    Args:
        folder_name: Name of the new folder
        parent_folder_path: Path to parent folder (e.g., 'bookmark_bar')
        bookmarks_path: Path to bookmarks file
        
    Returns:
        True if successful
    """
    if bookmarks_path is None:
        bookmarks_path = get_chrome_bookmarks_path()
    
    backup_bookmarks(bookmarks_path)
    
    bookmarks_data = load_bookmarks_file(bookmarks_path)
    
    # Find parent folder
    parent_folder = _find_folder_by_path(bookmarks_data, parent_folder_path)
    if not parent_folder:
        print(f"Parent folder not found: {parent_folder_path}", file=sys.stderr)
        return False
    
    # Generate new ID
    new_id = _generate_id()
    
    # Create new folder node
    new_folder = {
        "children": [],
        "date_added": str(int(time.time() * 1000000)),
        "date_last_used": "0",
        "date_modified": str(int(time.time() * 1000000)),
        "id": new_id,
        "name": folder_name,
        "type": "folder",
    }
    
    parent_folder.setdefault("children", []).append(new_folder)
    write_bookmarks_file(bookmarks_data, bookmarks_path)
    
    return True


def get_folder_structure(bookmarks_path: Optional[Path] = None) -> Dict[str, Any]:
    """Get the folder structure of bookmarks.
    
    Args:
        bookmarks_path: Path to bookmarks file
        
    Returns:
        Dict with folder paths and their bookmark counts.
        Paths use root key as prefix (e.g., 'bookmark_bar/Subfolder').
    """
    bookmarks_data = load_bookmarks_file(bookmarks_path)
    roots = bookmarks_data.get("roots", {})
    
    folders = {}
    
    def traverse(node: Dict[str, Any], path: str):
        if node.get("type") == "folder":
            folder_name = node.get("name", "")
            current_path = f"{path}/{folder_name}" if path else folder_name
            
            bookmark_count = sum(
                1 for child in node.get("children", [])
                if child.get("type") == "url"
            )
            subfolder_count = sum(
                1 for child in node.get("children", [])
                if child.get("type") == "folder"
            )
            
            folders[current_path] = {
                "bookmarks": bookmark_count,
                "subfolders": subfolder_count,
            }
            
            for child in node.get("children", []):
                traverse(child, current_path)
    
    for root_name in ["bookmark_bar", "other", "synced"]:
        if root_name in roots:
            root_node = roots[root_name]
            
            # Add root-level info
            bookmark_count = sum(
                1 for child in root_node.get("children", [])
                if child.get("type") == "url"
            )
            subfolder_count = sum(
                1 for child in root_node.get("children", [])
                if child.get("type") == "folder"
            )
            folders[root_name] = {
                "bookmarks": bookmark_count,
                "subfolders": subfolder_count,
            }
            
            # Traverse children using root key as prefix
            for child in root_node.get("children", []):
                traverse(child, root_name)
    
    return folders


def add_bookmark(
    url: str,
    title: str,
    folder_path: str,
    bookmarks_path: Optional[Path] = None,
) -> bool:
    """Add a new bookmark to a folder.
    
    Args:
        url: URL of the new bookmark
        title: Title/name for the bookmark
        folder_path: Path to target folder (e.g., 'bookmark_bar/Dev/Python')
        bookmarks_path: Path to bookmarks file
        
    Returns:
        True if successful
    """
    if bookmarks_path is None:
        bookmarks_path = get_chrome_bookmarks_path()
    
    backup_bookmarks(bookmarks_path)
    
    bookmarks_data = load_bookmarks_file(bookmarks_path)
    
    # Find target folder
    target_folder = _find_folder_by_path(bookmarks_data, folder_path)
    if not target_folder:
        print(f"Target folder not found: {folder_path}", file=sys.stderr)
        return False
    
    # Generate a unique ID
    new_id = _generate_id()
    
    # Create the bookmark node
    new_bookmark = {
        "date_added": str(int(time.time() * 1000000)),
        "date_last_used": "0",
        "id": new_id,
        "name": title,
        "type": "url",
        "url": url,
    }
    
    target_folder.setdefault("children", []).append(new_bookmark)
    write_bookmarks_file(bookmarks_data, bookmarks_path)
    
    return True


def bulk_move_bookmarks(
    moves: List[Dict[str, str]],
    bookmarks_path: Optional[Path] = None,
) -> int:
    """Move multiple bookmarks at once.
    
    Args:
        moves: List of dicts with 'url' and 'target_folder' keys
        bookmarks_path: Path to bookmarks file
        
    Returns:
        Number of successful moves
    """
    if bookmarks_path is None:
        bookmarks_path = get_chrome_bookmarks_path()
    
    backup_bookmarks(bookmarks_path)
    
    bookmarks_data = load_bookmarks_file(bookmarks_path)
    roots = bookmarks_data.get("roots", {})
    
    success_count = 0
    
    for move in moves:
        url = move.get("url")
        target_path = move.get("target_folder")
        
        if not url or not target_path:
            continue
        
        # Find the bookmark
        found = False
        for root_name in ["bookmark_bar", "other", "synced"]:
            if root_name in roots:
                result = _find_node_by_url(roots[root_name], url)
                if result:
                    bookmark_node, parent_node, index = result
                    
                    if parent_node is None:
                        continue
                    
                    target_folder = _find_folder_by_path(bookmarks_data, target_path)
                    if not target_folder:
                        continue
                    
                    parent_node["children"].pop(index)
                    target_folder.setdefault("children", []).append(bookmark_node)
                    
                    success_count += 1
                    found = True
                    break
    
    if success_count > 0:
        write_bookmarks_file(bookmarks_data, bookmarks_path)
    
    return success_count
