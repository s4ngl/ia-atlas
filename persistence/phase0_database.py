"""
Database module - handles PostgreSQL graph storage
Stores articles and their link relationships
"""
import psycopg2
from psycopg2 import pool, extras
from typing import Dict, List, Optional
from dataclasses import asdict
from datetime import datetime
from config import DatabaseConfig
import re


class GraphDB:
    """
    Manages PostgreSQL database for storing article graph
    """

    def __init__(self):
        """Initialize database connection and create tables"""
        try:
            self.conn = psycopg2.connect(**asdict(DatabaseConfig()))
            self.conn.autocommit = False  # Use transactions
            self.create_tables()
            print("✓ Database connected successfully")
        except psycopg2.Error as e:
            print(f"✗ Database connection failed: {e}")
            raise

    @staticmethod
    def extract_sys_kb_id(url: str) -> Optional[str]:
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

    def create_tables(self):
        """Create the articles and links tables if they don't exist"""
        with self.conn.cursor() as cur:
            # Articles table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS articles (
                    id SERIAL PRIMARY KEY,
                    url TEXT UNIQUE NOT NULL,
                    sys_kb_id TEXT,
                    title TEXT,
                    content TEXT,
                    number TEXT,
                    display_number TEXT,
                    snippet TEXT,
                    score REAL,
                    can_read TEXT,
                    depth INTEGER DEFAULT 0,
                    crawled_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)

            # Create index on URL for faster lookups
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_articles_url
                ON articles(url)
            """)

            # Create index on sys_kb_id for canonical URL lookups
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_articles_sys_kb_id
                ON articles(sys_kb_id)
            """)

            # Add unique constraint on sys_kb_id to prevent duplicates
            # Use IF NOT EXISTS pattern for constraint
            cur.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint
                        WHERE conname = 'unique_sys_kb_id'
                    ) THEN
                        ALTER TABLE articles ADD CONSTRAINT unique_sys_kb_id UNIQUE (sys_kb_id);
                    END IF;
                END $$;
            """)

            # Links table (represents edges in the graph)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS links (
                    source_id INTEGER REFERENCES articles(id) ON DELETE CASCADE,
                    target_id INTEGER REFERENCES articles(id) ON DELETE CASCADE,
                    created_at TIMESTAMP DEFAULT NOW(),
                    PRIMARY KEY (source_id, target_id)
                )
            """)

            # Create indexes for better query performance
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_links_source
                ON links(source_id)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_links_target
                ON links(target_id)
            """)

            self.conn.commit()

    def save_article(self, article: Dict) -> Optional[int]:
        """
        Save article and its links to the database

        Args:
            article: Dictionary containing article data
                Required keys: 'url', 'title', 'content', 'links'
                Optional keys: 'number', 'display_number', 'snippet', 'score', 'can_read'

        Returns:
            Article ID if saved successfully, None otherwise
        """
        try:
            with self.conn.cursor() as cur:
                # Extract sys_kb_id from URL
                sys_kb_id = self.extract_sys_kb_id(article['url'])

                # Strategy 1: Check by sys_kb_id (most reliable for same article)
                existing_id = None
                if sys_kb_id:
                    cur.execute(
                        "SELECT id, url, title FROM articles WHERE sys_kb_id = %s",
                        (sys_kb_id,)
                    )
                    existing = cur.fetchone()

                    if existing:
                        # Article with this sys_kb_id already exists
                        existing_id = existing[0]
                        existing_url = existing[1]
                        existing_title = existing[2]

                        print(f"  → Found existing article with same sys_kb_id")
                        print(f"  → Updating existing article (ID: {existing_id})")

                        # Update the existing article with new content
                        cur.execute("""
                            UPDATE articles SET
                                title = %s,
                                content = %s,
                                number = %s,
                                display_number = %s,
                                snippet = %s,
                                score = %s,
                                can_read = %s,
                                depth = %s,
                                updated_at = NOW()
                            WHERE id = %s
                            RETURNING id
                        """, (
                            article.get('title', existing_title),
                            article.get('content', ''),
                            article.get('number', ''),
                            article.get('display_number', ''),
                            article.get('snippet', ''),
                            article.get('score', 0.0),
                            article.get('can_read', 'Public'),
                            article.get('depth', 0),
                            existing_id
                        ))

                        result = cur.fetchone()
                        source_id = result[0] if result else existing_id

                        # Save links
                        if 'links' in article and article['links']:
                            self._save_links(cur, source_id, article['links'])

                        self.conn.commit()
                        return source_id

                # Strategy 2: Check by title (for different versions of same article)
                # Only if we didn't find by sys_kb_id and title is meaningful (not "Pending")
                # Also skip generic error page titles
                generic_titles = {
                    'Pending',
                    'Knowledge Article View - IUKB',
                    'Indiana University - ServiceNow',
                    'Login',
                    'Page Not Found',
                    'Access Denied'
                }

                if (not existing_id and
                    article.get('title') and
                    article['title'] not in generic_titles):

                    cur.execute(
                        """SELECT id, url, sys_kb_id, updated_at
                           FROM articles
                           WHERE title = %s
                           AND title NOT IN ('Pending', 'Knowledge Article View - IUKB',
                                           'Indiana University - ServiceNow', 'Login',
                                           'Page Not Found', 'Access Denied')""",
                        (article['title'],)
                    )
                    title_match = cur.fetchone()

                    if title_match:
                        # Found article with same title
                        existing_id = title_match[0]
                        existing_url = title_match[1]
                        existing_sys_kb_id = title_match[2]

                        # Only update if this version has content
                        if article.get('content') and article['content'].strip():
                            print(f"  → Found existing article with same title: {article['title']}")
                            print(f"  → Updating existing article (ID: {existing_id})")

                            # Update the existing article
                            cur.execute("""
                                UPDATE articles SET
                                    sys_kb_id = COALESCE(%s, sys_kb_id),
                                    content = %s,
                                    number = %s,
                                    display_number = %s,
                                    snippet = %s,
                                    score = %s,
                                    can_read = %s,
                                    depth = %s,
                                    updated_at = NOW()
                                WHERE id = %s
                                RETURNING id
                            """, (
                                sys_kb_id,  # Only update sys_kb_id if we have one
                                article.get('content', ''),
                                article.get('number', ''),
                                article.get('display_number', ''),
                                article.get('snippet', ''),
                                article.get('score', 0.0),
                                article.get('can_read', 'Public'),
                                article.get('depth', 0),
                                existing_id
                            ))

                            result = cur.fetchone()
                            source_id = result[0] if result else existing_id

                            # Save links
                            if 'links' in article and article['links']:
                                self._save_links(cur, source_id, article['links'])

                            self.conn.commit()
                            return source_id

                # No existing article found - insert new one
                cur.execute("""
                    INSERT INTO articles (
                        url, sys_kb_id, title, content, number, display_number,
                        snippet, score, can_read, depth, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (url) DO UPDATE SET
                        sys_kb_id = COALESCE(EXCLUDED.sys_kb_id, articles.sys_kb_id),
                        title = EXCLUDED.title,
                        content = EXCLUDED.content,
                        number = EXCLUDED.number,
                        display_number = EXCLUDED.display_number,
                        snippet = EXCLUDED.snippet,
                        score = EXCLUDED.score,
                        can_read = EXCLUDED.can_read,
                        depth = EXCLUDED.depth,
                        updated_at = NOW()
                    RETURNING id
                """, (
                    article['url'],
                    sys_kb_id,
                    article.get('title', ''),
                    article.get('content', ''),
                    article.get('number', ''),
                    article.get('display_number', ''),
                    article.get('snippet', ''),
                    article.get('score', 0.0),
                    article.get('can_read', 'Public'),
                    article.get('depth', 0)
                ))

                result = cur.fetchone()
                if not result:
                    return None

                source_id = result[0]

                # Save links
                if 'links' in article and article['links']:
                    self._save_links(cur, source_id, article['links'])

                self.conn.commit()
                return source_id

        except psycopg2.Error as e:
            print(f"Error saving article {article.get('url', 'unknown')}: {e}")
            self.conn.rollback()
            return None

    def _save_links(self, cur, source_id: int, links: List[str]):
        """
        Save links from an article to the database

        Args:
            cur: Database cursor
            source_id: ID of source article
            links: List of target URLs
        """
        for link_url in links:
            try:
                # Extract sys_kb_id from the link URL
                sys_kb_id = self.extract_sys_kb_id(link_url)

                # If we have sys_kb_id, check if article already exists
                if sys_kb_id:
                    cur.execute(
                        "SELECT id FROM articles WHERE sys_kb_id = %s",
                        (sys_kb_id,)
                    )
                    existing = cur.fetchone()

                    if existing:
                        # Article already exists, use its ID
                        target_id = existing[0]
                    else:
                        # Create new stub with sys_kb_id
                        cur.execute("""
                            INSERT INTO articles (url, sys_kb_id, title)
                            VALUES (%s, %s, %s)
                            ON CONFLICT (url) DO NOTHING
                            RETURNING id
                        """, (link_url, sys_kb_id, 'Pending'))

                        result = cur.fetchone()
                        if result:
                            target_id = result[0]
                        else:
                            # URL conflict but different sys_kb_id shouldn't happen
                            # but if it does, get the existing ID
                            cur.execute(
                                "SELECT id FROM articles WHERE url = %s",
                                (link_url,)
                            )
                            result = cur.fetchone()
                            if not result:
                                continue
                            target_id = result[0]
                else:
                    # No sys_kb_id found - use URL-based approach (fallback)
                    cur.execute("""
                        INSERT INTO articles (url, title)
                        VALUES (%s, %s)
                        ON CONFLICT (url) DO NOTHING
                        RETURNING id
                    """, (link_url, 'Pending'))

                    result = cur.fetchone()
                    if result:
                        target_id = result[0]
                    else:
                        # Article already exists, fetch its ID
                        cur.execute(
                            "SELECT id FROM articles WHERE url = %s",
                            (link_url,)
                        )
                        result = cur.fetchone()
                        if not result:
                            continue
                        target_id = result[0]

                # Create link
                cur.execute("""
                    INSERT INTO links (source_id, target_id)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING
                """, (source_id, target_id))

            except psycopg2.Error as e:
                print(f"Error saving link {link_url}: {e}")
                continue

    def get_article_by_url(self, url: str) -> Optional[Dict]:
        """
        Retrieve article by URL

        Args:
            url: Article URL

        Returns:
            Article dictionary or None if not found
        """
        try:
            with self.conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM articles WHERE url = %s",
                    (url,)
                )
                result = cur.fetchone()
                return dict(result) if result else None
        except psycopg2.Error as e:
            print(f"Error retrieving article {url}: {e}")
            return None

    def get_article_by_sys_kb_id(self, sys_kb_id: str) -> Optional[Dict]:
        """
        Retrieve article by sys_kb_id (canonical identifier)

        Args:
            sys_kb_id: Article sys_kb_id

        Returns:
            Article dictionary or None if not found
        """
        try:
            with self.conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM articles WHERE sys_kb_id = %s",
                    (sys_kb_id,)
                )
                result = cur.fetchone()
                return dict(result) if result else None
        except psycopg2.Error as e:
            print(f"Error retrieving article by sys_kb_id {sys_kb_id}: {e}")
            return None

    def get_uncrawled_articles(self, limit: int = 100) -> List[Dict]:
        """
        Get articles that haven't been crawled yet (stub entries)

        Args:
            limit: Maximum number of articles to return

        Returns:
            List of article dictionaries
        """
        try:
            with self.conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM articles
                    WHERE content IS NULL OR content = ''
                    LIMIT %s
                """, (limit,))
                return [dict(row) for row in cur.fetchall()]
        except psycopg2.Error as e:
            print(f"Error getting uncrawled articles: {e}")
            return []

    def get_crawled_article_urls(self) -> List[str]:
        """
        Get URLs of all articles that have been fully crawled (have content)
        Used to pre-populate the frontier's visited set on startup

        Returns URLs in a format that can be normalized by the frontier.

        Returns:
            List of URLs (preferring sys_kb_id format when available)
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    SELECT url, sys_kb_id FROM articles
                    WHERE content IS NOT NULL AND content != ''
                """)
                urls = []
                for row in cur.fetchall():
                    url, sys_kb_id = row
                    # If we have sys_kb_id, construct a URL with it for better normalization
                    if sys_kb_id:
                        urls.append(url)
                    else:
                        # Fallback to the stored URL
                        urls.append(url)
                return urls
        except psycopg2.Error as e:
            print(f"Error getting crawled article URLs: {e}")
            return []

    def get_article_links(self, article_id: int) -> List[str]:
        """
        Get all outbound links from an article

        Args:
            article_id: Article ID

        Returns:
            List of target URLs
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    SELECT a.url
                    FROM links l
                    JOIN articles a ON l.target_id = a.id
                    WHERE l.source_id = %s
                """, (article_id,))
                return [row[0] for row in cur.fetchall()]
        except psycopg2.Error as e:
            print(f"Error getting article links: {e}")
            return []

    def get_stats(self) -> Dict:
        """
        Get database statistics

        Returns:
            Dictionary with stats about articles and links
        """
        stats = {
            'total_articles': 0,
            'crawled_articles': 0,
            'pending_articles': 0,
            'total_links': 0
        }

        try:
            with self.conn.cursor() as cur:
                # Total articles
                cur.execute("SELECT COUNT(*) FROM articles")
                stats['total_articles'] = cur.fetchone()[0]

                # Crawled articles (have content)
                cur.execute("""
                    SELECT COUNT(*) FROM articles
                    WHERE content IS NOT NULL AND content != ''
                """)
                stats['crawled_articles'] = cur.fetchone()[0]

                # Pending articles
                stats['pending_articles'] = (
                    stats['total_articles'] - stats['crawled_articles']
                )

                # Total links
                cur.execute("SELECT COUNT(*) FROM links")
                stats['total_links'] = cur.fetchone()[0]

        except psycopg2.Error as e:
            print(f"Error getting stats: {e}")

        return stats

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            print("✓ Database connection closed")

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()
