# config/config.py
"""
Configuration file for ServiceNow Knowledge Base Graph Scraper
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Dict

# -----------------------------
# ServiceNow Configuration
# -----------------------------
@dataclass(frozen=True)
class ServiceNowConfig:
    """
    ServiceNow instance configuration

    Args:
        base_url: The base URL of your ServiceNow instance
                 Example: "https://your-instance.service-now.com"
    """
    base_url: str = "https://servicenow.iu.edu"


# -----------------------------
# Database Configuration
# -----------------------------
@dataclass(frozen=True)
class DatabaseConfig:
    """
    PostgreSQL database configuration

    Args:
        dbname: Name of the database
        user: Database username
        password: Database password
        host: Database host (usually 'localhost')
        port: Database port (default PostgreSQL port is 5432)
    """
    dbname: str = 'servicenow_kb'
    user: str = 'skaii.flakes'
    password: str = '20110012'
    host: str = 'localhost'
    port: int = 5432


# -----------------------------
# Request Configuration
# -----------------------------
@dataclass(frozen=True)
class RequestConfig:
    """
    HTTP request configuration for web scraping

    Args:
        delay: Delay in seconds between requests (rate limiting)
        timeout: Request timeout in seconds
        default_headers: Default HTTP headers to use in requests
    """
    delay: float = 1.0  # Seconds between requests
    timeout: int = 30  # Request timeout in seconds
    default_headers: Dict[str, str] = field(default_factory=lambda: {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:148.0) Gecko/20100101 Firefox/148.0',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    })


# -----------------------------
# Selenium Configuration
# -----------------------------
@dataclass(frozen=True)
class SeleniumConfig:
    """
    Selenium WebDriver configuration (used in legacy scraper)

    Args:
        headless: Run browser in headless mode (no GUI)
        page_load_timeout: Timeout for page loads in seconds
        wait_timeout: Timeout for element waits in seconds
    """
    headless: bool = True
    page_load_timeout: int = 30
    wait_timeout: int = 10


# -----------------------------
# Crawl Configuration
# -----------------------------
@dataclass(frozen=True)
class CrawlConfig:
    """
    Web crawling configuration for Phase 0

    Args:
        max_articles_per_keyword: Maximum number of articles to crawl per keyword
                                  Set to None for unlimited
        strategy: Crawl strategy - either "bfs" (breadth-first) or "dfs" (depth-first)
                 BFS: Crawls all articles at depth 0, then depth 1, then depth 2, etc.
                 DFS: Follows each article's links deeply before moving to next article
        search_keywords: List of (keyword, max_depth) tuples
                        keyword: Search term to find articles
                        max_depth: Maximum link depth to follow from search results
                                  0 = only search results
                                  1 = search results + their linked articles
                                  2 = search results + links + links from those links

    Example search_keywords:
        [
            ("Canvas", 2),        # Search "Canvas", follow links up to depth 2
            ("Email", 1),         # Search "Email", follow links up to depth 1
            ("VPN", 0),          # Search "VPN", only get search results (no links)
        ]
    """
    max_articles_per_keyword: int = 1000
    strategy: str = "bfs"  # "bfs" or "dfs"
    search_keywords: List[Tuple[str, int]] = field(default_factory=lambda: [
        ("containerization", 0),
        ("conda", 0),
        ("MATLAB", 0),
        ("R", 0),
        ("Python", 0),
        ("research computing", 0),
        ("data transfer", 0),
        ("job submission", 0),
        ("batch job", 0),
        ("Kubernetes", 0),
    ])
