"""
Fetcher module - handles all HTTP requests to ServiceNow
Includes search API and article HTML fetching with Selenium support
"""
import requests
import time
import re
import json
from typing import Dict, List, Optional
from urllib.parse import quote, urljoin
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from config import (
    REQUEST_DELAY, REQUEST_TIMEOUT, DEFAULT_HEADERS, SERVICENOW_BASE_URL,
    SELENIUM_HEADLESS, SELENIUM_PAGE_LOAD_TIMEOUT, SELENIUM_WAIT_TIMEOUT
)


class Fetcher:
    """Handles HTTP requests for ServiceNow search and article fetching"""

    def __init__(self):
        self.last_request_time = 0
        self.session = requests.Session()
        self.driver = None
        self.driver_initialized = False
        self._init_selenium()

    def _init_selenium(self):
        """Initialize Selenium WebDriver"""
        try:
            # Close existing driver if any
            if self.driver:
                try:
                    self.driver.quit()
                except Exception:
                    pass

            options = Options()
            if SELENIUM_HEADLESS:
                options.add_argument('--headless')

            # Additional options for stability
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--disable-blink-features=AutomationControlled')

            # Set page load timeout
            options.page_load_strategy = 'normal'

            self.driver = webdriver.Firefox(options=options)
            self.driver.set_page_load_timeout(SELENIUM_PAGE_LOAD_TIMEOUT)
            self.driver_initialized = True

            print("✓ Selenium WebDriver initialized")
        except Exception as e:
            print(f"✗ Failed to initialize Selenium: {e}")
            print("  Make sure Firefox and geckodriver are installed")
            self.driver = None
            self.driver_initialized = False

    def search_knowledge_base(
        self,
        keyword: str,
        cookies_string: str,
        user_token: str,
        start: int = 0,
        end: int = 100
    ) -> List[Dict]:
        """
        Search ServiceNow knowledge base and return list of articles

        Args:
            keyword: Search keyword
            cookies_string: Cookie string from browser
            user_token: X-UserToken from browser
            start: Starting index for results
            end: Ending index for results

        Returns:
            List of article dictionaries with metadata
        """
        # API endpoint with query parameters
        url = (
            f"{SERVICENOW_BASE_URL}/api/now/sp/rectangle/"
            f"350093d33bdd6a10bae1500864e45add"
            f"?id=iu_kb_search&query={quote(keyword)}&spa=1"
        )

        # Request headers matching browser
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:148.0) Gecko/20100101 Firefox/148.0",
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Referer": f"{SERVICENOW_BASE_URL}/kb?id=iu_kb_search&query={quote(keyword)}&spa=1",
            "x-portal": "bb4b42871b290e106ef441d8cd4bcbdb",
            "Content-Type": "application/json;charset=utf-8",
            "X-Transaction-Source": "Interface=Web,Interface-Name=KB,Interface-Type=Service Portal,Interface-SysID=bb4b42871b290e106ef441d8cd4bcbdb",
            "X-Use-Polaris": "false",
            "X-UserToken": user_token,
            "Origin": SERVICENOW_BASE_URL,
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }

        # Request payload
        payload_data = {
            "keyword": keyword,
            "language": "",
            "variables": {},
            "resource": "",
            "kb_query": "",
            "social_query": "",
            "category_as_tree": False,
            "order": "relevancy,false",
            "start": start,
            "end": end,
            "attachment": True,
            "portal_suffix": "kb",
            "knowledge_fields": [
                "can_read_user_criteria",
                "number",
                "sys_updated_on",
                "display_number"
            ],
            "social_fields": [
                "sys_updated_on",
                "sys_created_on",
                "votes",
                "answer_count"
            ]
        }

        request_payload = {
            "payload": json.dumps(payload_data),
            "timeout": {},
            "sessionRotationTrigger": True
        }

        # Parse cookies
        cookies_dict = self._parse_cookies(cookies_string)

        # Rate limiting
        self._rate_limit()

        try:
            response = self.session.post(
                url,
                headers=headers,
                json=request_payload,
                cookies=cookies_dict,
                timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()
            self.last_request_time = time.time()

            return self._extract_search_results(response.json())

        except requests.exceptions.RequestException as e:
            print(f"Error searching for '{keyword}': {e}")
            return []

    def fetch_article_html(self, url: str, cookies_string: str = None) -> Optional[str]:
        """
        Fetch the HTML content of a single article using Selenium
        This allows capturing dynamically loaded Angular content

        Args:
            url: Article URL (can be relative or absolute)
            cookies_string: Optional cookies for authenticated access

        Returns:
            HTML content as string, or None if fetch failed
        """
        # Make absolute URL if relative
        if not url.startswith('http'):
            url = urljoin(SERVICENOW_BASE_URL, url)

        # Rate limiting
        self._rate_limit()

        # Try Selenium first for dynamic content
        if self.driver_initialized and self.driver:
            try:
                html = self._fetch_with_selenium(url, cookies_string)
                if html:
                    self.last_request_time = time.time()
                    return html
            except Exception as e:
                print(f"  Selenium fetch failed: {e}")
                # Driver might be broken, try to reinitialize
                self.driver_initialized = False

        # Fallback to requests if Selenium fails
        return self._fetch_with_requests(url, cookies_string)

    def _fetch_with_selenium(self, url: str, cookies_string: str = None) -> Optional[str]:
        """
        Fetch page using Selenium to capture dynamic content

        Args:
            url: Article URL
            cookies_string: Optional cookies for authenticated access

        Returns:
            HTML content as string, or None if fetch failed
        """
        try:
            # Check if driver is still alive
            try:
                _ = self.driver.current_url
            except Exception:
                # Driver is dead, reinitialize
                print("  → Selenium driver connection lost, reinitializing...")
                self._init_selenium()
                if not self.driver_initialized:
                    return None

            # Add cookies BEFORE navigating to the page if provided
            # This prevents an initial unauthenticated request
            if cookies_string:
                # First navigate to the domain to set cookies
                # (cookies can only be set for the current domain)
                domain_url = f"{SERVICENOW_BASE_URL}/kb"
                try:
                    self.driver.get(domain_url)
                except Exception:
                    pass  # Ignore errors on domain navigation

                # Now add cookies
                cookies_dict = self._parse_cookies(cookies_string)
                for name, value in cookies_dict.items():
                    try:
                        self.driver.add_cookie({'name': name, 'value': value})
                    except Exception as e:
                        # Silently fail for incompatible cookies
                        pass

            # Now navigate to the actual page (WITH cookies)
            self.driver.get(url)

            # Wait for Angular content to load
            # Wait for specific elements that indicate the page is fully loaded
            wait = WebDriverWait(self.driver, SELENIUM_WAIT_TIMEOUT)

            try:
                # Wait for article content or links to be present
                wait.until(
                    EC.presence_of_element_located((By.TAG_NAME, "article"))
                )
            except TimeoutException:
                # If article tag doesn't exist, just wait a bit for any content
                time.sleep(2)

            # Additional wait for Angular to finish rendering
            time.sleep(1)

            # Get the fully rendered HTML
            html = self.driver.page_source

            return html

        except WebDriverException as e:
            print(f"  Selenium error fetching {url}: {e}")
            # Mark driver as not initialized so it gets restarted
            self.driver_initialized = False
            return None
        except Exception as e:
            print(f"  Unexpected error with Selenium: {e}")
            self.driver_initialized = False
            return None

    def _fetch_with_requests(self, url: str, cookies_string: str = None) -> Optional[str]:
        """
        Fallback method using requests library

        Args:
            url: Article URL
            cookies_string: Optional cookies for authenticated access

        Returns:
            HTML content as string, or None if fetch failed
        """
        headers = DEFAULT_HEADERS.copy()
        cookies_dict = self._parse_cookies(cookies_string) if cookies_string else {}

        try:
            response = self.session.get(
                url,
                headers=headers,
                cookies=cookies_dict,
                timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()
            self.last_request_time = time.time()
            return response.text

        except requests.exceptions.RequestException as e:
            print(f"Error fetching {url}: {e}")
            return None

    def _rate_limit(self):
        """Enforce rate limiting between requests"""
        time_since_last = time.time() - self.last_request_time
        if time_since_last < REQUEST_DELAY:
            time.sleep(REQUEST_DELAY - time_since_last)

    def _parse_cookies(self, cookies_string: str) -> Dict[str, str]:
        """
        Parse cookie string into dictionary

        Args:
            cookies_string: Cookie string like "name1=value1; name2=value2"

        Returns:
            Dictionary of cookie name-value pairs
        """
        if not cookies_string:
            return {}

        cookies_dict = {}
        try:
            cookies_dict = {
                item.split('=')[0].strip(): item.split('=', 1)[1].strip()
                for item in cookies_string.split(';')
                if '=' in item
            }
        except Exception as e:
            print(f"Error parsing cookies: {e}")

        return cookies_dict

    def _extract_search_results(self, response_data: Dict) -> List[Dict]:
        """
        Extract article information from search API response

        Args:
            response_data: JSON response from search API

        Returns:
            List of article dictionaries
        """
        articles = []

        try:
            if "result" not in response_data:
                return articles

            result = response_data["result"]

            if not isinstance(result, dict) or "data" not in result:
                return articles

            data = result["data"]

            results_container = data.get("results", {})
            articles_list = results_container.get("results", [])

            for article in articles_list:
                # Only process knowledge articles
                if article.get("meta", {}).get("source") != "knowledge":
                    continue

                meta = article.get("meta", {})

                articles.append({
                    "id": article.get("id", ""),
                    "title": article.get("title", ""),
                    "snippet": article.get("snippet", ""),
                    "link": article.get("link", ""),
                    "number": meta.get("number", {}).get("value", ""),
                    "display_number": meta.get("display_number", {}).get("value", ""),
                    "sys_updated_on": meta.get("sys_updated_on", {}).get("display_value", ""),
                    "score": meta.get("score", 0),
                    "can_read": meta.get("can_read_user_criteria", {}).get("display_value", "Public"),
                })

        except Exception as e:
            print(f"Error extracting search results: {e}")

        return articles

    def parse_curl_command(self, curl_command: str) -> tuple[str, str]:
        """
        Parse curl command to extract cookies and user token

        Args:
            curl_command: cURL command string from browser

        Returns:
            Tuple of (cookies_string, user_token)
        """
        cookies = ""
        user_token = ""

        # Extract Cookie header
        cookie_match = re.search(r"-H ['\"]Cookie: ([^'\"]+)['\"]", curl_command)
        if cookie_match:
            cookies = cookie_match.group(1)

        # Extract X-UserToken header
        token_match = re.search(r"-H ['\"]X-UserToken: ([^'\"]+)['\"]", curl_command)
        if token_match:
            user_token = token_match.group(1)

        return cookies, user_token

    def close(self):
        """Clean up resources"""
        if self.driver:
            try:
                self.driver.quit()
                self.driver_initialized = False
                print("✓ Selenium WebDriver closed")
            except Exception:
                pass

    def __del__(self):
        """Destructor to ensure Selenium closes"""
        self.close()
