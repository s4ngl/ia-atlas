"""
Parser module - extracts content and links from ServiceNow article HTML
"""
from bs4 import BeautifulSoup
from typing import Dict, List, Set
from urllib.parse import urljoin, urlparse
from config import SERVICENOW_BASE_URL


class Parser:
    """Parses ServiceNow article HTML to extract content and links"""

    def __init__(self):
        self.base_url = SERVICENOW_BASE_URL

    def extract_article(self, html: str, url: str) -> Dict:
        """
        Extract title, content, and links from article HTML

        Args:
            html: Raw HTML content
            url: URL of the article

        Returns:
            Dictionary containing article data:
            {
                'url': str,
                'title': str,
                'content': str,
                'links': List[str],
                'html': str
            }
        """
        soup = BeautifulSoup(html, 'html.parser')

        title = self._extract_title(soup)
        content = self._extract_content(soup)
        links = self._extract_knowledge_links(soup, url)

        return {
            'url': url,
            'title': title,
            'content': content,
            'links': links,
            'html': html
        }

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """
        Extract article title from HTML

        Args:
            soup: BeautifulSoup object

        Returns:
            Article title as string
        """
        # Try multiple selectors for ServiceNow article titles
        selectors = [
            'h1.article-title',
            'h1[data-kb-title]',
            '.kb-article-title',
            'article h1',
            'h1'
        ]

        for selector in selectors:
            title_elem = soup.select_one(selector)
            if title_elem:
                return title_elem.get_text(strip=True)

        # Fallback to page title
        if soup.title:
            return soup.title.string.strip()

        return "Untitled Article"

    def _extract_content(self, soup: BeautifulSoup) -> str:
        """
        Extract main article content from HTML

        Args:
            soup: BeautifulSoup object

        Returns:
            Article content as string
        """
        # Try to find the main content area
        content_selectors = [
            'article',
            '.kb-article-content',
            '.article-content',
            'main',
            '[role="main"]',
            '.content'
        ]

        content_elem = None
        for selector in content_selectors:
            content_elem = soup.select_one(selector)
            if content_elem:
                break

        # Fallback to body if no content area found
        if not content_elem:
            content_elem = soup.body

        if not content_elem:
            return ""

        # Remove script and style elements
        for script in content_elem(['script', 'style', 'nav', 'footer', 'header']):
            script.decompose()

        # Get text content
        text = content_elem.get_text(separator='\n', strip=True)

        # Clean up excessive whitespace
        lines = [line.strip() for line in text.split('\n')]
        lines = [line for line in lines if line]  # Remove empty lines

        return '\n'.join(lines)

    def _extract_knowledge_links(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        """
        Extract links to other knowledge base articles

        Args:
            soup: BeautifulSoup object
            base_url: Base URL for resolving relative links

        Returns:
            List of absolute URLs to other KB articles
        """
        links: Set[str] = set()

        # Find all links in the content
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']

            # Make absolute URL
            absolute_url = self._make_absolute_url(href, base_url)

            # Only include ServiceNow KB article links
            if self._is_kb_article_link(absolute_url):
                links.add(absolute_url)

        return list(links)

    def _make_absolute_url(self, href: str, base_url: str) -> str:
        """
        Convert relative URL to absolute URL

        Args:
            href: URL (relative or absolute)
            base_url: Base URL for resolving relative URLs

        Returns:
            Absolute URL
        """
        # Handle empty href
        if not href or href.startswith('#'):
            return ""

        # Already absolute
        if href.startswith('http'):
            return href

        # Make absolute using urljoin
        return urljoin(base_url, href)

    def _is_kb_article_link(self, url: str) -> bool:
        """
        Check if URL is a ServiceNow knowledge base article

        Args:
            url: URL to check

        Returns:
            True if URL is a KB article, False otherwise
        """
        if not url:
            return False

        parsed = urlparse(url)

        # Must be from ServiceNow domain
        if 'servicenow.iu.edu' not in parsed.netloc:
            return False

        # Check for KB article patterns
        kb_patterns = [
            'id=kb_article',
            'id=kb_article_view',
            'sys_kb_id=',
        ]

        query = parsed.query.lower()
        path = parsed.path.lower()

        for pattern in kb_patterns:
            if pattern in query or pattern in path:
                return True

        return False

    def extract_article_metadata(self, soup: BeautifulSoup) -> Dict:
        """
        Extract metadata from article (number, update date, etc.)

        Args:
            soup: BeautifulSoup object

        Returns:
            Dictionary of metadata
        """
        metadata = {}

        # Try to extract article number
        number_elem = soup.select_one('[data-article-number]')
        if number_elem:
            metadata['number'] = number_elem.get('data-article-number', '')

        # Try to extract update date
        date_elem = soup.select_one('.article-date, .updated-date, time')
        if date_elem:
            metadata['updated'] = date_elem.get_text(strip=True)

        return metadata
