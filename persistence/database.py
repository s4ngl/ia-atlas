"""
Enhanced database module with support for article enrichment and topics
Extends the original GraphDB with new tables for Phase 1-2
"""
import psycopg2
from psycopg2 import extras
from typing import Dict, List, Optional
from dataclasses import asdict
from datetime import datetime
import sys
sys.path.append('/mnt/project')
from config import DatabaseConfig


class EnrichedGraphDB:
    """
    Extended database with support for:
    - Article enrichment metadata
    - Topics and topic relationships
    - Information architecture analytics
    """

    def __init__(self):
        """Initialize database connection and create all tables"""
        try:
            self.conn = psycopg2.connect(**asdict(DatabaseConfig()))
            self.conn.autocommit = False
            self.create_enrichment_tables()
            print("✓ Enhanced database connected successfully")
        except psycopg2.Error as e:
            print(f"✗ Database connection failed: {e}")
            raise

    def create_enrichment_tables(self):
        """Create tables for enrichment, topics, and IA analytics"""
        with self.conn.cursor() as cur:
            # Article enrichment table
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
                    LEFT JOIN article_enrichment e ON a.id = e.article_id
                    WHERE e.id IS NULL
                    AND a.content IS NOT NULL
                    AND a.content != ''
                    AND NOT a.content LIKE '[BROKEN ARTICLE:%%'
                    AND NOT a.content LIKE '[MINIMAL CONTENT:%%'
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
                    SELECT e.*, a.title, a.url
                    FROM article_enrichment e
                    JOIN articles a ON e.article_id = a.id
                    ORDER BY e.canonical_topic
                """)
                return [dict(row) for row in cur.fetchall()]
        except psycopg2.Error as e:
            print(f"Error getting enrichments: {e}")
            return []

    def save_topic(self, topic_data: Dict) -> Optional[int]:
        """
        Save or update a topic

        Args:
            topic_data: Dict with keys: name, normalized_name, and optional metrics

        Returns:
            Topic ID or None if failed
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO topics (
                        name, normalized_name, total_articles, indegree,
                        outdegree, prerequisite_count, intent_distribution,
                        complexity_distribution, audience_distribution
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

    def get_enrichment_stats(self) -> Dict:
        """Get statistics about enrichment progress"""
        stats = {
            'total_articles': 0,
            'enriched_articles': 0,
            'unenriched_articles': 0,
            'total_topics': 0,
            'total_relationships': 0
        }

        try:
            with self.conn.cursor() as cur:
                # Total articles with content
                cur.execute("""
                    SELECT COUNT(*) FROM articles
                    WHERE content IS NOT NULL
                    AND content != ''
                    AND NOT content LIKE '[BROKEN ARTICLE:%'
                    AND NOT content LIKE '[MINIMAL CONTENT:%'
                """)
                stats['total_articles'] = cur.fetchone()[0]

                # Enriched articles
                cur.execute("SELECT COUNT(*) FROM article_enrichment")
                stats['enriched_articles'] = cur.fetchone()[0]

                stats['unenriched_articles'] = (
                    stats['total_articles'] - stats['enriched_articles']
                )

                # Topics
                cur.execute("SELECT COUNT(*) FROM topics")
                stats['total_topics'] = cur.fetchone()[0]

                # Relationships
                cur.execute("SELECT COUNT(*) FROM topic_relationships")
                stats['total_relationships'] = cur.fetchone()[0]

        except psycopg2.Error as e:
            print(f"Error getting enrichment stats: {e}")

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
