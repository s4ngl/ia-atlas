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
    base_url: str = "https://servicenow.iu.edu"


# -----------------------------
# Database Configuration
# -----------------------------
@dataclass(frozen=True)
class DatabaseConfig:
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
    headless: bool = True
    page_load_timeout: int = 30
    wait_timeout: int = 10


# -----------------------------
# Crawl Configuration
# -----------------------------
@dataclass(frozen=True)
class CrawlConfig:
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
