"""
ServiceNow Knowledge Base Graph Scraper
Main entry point for the application
"""
import sys
import time
from typing import Optional, Dict
from scraper import Fetcher, Frontier, Parser
from graph import GraphDB
from config import SERVICENOW_BASE_URL, SEARCH_KEYWORDS, CRAWL_STRATEGY, MAX_ARTICLES_PER_KEYWORD


def print_banner():
    """Print application banner"""
    print("=" * 80)
    print("  ServiceNow Knowledge Base Graph Scraper")
    print("=" * 80)
    print()


def get_curl_credentials() -> tuple[str, str]:
    """
    Read curl command from curl.txt and extract credentials

    Returns:
        Tuple of (cookies_string, user_token)
    """
    print("Reading curl.txt for authentication credentials...")

    try:
        with open("curl.txt", "r") as f:
            curl_command = f.read().strip()
    except FileNotFoundError:
        print("✗ Error: curl.txt not found")
        print("  Please create curl.txt with your cURL command")
        sys.exit(1)

    if not curl_command:
        print("✗ Error: curl.txt is empty")
        sys.exit(1)

    # Parse curl command to extract credentials
    fetcher = Fetcher()
    cookies, user_token = fetcher.parse_curl_command(curl_command)

    if not cookies or not user_token:
        print("✗ Error: Could not extract cookies and user token from cURL command")
        print("  Make sure you copied the complete cURL command including headers")
        sys.exit(1)

    print("✓ Successfully parsed authentication credentials")
    print()

    return cookies, user_token


def denormalize_url(url: str) -> str:
    """
    Convert normalized frontier URL back to full URL

    Args:
        url: URL (either normalized 'sys_kb_id:XXX' or full URL)

    Returns:
        Full ServiceNow URL
    """
    if url.startswith('sys_kb_id:'):
        sys_kb_id = url.split(':', 1)[1]
        return f"{SERVICENOW_BASE_URL}/kb?id=kb_article_view&sys_kb_id={sys_kb_id}"
    return url


