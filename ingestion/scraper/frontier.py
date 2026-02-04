"""
Frontier module - manages the queue of URLs to crawl
Implements BFS/DFS strategies and visited tracking
"""
from typing import Optional, Set, List
from collections import deque
import re


class Frontier:
    """
    Manages URLs to visit next using a queue/stack structure
    Tracks visited URLs to avoid duplicates
    """

    def __init__(self, strategy: str = "bfs"):
        """
        Initialize frontier with specified strategy

        Args:
            strategy: Either "bfs" (breadth-first) or "dfs" (depth-first)
        """
        self.strategy = strategy.lower()
        self.queue = deque()
        self.visited: Set[str] = set()
        self.pending: Set[str] = set()  # URLs in queue but not yet visited
        self.skipped_kb_articles = 0  # Add this line

    def add(self, url: str) -> bool:
        """
        Add a URL to the frontier if it hasn't been visited

        Args:
            url: URL to add

        Returns:
            True if URL was added, False if already visited or skipped
        """
        normalized = self._normalize_url(url)

        # Skip KB-prefixed articles at the frontier level
        if normalized.startswith('sys_kb_id:'):
            sys_kb_id = normalized.split(':', 1)[1]
            # Skip all KB-prefixed articles (they're always broken)
            if sys_kb_id.startswith('KB'):
                self.skipped_kb_articles += 1
                if self.skipped_kb_articles <= 10:  # Log first 10 for debugging
                    print(f"[Frontier] Skipping KB-prefixed article: {sys_kb_id}")
                elif self.skipped_kb_articles == 11:
                    print(f"[Frontier] ... and more KB articles (logging stopped)")
                return False

        if normalized in self.visited:
            return False

        if normalized not in self.pending:
            # FIX: Use add() for sets, not append()
            self.pending.add(normalized)
            self.queue.append(normalized)

        return True

    def add_batch(self, urls: List[str]) -> int:
        """
        Add multiple URLs to the frontier

        Args:
            urls: List of URLs to add

        Returns:
            Number of URLs actually added (excluding duplicates)
        """
        added_count = 0
        for url in urls:
            if self.add(url):
                added_count += 1
        return added_count

    def get_next(self) -> Optional[str]:
        """
        Get the next URL to crawl

        Returns:
            Next URL to visit, or None if queue is empty
        """
        if not self.queue:
            return None

        # BFS: pop from left (FIFO)
        # DFS: pop from right (LIFO)
        if self.strategy == "bfs":
            url = self.queue.popleft()
        else:  # dfs
            url = self.queue.pop()

        self.visited.add(url)
        self.pending.discard(url)

        return url

    def empty(self) -> bool:
        """
        Check if frontier is empty

        Returns:
            True if no more URLs to crawl
        """
        return len(self.queue) == 0

    def size(self) -> int:
        """
        Get current size of the frontier

        Returns:
            Number of URLs pending in queue
        """
        return len(self.queue)

    def visited_count(self) -> int:
        """
        Get number of URLs already visited

        Returns:
            Count of visited URLs
        """
        return len(self.visited)

    def has_visited(self, url: str) -> bool:
        """
        Check if URL has been visited

        Args:
            url: URL to check

        Returns:
            True if URL has been visited
        """
        return self._normalize_url(url) in self.visited

    def mark_visited(self, url: str) -> None:
        """
        Mark a URL as visited (useful for skipping URLs without crawling them)

        Args:
            url: URL to mark as visited
        """
        normalized = self._normalize_url(url)
        self.visited.add(normalized)
        self.pending.discard(normalized)

    def clear(self):
        """Reset the frontier to empty state"""
        self.queue.clear()
        self.visited.clear()
        self.pending.clear()

    def load_visited_urls(self, urls: List[str]):
        """
        Load a list of already-visited URLs into the frontier
        Used to resume crawling by marking articles as already processed

        Args:
            urls: List of URLs to mark as visited
        """
        for url in urls:
            normalized_url = self._normalize_url(url)
            self.visited.add(normalized_url)

        print(f"Loaded {len(urls)} already-crawled articles into frontier")

    def _normalize_url(self, url: str) -> str:
        """
        Normalize URL for consistent comparison
        Uses sys_kb_id as the canonical identifier if available

        Args:
            url: URL to normalize

        Returns:
            Normalized URL (sys_kb_id if found, otherwise cleaned URL)
        """
        # Try to extract sys_kb_id (canonical identifier)
        sys_kb_id = self._extract_sys_kb_id(url)
        if sys_kb_id:
            # Use sys_kb_id as the canonical identifier
            return f"sys_kb_id:{sys_kb_id}"

        # Fallback: basic URL normalization
        # Remove trailing slash
        url = url.rstrip('/')

        # Remove fragments (everything after #)
        if '#' in url:
            url = url.split('#')[0]

        return url

    @staticmethod
    def _extract_sys_kb_id(url: str) -> Optional[str]:
        """
        Extract the canonical sys_kb_id from a ServiceNow URL

        Args:
            url: ServiceNow article URL

        Returns:
            sys_kb_id if found, None otherwise
        """
        # Try to extract sys_kb_id parameter (hex format)
        match = re.search(r'sys_kb_id=([a-f0-9]+)', url, re.IGNORECASE)
        if match:
            return match.group(1)

        # Try to extract sysparm_article parameter (KB number format)
        match = re.search(r'sysparm_article=(KB[0-9]+)', url, re.IGNORECASE)
        if match:
            return match.group(1)

        return None

    def get_stats(self) -> dict:
        """
        Get frontier statistics

        Returns:
            Dictionary with frontier stats
        """
        return {
            'pending': len(self.queue),
            'visited': len(self.visited),
            'total_seen': len(self.visited) + len(self.pending),
            'strategy': self.strategy,
            'skipped_kb': self.skipped_kb_articles  # Add this line
        }

    def __repr__(self) -> str:
        """String representation of frontier"""
        return (
            f"Frontier(strategy={self.strategy}, "
            f"pending={len(self.queue)}, "
            f"visited={len(self.visited)}, "
            f"skipped_kb={self.skipped_kb_articles})"
        )
