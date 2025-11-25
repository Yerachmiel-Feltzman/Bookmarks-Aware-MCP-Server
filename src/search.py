"""Search engine module for bookmarks."""
from typing import List, Dict, Protocol
import re


class SearchEngine(Protocol):
    """Protocol for search engines to allow extensibility."""
    
    def search(self, query: str, bookmarks: List[Dict[str, str]], limit: int = 10) -> List[Dict[str, str]]:
        """Search bookmarks based on query.
        
        Args:
            query: Search query string
            bookmarks: List of bookmarks to search
            limit: Maximum number of results to return
            
        Returns:
            List of matching bookmarks, sorted by relevance
        """
        ...


class KeywordSearchEngine:
    """Simple keyword-based search engine."""
    
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
    
    def _score_bookmark(self, query_tokens: List[str], bookmark: Dict[str, str]) -> int:
        """Score a bookmark based on query tokens.
        
        Args:
            query_tokens: List of query tokens
            bookmark: Bookmark dictionary with 'url', 'title', 'description'
            
        Returns:
            Score (number of matching tokens)
        """
        score = 0
        
        # Combine searchable text
        searchable_text = f"{bookmark.get('title', '')} {bookmark.get('url', '')} {bookmark.get('description', '')}"
        bookmark_tokens = self._tokenize(searchable_text)
        
        # Count matching tokens
        for token in query_tokens:
            if token in bookmark_tokens:
                score += 1
        
        return score
    
    def search(self, query: str, bookmarks: List[Dict[str, str]], limit: int = 10) -> List[Dict[str, str]]:
        """Search bookmarks using keyword matching.
        
        Args:
            query: Search query string
            bookmarks: List of bookmarks to search
            limit: Maximum number of results to return
            
        Returns:
            List of matching bookmarks, sorted by relevance (highest score first)
        """
        if not query or not bookmarks:
            return []
        
        query_tokens = self._tokenize(query)
        
        # Score each bookmark
        scored_bookmarks = []
        for bookmark in bookmarks:
            score = self._score_bookmark(query_tokens, bookmark)
            if score > 0:
                scored_bookmarks.append((score, bookmark))
        
        # Sort by score (descending) and return top results
        scored_bookmarks.sort(key=lambda x: x[0], reverse=True)
        
        return [bookmark for _, bookmark in scored_bookmarks[:limit]]