def crawl_article(
    fetcher: Fetcher,
    parser: Parser,
    db: GraphDB,
    url: str,
    cookies: str,
    article_metadata: Optional[dict] = None,
    current_depth: int = 0
) -> tuple[bool, int]:
    """
    Crawl a single article and save to database

    Args:
        fetcher: Fetcher instance
        parser: Parser instance
        db: Database instance
        url: Article URL (may be normalized)
        cookies: Cookie string for authentication
        article_metadata: Optional metadata from search results
        current_depth: Current depth from initial search

    Returns:
        Tuple of (success, depth) where depth is the article's depth level
    """
    # Convert normalized URL to full URL if needed
    full_url = denormalize_url(url)

    print(f"  Fetching: {url}")
    print(f"  Depth: {current_depth}")

    # Fetch HTML using Selenium (for dynamic content)
    html = fetcher.fetch_article_html(full_url, cookies)

    if not html:
        print(f"  ✗ Failed to fetch article")
        return False, current_depth

    # Parse article
    article = parser.extract_article(html, full_url)

    # Skip generic error/redirect pages
    generic_titles = [
        "Knowledge Article View - IUKB",
        "Indiana University - ServiceNow",
        "Login",
        "Page Not Found",
        "Access Denied"
    ]

    # Check if this might be an authentication issue rather than a broken article
    # If the article has metadata from search (meaning it exists), but shows generic title,
    # it might just be an auth issue - don't mark as broken
    if article['title'] in generic_titles:
        if article_metadata and article_metadata.get('title'):
            # We have metadata showing this is a real article, probably just auth issue
            print(f"  ⚠ Warning: Generic page but article exists in search results")
            print(f"     Search title: {article_metadata.get('title')}")
            print(f"     This might be an authentication issue, not a broken article")
            print(f"  ⚠ Skipping without marking as broken (may retry later)")
            return False, current_depth
        else:
            # No metadata, genuinely broken
            print(f"  ⚠ Skipping generic redirect/error page: {article['title']}")

            # Save to database as a broken article so we skip it next time
            # This prevents re-fetching the same broken articles
            article_stub = {
                'url': full_url,
                'title': article['title'],
                'content': f"[BROKEN ARTICLE: {article['title']}]",
                'links': []
            }
            if article_metadata:
                article_stub.update({
                    'number': article_metadata.get('number', ''),
                    'display_number': article_metadata.get('display_number', ''),
                    'snippet': article_metadata.get('snippet', ''),
                    'score': article_metadata.get('score', 0),
                    'can_read': article_metadata.get('can_read', 'Public'),
                })
            article_stub['depth'] = current_depth

            # Save the broken article marker
            db.save_article(article_stub)

            return False, current_depth

    # Skip if content is suspiciously short (likely error page)
    if len(article.get('content', '')) < 100:
        print(f"  ⚠ Skipping page with minimal content (likely error/redirect)")

        # Save to database as a broken article
        article['content'] = f"[MINIMAL CONTENT: {len(article.get('content', ''))} chars]"
        if article_metadata:
            article.update({
                'number': article_metadata.get('number', ''),
                'display_number': article_metadata.get('display_number', ''),
                'snippet': article_metadata.get('snippet', ''),
                'score': article_metadata.get('score', 0),
                'can_read': article_metadata.get('can_read', 'Public'),
            })
        article['depth'] = current_depth
        db.save_article(article)

        return False, current_depth

    # Add metadata from search results if available
    if article_metadata:
        article.update({
            'number': article_metadata.get('number', ''),
            'display_number': article_metadata.get('display_number', ''),
            'snippet': article_metadata.get('snippet', ''),
            'score': article_metadata.get('score', 0),
            'can_read': article_metadata.get('can_read', 'Public'),
        })

    # Add depth information
    article['depth'] = current_depth

    # Save to database
    article_id = db.save_article(article)

    if article_id:
        print(f"  ✓ Saved article (ID: {article_id})")
        print(f"    Title: {article['title']}")
        print(f"    Links found: {len(article['links'])}")
        return True, current_depth
    else:
        print(f"  ✗ Failed to save article")
        return False, current_depth


