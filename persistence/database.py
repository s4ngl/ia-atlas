"""
Enhanced database module with support for all pipeline phases (0-3)
- Phase 0: Article scraping and link storage
- Phase 1: Article enrichment metadata
- Phase 2: Topics and topic relationships
- Phase 3: Information architecture analytics
"""
import psycopg2
from psycopg2 import extras
from typing import Dict, List, Optional
from dataclasses import asdict
from datetime import datetime
import sys
import re
sys.path.append('/mnt/project')
from config import DatabaseConfig


class EnrichedGraphDB:
    """
    Unified database supporting all pipeline phases:
    - Phase 0 scraping (articles, links)
    - Phase 1-2 analysis (enrichment, topics)
    - Phase 3 IA analytics
    """

    def __init__(self):
        """Initialize database connection and create all tables"""
        try:
            self.conn = psycopg2.connect(**asdict(DatabaseConfig()))
            self.conn.autocommit = False
            self.create_all_tables()
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

    def create_all_tables(self):
        """Create tables for all pipeline phases"""
        with self.conn.cursor() as cur:
            # ================================================================
            # PHASE 0 TABLES: Scraping
            # ================================================================

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

            # Create indexes on articles
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_articles_url
                ON articles(url)
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_articles_sys_kb_id
                ON articles(sys_kb_id)
            """)

            # Add unique constraint on sys_kb_id to prevent duplicates
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

            # ================================================================
            # PHASE 1 TABLE: Article Enrichment
            # ================================================================

            cur.execute("""
                CREATE TABLE IF NOT EXISTS article_enrichment (
                    id SERIAL PRIMARY KEY,
                    article_id INTEGER REFERENCES articles(id) ON DELETE CASCADE,
                    canonical_topic TEXT NOT NULL,
                    keywords TEXT[],
                    intent TEXT,
                    audience TEXT,
                    prerequisites TEXT[],
                    complexity TEXT,
                    enriched_at TIMESTAMP DEFAULT NOW(),
                    llm_model TEXT,
                    UNIQUE(article_id)
                )
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_enrichment_article
                ON article_enrichment(article_id)
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_enrichment_topic
                ON article_enrichment(canonical_topic)
            """)

            # ================================================================
            # PHASE 2 TABLES: Topic Graph
            # ================================================================

            # Topics table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS topics (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    normalized_name TEXT NOT NULL UNIQUE,
                    total_articles INTEGER DEFAULT 0,
                    indegree INTEGER DEFAULT 0,
                    outdegree INTEGER DEFAULT 0,
                    prerequisite_count INTEGER DEFAULT 0,
                    intent_distribution JSONB,
                    complexity_distribution JSONB,
                    audience_distribution JSONB,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_topics_normalized
                ON topics(normalized_name)
            """)

            # Topic-Article mapping
            cur.execute("""
                CREATE TABLE IF NOT EXISTS topic_articles (
                    topic_id INTEGER REFERENCES topics(id) ON DELETE CASCADE,
                    article_id INTEGER REFERENCES articles(id) ON DELETE CASCADE,
                    PRIMARY KEY (topic_id, article_id)
                )
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_topic_articles_topic
                ON topic_articles(topic_id)
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_topic_articles_article
                ON topic_articles(article_id)
            """)

            # Topic relationships table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS topic_relationships (
                    id SERIAL PRIMARY KEY,
                    source_topic_id INTEGER REFERENCES topics(id) ON DELETE CASCADE,
                    target_topic_id INTEGER REFERENCES topics(id) ON DELETE CASCADE,
                    relationship_type TEXT NOT NULL,
                    weight REAL DEFAULT 1.0,
                    supporting_article_count INTEGER DEFAULT 0,
                    link_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(source_topic_id, target_topic_id, relationship_type)
                )
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_topic_rel_source
                ON topic_relationships(source_topic_id)
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_topic_rel_target
                ON topic_relationships(target_topic_id)
            """)

            self.conn.commit()

    # ========================================================================
    # PHASE 0 METHODS: Article Scraping
    # ========================================================================

    def save_article(self, article: Dict) -> Optional[int]:
        """
        Save article and its links to the database (Phase 0)

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
                        existing_id = title_match[0]
                        existing_url = title_match[1]
                        existing_sys_kb_id = title_match[2]
                        existing_updated = title_match[3]

                        print(f"  → Found article with same title but different URL")
                        print(f"  → Existing: {existing_url}")
                        print(f"  → New:      {article['url']}")

                        # If this is a better version (has sys_kb_id when old doesn't)
                        # or if content is more recent, update
                        should_update = (
                            (sys_kb_id and not existing_sys_kb_id) or
                            (article.get('content') and
                             len(article.get('content', '')) > 100)
                        )

                        if should_update:
                            print(f"  → Updating existing article (ID: {existing_id})")
                            cur.execute("""
                                UPDATE articles SET
                                    url = %s,
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
                                article['url'],
                                sys_kb_id,
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

                # Strategy 3: Insert new article
                if not existing_id:
                    cur.execute("""
                        INSERT INTO articles (
                            url, sys_kb_id, title, content, number, display_number,
                            snippet, score, can_read, depth
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (url) DO UPDATE SET
                            title = EXCLUDED.title,
                            content = EXCLUDED.content,
                            sys_kb_id = COALESCE(EXCLUDED.sys_kb_id, articles.sys_kb_id),
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
                        # Conflict occurred, fetch the existing ID
                        cur.execute(
                            "SELECT id FROM articles WHERE url = %s",
                            (article['url'],)
                        )
                        result = cur.fetchone()

                    source_id = result[0] if result else None

                    if source_id and 'links' in article and article['links']:
                        self._save_links(cur, source_id, article['links'])

                    self.conn.commit()
                    return source_id

        except psycopg2.Error as e:
            print(f"Error saving article: {e}")
            self.conn.rollback()
            return None

    def _save_links(self, cur, source_id: int, links: List[str]):
        """Helper method to save article links"""
        for link_url in links:
            try:
                # Extract sys_kb_id from link URL
                link_sys_kb_id = self.extract_sys_kb_id(link_url)

                if link_sys_kb_id:
                    # Prefer sys_kb_id-based insertion
                    cur.execute("""
                        INSERT INTO articles (url, sys_kb_id, title)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (sys_kb_id) DO NOTHING
                        RETURNING id
                    """, (link_url, link_sys_kb_id, 'Pending'))

                    result = cur.fetchone()
                    if result:
                        target_id = result[0]
                    else:
                        # sys_kb_id conflict - get existing ID
                        cur.execute(
                            "SELECT id FROM articles WHERE sys_kb_id = %s",
                            (link_sys_kb_id,)
                        )
                        result = cur.fetchone()
                        if not result:
                            continue
                        target_id = result[0]
                else:
                    # No sys_kb_id - use URL-based approach
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
                        # URL conflict - get existing ID
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
        """Retrieve article by URL"""
        try:
            with self.conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM articles WHERE url = %s", (url,))
                result = cur.fetchone()
                return dict(result) if result else None
        except psycopg2.Error as e:
            print(f"Error retrieving article {url}: {e}")
            return None

    def get_article_by_sys_kb_id(self, sys_kb_id: str) -> Optional[Dict]:
        """Retrieve article by sys_kb_id (canonical identifier)"""
        try:
            with self.conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM articles WHERE sys_kb_id = %s", (sys_kb_id,))
                result = cur.fetchone()
                return dict(result) if result else None
        except psycopg2.Error as e:
            print(f"Error retrieving article by sys_kb_id {sys_kb_id}: {e}")
            return None

    def get_uncrawled_articles(self, limit: int = 100) -> List[Dict]:
        """Get articles that haven't been crawled yet (stub entries)"""
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
        """Get URLs of all fully crawled articles (have content)"""
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    SELECT url, sys_kb_id FROM articles
                    WHERE content IS NOT NULL AND content != ''
                """)
                urls = []
                for row in cur.fetchall():
                    url, sys_kb_id = row
                    urls.append(url)
                return urls
        except psycopg2.Error as e:
            print(f"Error getting crawled article URLs: {e}")
            return []

    def get_article_links(self, article_id: int) -> List[str]:
        """Get all outbound links from an article"""
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

    # ========================================================================
    # PHASE 1 METHODS: Article Enrichment
    # ========================================================================

    def save_enrichment(self, enrichment_data: Dict) -> Optional[int]:
        """
        Save article enrichment data

        Args:
            enrichment_data: Dict with keys: article_id, canonical_topic,
                           keywords, intent, audience, prerequisites,
                           complexity, llm_model

        Returns:
            Enrichment ID or None if failed
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO article_enrichment (
                        article_id, canonical_topic, keywords, intent,
                        audience, prerequisites, complexity, llm_model
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (article_id) DO UPDATE SET
                        canonical_topic = EXCLUDED.canonical_topic,
                        keywords = EXCLUDED.keywords,
                        intent = EXCLUDED.intent,
                        audience = EXCLUDED.audience,
                        prerequisites = EXCLUDED.prerequisites,
                        complexity = EXCLUDED.complexity,
                        enriched_at = NOW(),
                        llm_model = EXCLUDED.llm_model
                    RETURNING id
                """, (
                    enrichment_data['article_id'],
                    enrichment_data['canonical_topic'],
                    enrichment_data.get('keywords', []),
                    enrichment_data.get('intent'),
                    enrichment_data.get('audience'),
                    enrichment_data.get('prerequisites', []),
                    enrichment_data.get('complexity'),
                    enrichment_data.get('llm_model')
                ))

                result = cur.fetchone()
                self.conn.commit()
                return result[0] if result else None

        except psycopg2.Error as e:
            print(f"Error saving enrichment: {e}")
            self.conn.rollback()
            return None

    def get_enrichment_by_article(self, article_id: int) -> Optional[Dict]:
        """Get enrichment data for an article"""
        try:
            with self.conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM article_enrichment WHERE article_id = %s",
                    (article_id,)
                )
                result = cur.fetchone()
                return dict(result) if result else None
        except psycopg2.Error as e:
            print(f"Error getting enrichment: {e}")
            return None

    def get_unenriched_articles(self, limit: int = 100) -> List[Dict]:
        """
        Get articles that haven't been enriched yet
        Only returns articles with actual content
        """
        try:
            with self.conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT a.id, a.url, a.title, a.content, a.snippet
                    FROM articles a
                    LEFT JOIN article_enrichment ae ON a.id = ae.article_id
                    WHERE ae.id IS NULL
                    AND a.content IS NOT NULL
                    AND a.content != ''
                    AND NOT a.content LIKE '[BROKEN ARTICLE:%'
                    AND NOT a.content LIKE '[MINIMAL CONTENT:%'
                    ORDER BY a.id
                    LIMIT %s
                """, (limit,))
                return [dict(row) for row in cur.fetchall()]
        except psycopg2.Error as e:
            print(f"Error getting unenriched articles: {e}")
            return []

    def get_all_enrichments(self) -> List[Dict]:
        """Get all article enrichments"""
        try:
            with self.conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT ae.*, a.title, a.url
                    FROM article_enrichment ae
                    JOIN articles a ON ae.article_id = a.id
                    ORDER BY ae.id
                """)
                return [dict(row) for row in cur.fetchall()]
        except psycopg2.Error as e:
            print(f"Error getting enrichments: {e}")
            return []

    # ========================================================================
    # PHASE 2 METHODS: Topic Graph
    # ========================================================================

    def save_topic(self, topic_data: Dict) -> Optional[int]:
        """
        Save or update a topic

        Args:
            topic_data: Dict with keys: name, normalized_name, total_articles,
                       indegree, outdegree, prerequisite_count,
                       intent_distribution, complexity_distribution, audience_distribution

        Returns:
            Topic ID or None if failed
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO topics (
                        name, normalized_name, total_articles,
                        indegree, outdegree, prerequisite_count,
                        intent_distribution, complexity_distribution, audience_distribution
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (normalized_name) DO UPDATE SET
                        name = EXCLUDED.name,
                        total_articles = EXCLUDED.total_articles,
                        indegree = EXCLUDED.indegree,
                        outdegree = EXCLUDED.outdegree,
                        prerequisite_count = EXCLUDED.prerequisite_count,
                        intent_distribution = EXCLUDED.intent_distribution,
                        complexity_distribution = EXCLUDED.complexity_distribution,
                        audience_distribution = EXCLUDED.audience_distribution,
                        updated_at = NOW()
                    RETURNING id
                """, (
                    topic_data['name'],
                    topic_data['normalized_name'],
                    topic_data.get('total_articles', 0),
                    topic_data.get('indegree', 0),
                    topic_data.get('outdegree', 0),
                    topic_data.get('prerequisite_count', 0),
                    psycopg2.extras.Json(topic_data.get('intent_distribution', {})),
                    psycopg2.extras.Json(topic_data.get('complexity_distribution', {})),
                    psycopg2.extras.Json(topic_data.get('audience_distribution', {}))
                ))

                result = cur.fetchone()
                self.conn.commit()
                return result[0] if result else None

        except psycopg2.Error as e:
            print(f"Error saving topic: {e}")
            self.conn.rollback()
            return None

    def link_article_to_topic(self, topic_id: int, article_id: int):
        """Create a link between a topic and an article"""
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO topic_articles (topic_id, article_id)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING
                """, (topic_id, article_id))
                self.conn.commit()
        except psycopg2.Error as e:
            print(f"Error linking article to topic: {e}")
            self.conn.rollback()

    def save_topic_relationship(self, relationship_data: Dict) -> Optional[int]:
        """
        Save a relationship between two topics

        Args:
            relationship_data: Dict with keys: source_topic_id, target_topic_id,
                             relationship_type, weight, supporting_article_count, link_count

        Returns:
            Relationship ID or None if failed
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO topic_relationships (
                        source_topic_id, target_topic_id, relationship_type,
                        weight, supporting_article_count, link_count
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (source_topic_id, target_topic_id, relationship_type)
                    DO UPDATE SET
                        weight = EXCLUDED.weight,
                        supporting_article_count = EXCLUDED.supporting_article_count,
                        link_count = EXCLUDED.link_count
                    RETURNING id
                """, (
                    relationship_data['source_topic_id'],
                    relationship_data['target_topic_id'],
                    relationship_data['relationship_type'],
                    relationship_data.get('weight', 1.0),
                    relationship_data.get('supporting_article_count', 0),
                    relationship_data.get('link_count', 0)
                ))

                result = cur.fetchone()
                self.conn.commit()
                return result[0] if result else None

        except psycopg2.Error as e:
            print(f"Error saving topic relationship: {e}")
            self.conn.rollback()
            return None

    def get_all_topics(self) -> List[Dict]:
        """Get all topics"""
        try:
            with self.conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM topics ORDER BY total_articles DESC")
                return [dict(row) for row in cur.fetchall()]
        except psycopg2.Error as e:
            print(f"Error getting topics: {e}")
            return []

    def get_topic_by_normalized_name(self, normalized_name: str) -> Optional[Dict]:
        """Get a topic by its normalized name"""
        try:
            with self.conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM topics WHERE normalized_name = %s",
                    (normalized_name,)
                )
                result = cur.fetchone()
                return dict(result) if result else None
        except psycopg2.Error as e:
            print(f"Error getting topic: {e}")
            return None

    def get_topic_relationships(self, topic_id: Optional[int] = None) -> List[Dict]:
        """
        Get topic relationships

        Args:
            topic_id: If provided, only get relationships involving this topic

        Returns:
            List of relationship dictionaries
        """
        try:
            with self.conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
                if topic_id:
                    cur.execute("""
                        SELECT r.*,
                               t1.name as source_name,
                               t2.name as target_name
                        FROM topic_relationships r
                        JOIN topics t1 ON r.source_topic_id = t1.id
                        JOIN topics t2 ON r.target_topic_id = t2.id
                        WHERE r.source_topic_id = %s OR r.target_topic_id = %s
                    """, (topic_id, topic_id))
                else:
                    cur.execute("""
                        SELECT r.*,
                               t1.name as source_name,
                               t2.name as target_name
                        FROM topic_relationships r
                        JOIN topics t1 ON r.source_topic_id = t1.id
                        JOIN topics t2 ON r.target_topic_id = t2.id
                    """)
                return [dict(row) for row in cur.fetchall()]
        except psycopg2.Error as e:
            print(f"Error getting topic relationships: {e}")
            return []

    def get_articles_by_topic(self, topic_id: int) -> List[Dict]:
        """Get all articles for a given topic"""
        try:
            with self.conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT a.*
                    FROM articles a
                    JOIN topic_articles ta ON a.id = ta.article_id
                    WHERE ta.topic_id = %s
                """, (topic_id,))
                return [dict(row) for row in cur.fetchall()]
        except psycopg2.Error as e:
            print(f"Error getting articles by topic: {e}")
            return []

    # ========================================================================
    # STATISTICS & UTILITIES
    # ========================================================================

    def get_stats(self) -> Dict:
        """
        Get comprehensive database statistics across all phases

        Returns:
            Dictionary with stats about articles, links, enrichment, topics
        """
        stats = {
            # Phase 0
            'total_articles': 0,
            'crawled_articles': 0,
            'pending_articles': 0,
            'total_links': 0,
            # Phase 1
            'enriched_articles': 0,
            'unenriched_articles': 0,
            # Phase 2
            'total_topics': 0,
            'total_relationships': 0
        }

        try:
            with self.conn.cursor() as cur:
                # Total articles
                cur.execute("SELECT COUNT(*) FROM articles")
                stats['total_articles'] = cur.fetchone()[0]

                # Crawled articles (have content)
                cur.execute("""
                    SELECT COUNT(*) FROM articles
                    WHERE content IS NOT NULL
                    AND content != ''
                    AND NOT content LIKE '[BROKEN ARTICLE:%'
                    AND NOT content LIKE '[MINIMAL CONTENT:%'
                """)
                stats['crawled_articles'] = cur.fetchone()[0]

                # Pending articles
                stats['pending_articles'] = (
                    stats['total_articles'] - stats['crawled_articles']
                )

                # Total links
                cur.execute("SELECT COUNT(*) FROM links")
                stats['total_links'] = cur.fetchone()[0]

                # Enriched articles
                cur.execute("SELECT COUNT(*) FROM article_enrichment")
                stats['enriched_articles'] = cur.fetchone()[0]

                # Unenriched articles (with valid content)
                stats['unenriched_articles'] = (
                    stats['crawled_articles'] - stats['enriched_articles']
                )

                # Topics
                cur.execute("SELECT COUNT(*) FROM topics")
                stats['total_topics'] = cur.fetchone()[0]

                # Relationships
                cur.execute("SELECT COUNT(*) FROM topic_relationships")
                stats['total_relationships'] = cur.fetchone()[0]

        except psycopg2.Error as e:
            print(f"Error getting stats: {e}")

        return stats

    def get_enrichment_stats(self) -> Dict:
        """Get statistics about enrichment progress (backwards compatible)"""
        return self.get_stats()

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
