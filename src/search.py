"""Search engine module for bookmarks."""
from typing import List, Dict, Protocol, Optional, Any
import re


class SearchEngine(Protocol):
    """Protocol for search engines to allow extensibility."""
    
    def search(
        self,
        query: str,
        bookmarks: List[Dict[str, str]],
        limit: int = 10,
        tags_filter: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """Search bookmarks based on query.
        
        Args:
            query: Search query string
            bookmarks: List of bookmarks to search
            limit: Maximum number of results to return
            tags_filter: Optional list of tags to filter by
            metadata: Optional dict of url -> metadata for enhanced search
            
        Returns:
            List of matching bookmarks, sorted by relevance
        """
        ...


class KeywordSearchEngine:
    """Keyword-based search engine with metadata support."""
    
    def _tokenize(self, text: str) -> List[str]:
        """Tokenize text into words.
        
        Args:
            text: Text to tokenize
            
        Returns:
            List of lowercase words
        """
        # Convert to lowercase and split on non-word characters
        words = re.findall(r'\b\w+\b', text.lower())
        return words
    
    def _score_bookmark(
        self,
        query_tokens: List[str],
        bookmark: Dict[str, str],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Score a bookmark based on query tokens.
        
        Args:
            query_tokens: List of query tokens
            bookmark: Bookmark dictionary with 'url', 'title', 'description'
            metadata: Optional metadata with 'summary' and 'tags'
            
        Returns:
            Score (number of matching tokens, weighted)
        """
        score = 0
        
        # Combine searchable text from bookmark
        searchable_text = f"{bookmark.get('title', '')} {bookmark.get('url', '')} {bookmark.get('description', '')}"
        
        # Add metadata if available
        if metadata:
            summary = metadata.get('summary', '')
            tags = metadata.get('tags', [])
            if summary:
                searchable_text += f" {summary}"
            if tags:
                searchable_text += f" {' '.join(tags)}"
        
        bookmark_tokens = self._tokenize(searchable_text)
        
        # Count matching tokens
        for token in query_tokens:
            if token in bookmark_tokens:
                score += 1
        
        # Bonus for tag matches (exact match in tags list)
        if metadata and metadata.get('tags'):
            for token in query_tokens:
                if token in metadata['tags']:
                    score += 2  # Extra weight for tag matches
        
        return score
    
    def _matches_tags_filter(
        self,
        metadata: Optional[Dict[str, Any]],
        tags_filter: List[str],
    ) -> bool:
        """Check if bookmark matches tag filter.
        
        Args:
            metadata: Bookmark metadata
            tags_filter: Required tags
            
        Returns:
            True if all filter tags are present
        """
        if not metadata or not metadata.get('tags'):
            return False
        
        bookmark_tags = set(metadata['tags'])
        return all(tag.lower() in bookmark_tags for tag in tags_filter)
    
    def search(
        self,
        query: str,
        bookmarks: List[Dict[str, str]],
        limit: int = 10,
        tags_filter: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """Search bookmarks using keyword matching with metadata.
        
        Args:
            query: Search query string
            bookmarks: List of bookmarks to search
            limit: Maximum number of results to return
            tags_filter: Optional list of tags to filter by (AND logic)
            metadata: Optional dict of url -> metadata for enhanced search
            
        Returns:
            List of matching bookmarks with metadata, sorted by relevance
        """
        if not bookmarks:
            return []
        
        # If only filtering by tags (no query)
        if not query and tags_filter and metadata:
            results = []
            for bookmark in bookmarks:
                url = bookmark.get('url', '')
                meta = metadata.get(url)
                if self._matches_tags_filter(meta, tags_filter):
                    result = {**bookmark}
                    if meta:
                        result['summary'] = meta.get('summary', '')
                        result['tags'] = meta.get('tags', [])
                    results.append(result)
            return results[:limit]
        
        if not query:
            return []
        
        query_tokens = self._tokenize(query)
        metadata = metadata or {}
        
        # Score each bookmark
        scored_bookmarks = []
        for bookmark in bookmarks:
            url = bookmark.get('url', '')
            meta = metadata.get(url)
            
            # Apply tags filter if specified
            if tags_filter and not self._matches_tags_filter(meta, tags_filter):
                continue
            
            score = self._score_bookmark(query_tokens, bookmark, meta)
            if score > 0:
                # Merge bookmark with metadata
                result = {**bookmark}
                if meta:
                    result['summary'] = meta.get('summary', '')
                    result['tags'] = meta.get('tags', [])
                scored_bookmarks.append((score, result))
        
        # Sort by score (descending) and return top results
        scored_bookmarks.sort(key=lambda x: x[0], reverse=True)
        
        return [bookmark for _, bookmark in scored_bookmarks[:limit]]