def crawl_keyword(
    keyword: str,
    max_depth: int,
    cookies: str,
    user_token: str,
    fetcher: Fetcher,
    parser: Parser,
    db: GraphDB,
    frontier: Frontier,
    url_depths: Dict[str, int]
) -> dict:
    """
    Crawl all articles for a single keyword up to max_depth

    Args:
        keyword: Search keyword
        max_depth: Maximum depth to crawl
        cookies: Cookie string for authentication
        user_token: X-UserToken for authentication
        fetcher: Fetcher instance
        parser: Parser instance
        db: Database instance
        frontier: Shared frontier instance (persists across keywords)
        url_depths: Shared URL depths tracker (persists across keywords)

    Returns:
        Dictionary with crawl statistics
    """
    print("\n" + "=" * 80)
    print(f"Starting crawl for keyword: '{keyword}' (max depth: {max_depth})")
    print("=" * 80)

    # Step 1: Perform initial search
    print(f"\nSearching for: '{keyword}'")
    print("-" * 80)

    search_results = fetcher.search_knowledge_base(
        keyword=keyword,
        cookies_string=cookies,
        user_token=user_token
    )

    if not search_results:
        print("✗ No search results found for this keyword")
        return {
            'keyword': keyword,
            'crawled': 0,
            'failed': 0,
            'max_depth': max_depth
        }

    print(f"✓ Found {len(search_results)} articles")

    # Create a mapping of normalized URL -> metadata for later use
    metadata_map = {}
    added_count = 0
    for result in search_results:
        # Construct full URL
        full_url = f"{SERVICENOW_BASE_URL}/kb{result['link']}"

        # Add to frontier (frontier will normalize it)
        if frontier.add(full_url):
            # Get the normalized version for metadata mapping
            normalized = frontier._normalize_url(full_url)
            metadata_map[normalized] = result
            url_depths[normalized] = 0
            added_count += 1

    print(f"Added {added_count} new articles to crawl queue")

    # Step 2: Main crawl loop
    print("\nStarting crawl...")
    print("-" * 80)

    crawled_count = 0
    failed_count = 0
    selenium_errors = 0

    try:
        while not frontier.empty() and crawled_count < MAX_ARTICLES_PER_KEYWORD:
            url = frontier.get_next()

            if not url:
                break

            # Get current depth for this URL
            current_depth = url_depths.get(url, 0)

            # Skip if we've exceeded max depth
            if current_depth > max_depth:
                continue

            # Convert normalized URL to full URL for database lookup
            full_url = denormalize_url(url)

            # Extract sys_kb_id from the URL
            sys_kb_id = db.extract_sys_kb_id(full_url)

            # Check if we already have content for this article (by sys_kb_id OR URL)
            existing_article = None

            # First try by sys_kb_id (most reliable)
            if sys_kb_id:
                existing_article = db.get_article_by_sys_kb_id(sys_kb_id)

            # Fallback to URL lookup
            if not existing_article:
                existing_article = db.get_article_by_url(full_url)

            # Skip if we already have content for this article
            if existing_article and existing_article.get('content') and existing_article['content'].strip():
                # Check if it's a broken article marker
                content = existing_article.get('content', '')
                if content.startswith('[BROKEN ARTICLE:') or content.startswith('[MINIMAL CONTENT:'):
                    print(f"\n[Skipped] Known broken/minimal article")
                    print(f"  URL: {url}")
                    print(f"  Marker: {content[:50]}...")
                    continue

                print(f"\n[Skipped] Article already crawled")
                print(f"  URL: {url}")
                print(f"  Title: {existing_article.get('title', 'Unknown')}")
                print(f"  Existing ID: {existing_article['id']}")

                # Still need to add its links to the frontier if we haven't reached max depth
                if current_depth < max_depth:
                    links = db.get_article_links(existing_article['id'])
                    added = 0
                    for link in links:
                        if frontier.add(link):
                            normalized_link = frontier._normalize_url(link)
                            url_depths[normalized_link] = current_depth + 1
                            added += 1

                    if added > 0:
                        print(f"  ✓ Added {added} linked articles to queue (depth {current_depth + 1})")

                continue

            print(f"\n[{crawled_count + 1}] Crawling article...")

            # Get metadata if available from search results
            metadata = metadata_map.get(url)

            # Crawl the article
            try:
                success, depth = crawl_article(
                    fetcher=fetcher,
                    parser=parser,
                    db=db,
                    url=url,
                    cookies=cookies,
                    article_metadata=metadata,
                    current_depth=current_depth
                )

                if success:
                    crawled_count += 1
                    selenium_errors = 0  # Reset error counter on success

                    # Get the article to find its links
                    article = db.get_article_by_url(full_url)
                    if article:
                        # Get outbound links and add to frontier (if not at max depth)
                        if current_depth < max_depth:
                            links = db.get_article_links(article['id'])
                            added = 0
                            for link in links:
                                if frontier.add(link):
                                    # Set depth for new link
                                    normalized_link = frontier._normalize_url(link)
                                    url_depths[normalized_link] = current_depth + 1
                                    added += 1

                            if added > 0:
                                print(f"  ✓ Added {added} new articles to queue (depth {current_depth + 1})")
                        else:
                            print(f"  → Max depth reached, not adding linked articles")
                else:
                    failed_count += 1

            except Exception as e:
                print(f"  ✗ Error crawling article: {e}")
                failed_count += 1
                selenium_errors += 1

                # If we have multiple consecutive Selenium errors, try to restart driver
                if selenium_errors >= 3:
                    print("  → Multiple Selenium errors detected, attempting to restart driver...")
                    try:
                        fetcher.close()
                        fetcher._init_selenium()
                        selenium_errors = 0
                        print("  ✓ Selenium driver restarted")
                    except Exception as restart_error:
                        print(f"  ✗ Failed to restart Selenium: {restart_error}")
                        print("  → Continuing without Selenium (using fallback)")

            # Print progress
            stats = frontier.get_stats()
            print(f"  Progress: {stats['visited']} visited, {stats['pending']} pending")

    except KeyboardInterrupt:
        print("\n\n✗ Crawl interrupted by user")

    # Return statistics for this keyword
    return {
        'keyword': keyword,
        'crawled': crawled_count,
        'failed': failed_count,
        'max_depth': max_depth,
        'frontier_stats': frontier.get_stats()
    }


def main():
    """Main application logic"""
    print_banner()

    # Get credentials from curl.txt
    cookies, user_token = get_curl_credentials()

    # Load keywords from config
    if not SEARCH_KEYWORDS:
        print("✗ Error: No keywords defined in config.py")
        print("  Please add keywords to SEARCH_KEYWORDS in config.py")
        sys.exit(1)

    print(f"Loaded {len(SEARCH_KEYWORDS)} keyword(s) from config.py:")
    for keyword, depth in SEARCH_KEYWORDS:
        print(f"  • '{keyword}' (max depth: {depth})")
    print()

    # Initialize components
    print("Initializing components...")
    fetcher = Fetcher()
    parser = Parser()

    try:
        db = GraphDB()
    except Exception as e:
        print(f"✗ Failed to initialize database: {e}")
        print("  Please check your database configuration in config.py")
        sys.exit(1)

    print("✓ All components initialized")
    print()

    # Initialize shared frontier and URL depths tracker
    print("Initializing shared frontier...")
    frontier = Frontier(strategy=CRAWL_STRATEGY)
    url_depths: Dict[str, int] = {}

    # Load already-crawled articles from database into frontier
    print("Loading already-crawled articles from database...")
    crawled_urls = db.get_crawled_article_urls()
    if crawled_urls:
        frontier.load_visited_urls(crawled_urls)
        print(f"✓ Loaded {len(crawled_urls)} already-crawled articles")
        print("  These articles will be skipped if encountered again")
    else:
        print("  No previously crawled articles found")
    print()

    # Process each keyword
    all_results = []

    try:
        for keyword, max_depth in SEARCH_KEYWORDS:
            result = crawl_keyword(
                keyword=keyword,
                max_depth=max_depth,
                cookies=cookies,
                user_token=user_token,
                fetcher=fetcher,
                parser=parser,
                db=db,
                frontier=frontier,
                url_depths=url_depths
            )
            all_results.append(result)

    except KeyboardInterrupt:
        print("\n\n✗ Crawl interrupted by user")
    finally:
        # Clean up
        fetcher.close()

    # Step 3: Summary
    print("\n" + "=" * 80)
    print("Overall Crawl Summary")
    print("=" * 80)

    total_crawled = 0
    total_failed = 0
    total_skipped_kb = 0

    for result in all_results:
        print(f"\nKeyword: '{result['keyword']}' (max depth: {result['max_depth']})")
        print(f"  Articles crawled: {result['crawled']}")
        print(f"  Articles failed:  {result['failed']}")
        if 'frontier_stats' in result:
            print(f"  URLs visited:     {result['frontier_stats']['visited']}")
            print(f"  URLs pending:     {result['frontier_stats']['pending']}")
            if 'skipped_kb' in result['frontier_stats']:
                print(f"  KB articles skipped: {result['frontier_stats']['skipped_kb']}")
                total_skipped_kb += result['frontier_stats']['skipped_kb']

        total_crawled += result['crawled']
        total_failed += result['failed']

    print("\n" + "-" * 80)
    print(f"Total articles crawled: {total_crawled}")
    print(f"Total articles failed:  {total_failed}")
    if total_skipped_kb > 0:
        print(f"KB articles skipped:   {total_skipped_kb} (broken/redirect URLs)")
    print()

    db_stats = db.get_stats()
    print("Database Statistics:")
    print(f"Total articles:       {db_stats['total_articles']}")
    print(f"Crawled articles:     {db_stats['crawled_articles']}")
    print(f"Pending articles:     {db_stats['pending_articles']}")
    print(f"Total links:          {db_stats['total_links']}")
    print()

    # Close database connection
    db.close()

    print("✓ Scraper finished")


if __name__ == "__main__":
    main()
