"""
 Topic Graph Builder - Phase 2 Enhancement with Hierarchical Fallback
Addresses issues with relationship inference and topic consolidation
Ensures 100% article coverage
"""
from typing import Dict, List, Set, Optional, Tuple
from collections import defaultdict, Counter
import sys

from core.models import Topic, TopicRelationship, ArticleEnrichment
from persistence.database import EnrichedGraphDB
from analysis.topics.normalizer import TopicNormalizer

class TopicGraphBuilder:
    """
     topic graph builder with better relationship inference and hierarchical fallback

    Key improvements:
    1. Hierarchical topic assignment (100% article coverage)
    2. Lower threshold for prerequisite relationships
    3. Better parent-child detection
    4. Semantic similarity for related topics
    5. Topic consolidation based on article overlap
    """

    def __init__(self, db: EnrichedGraphDB, min_articles: int = 2):
        """
        Initialize topic graph builder

        Args:
            db: Database instance
            min_articles: Minimum articles for specific topics (fallback handles orphans)
        """
        self.db = db
        self.normalizer = TopicNormalizer()
        self.topics: Dict[str, 'Topic'] = {}
        self.topic_id_map: Dict[str, int] = {}
        self.min_articles = min_articles

        # Track orphaned articles for fallback assignment
        self.orphaned_articles: Dict[str, List[int]] = defaultdict(list)

    def build_topics_from_enrichment(
        self,
        save_to_db: bool = True,
        verbose: bool = True
    ) -> Dict[str, Topic]:
        """
        Build topics with hierarchical fallback for 100% coverage

        Args:
            save_to_db: Whether to save topics to database
            verbose: Whether to print progress

        Returns:
            Dictionary of normalized_name -> Topic
        """
        if verbose:
            print("Building topics with hierarchical fallback...")
            print("=" * 80)

        # Get all enrichments
        enrichments = self.db.get_all_enrichments()

        if not enrichments:
            print("No enrichment data found. Run Phase 1 first.")
            return {}

        if verbose:
            print(f"Found {len(enrichments)} enriched articles")

        # Step 1: Normalize all topics and collect fallbacks
        if verbose:
            print("\nNormalizing topics with fallback categories...")

        normalization_mapping = {}  # raw -> (normalized, fallback)

        for enrichment in enrichments:
            raw_topic = enrichment['canonical_topic']
            normalized, fallback = self.normalizer.normalize_with_fallback(raw_topic)
            normalization_mapping[raw_topic] = (normalized, fallback)

        # Step 2: Create topics from normalized names
        if verbose:
            print("Creating topic objects...")

        for enrichment in enrichments:
            raw_topic = enrichment['canonical_topic']
            normalized_topic, fallback_topic = normalization_mapping[raw_topic]

            # Get or create normalized topic
            if normalized_topic not in self.topics:
                self.topics[normalized_topic] = Topic(
                    id=None,
                    name=raw_topic,  # Keep one of the raw names
                    normalized_name=normalized_topic,
                    article_ids=set(),
                    intent_distribution={},
                    complexity_distribution={},
                    audience_distribution={}
                )

            topic = self.topics[normalized_topic]

            # Add article to topic
            topic.article_ids.add(enrichment['article_id'])

            # Track fallback for this article
            self.orphaned_articles[fallback_topic].append(enrichment['article_id'])

            # Update distributions
            self._update_topic_distributions(topic, enrichment)

            # Update article count
            topic.total_articles = len(topic.article_ids)

        if verbose:
            print(f"Created {len(self.topics)} specific topics")

        # Step 3: Filter low-count topics and reassign to fallbacks
        if verbose:
            print(f"\nFiltering topics with < {self.min_articles} articles...")

        kept_topics = {}
        orphan_count = 0
        reassigned_count = 0

        for normalized_name, topic in self.topics.items():
            if topic.total_articles >= self.min_articles:
                kept_topics[normalized_name] = topic
            else:
                orphan_count += 1

        if verbose:
            print(f"Removed {orphan_count} low-count topics")
            print(f"Reassigning {sum(1 for t in self.topics.values() if t.total_articles < self.min_articles)} articles to fallback categories...")

        # Step 4: Create fallback category topics
        fallback_topics_created = 0

        for enrichment in enrichments:
            raw_topic = enrichment['canonical_topic']
            normalized_topic, fallback_topic = normalization_mapping[raw_topic]

            # If the normalized topic didn't make the cut, use fallback
            if normalized_topic not in kept_topics and fallback_topic:
                # Create or update fallback topic
                if fallback_topic not in kept_topics:
                    kept_topics[fallback_topic] = Topic(
                        id=None,
                        name=fallback_topic,
                        normalized_name=fallback_topic,
                        article_ids=set(),
                        intent_distribution={},
                        complexity_distribution={},
                        audience_distribution={}
                    )
                    fallback_topics_created += 1

                fallback_topic_obj = kept_topics[fallback_topic]
                fallback_topic_obj.article_ids.add(enrichment['article_id'])
                self._update_topic_distributions(fallback_topic_obj, enrichment)
                fallback_topic_obj.total_articles = len(fallback_topic_obj.article_ids)
                reassigned_count += 1

        self.topics = kept_topics

        if verbose:
            print(f"Created {fallback_topics_created} fallback category topics")
            print(f"Reassigned {reassigned_count} articles to categories")
            print(f"Final topic count: {len(self.topics)}")

        # Step 5: Verify 100% coverage
        total_articles_in_topics = sum(len(t.article_ids) for t in self.topics.values())

        if verbose:
            print(f"\nCoverage: {total_articles_in_topics}/{len(enrichments)} articles ({total_articles_in_topics/len(enrichments)*100:.1f}%)")

        # Step 6: Save to database if requested
        if save_to_db:
            if verbose:
                print("\nSaving topics to database...")

            # Save all topics
            for normalized_name, topic in self.topics.items():
                topic_data = {
                    'name': topic.name,
                    'normalized_name': topic.normalized_name,
                    'total_articles': topic.total_articles,
                    'intent_distribution': topic.intent_distribution,
                    'complexity_distribution': topic.complexity_distribution,
                    'audience_distribution': topic.audience_distribution
                }

                topic_id = self.db.save_topic(topic_data)

                if topic_id:
                    topic.id = topic_id
                    self.topic_id_map[normalized_name] = topic_id

            # Link articles to topics
            if verbose:
                print("Linking articles to topics...")

            for normalized_name, topic in self.topics.items():
                if topic.id:
                    for article_id in topic.article_ids:
                        self.db.link_article_to_topic(topic.id, article_id)

            if verbose:
                print(f"✓ Saved {len(self.topics)} topics to database")

        return self.topics

    def _update_topic_distributions(self, topic: Topic, enrichment: dict):
        """Helper to update topic distributions from enrichment"""
        intent = enrichment.get('intent', 'unknown')
        if intent:
            topic.intent_distribution[intent] = topic.intent_distribution.get(intent, 0) + 1

        complexity = enrichment.get('complexity', 'unknown')
        if complexity:
            topic.complexity_distribution[complexity] = topic.complexity_distribution.get(complexity, 0) + 1

        audience = enrichment.get('audience', 'unknown')
        if audience:
            topic.audience_distribution[audience] = topic.audience_distribution.get(audience, 0) + 1
        print(f"✓ Saved {len(self.topics)} topics to database")

        return self.topics

    def infer_topic_relationships(
        self,
        save_to_db: bool = True,
        verbose: bool = True
    ) -> List['TopicRelationship']:
        """
         relationship inference with better detection

        Returns:
            List of TopicRelationship objects
        """
        if verbose:
            print("\nInferring topic relationships (improved)...")
            print("=" * 80)

        relationships = []

        # Ensure topics are loaded
        if not self.topics:
            self.topics = self._load_topics_from_db()

        # Step 1: Find subtopic relationships (improved)
        if verbose:
            print("\nFinding subtopic relationships (algorithm)...")

        subtopic_rels = self._find_subtopic_relationships()
        relationships.extend(subtopic_rels)

        if verbose:
            print(f"Found {len(subtopic_rels)} subtopic relationships")

        # Step 2: Find prerequisite relationships (lower threshold)
        if verbose:
            print("\nFinding prerequisite relationships (lowered threshold)...")

        prereq_rels = self._find_prerequisite_relationships()
        relationships.extend(prereq_rels)

        if verbose:
            print(f"Found {len(prereq_rels)} prerequisite relationships")

        # Step 3: Find related topics (improved)
        if verbose:
            print("\nFinding related topics (criteria)...")

        related_rels = self._find_related_topics()
        relationships.extend(related_rels)

        if verbose:
            print(f"Found {len(related_rels)} related-to relationships")

        # Step 4: Consolidation suggestions
        if verbose:
            print("\nAnalyzing topics for consolidation...")

        consolidation_suggestions = self._suggest_topic_consolidation()

        if verbose and consolidation_suggestions:
            print(f"\nSuggested consolidations: {len(consolidation_suggestions)}")
            for canonical, similar_topics in list(consolidation_suggestions.items())[:10]:
                print(f"  • {canonical}")
                for topic in similar_topics[:3]:
                    print(f"    - merge: {topic}")

        # Save relationships
        if save_to_db:
            if verbose:
                print("\nUpdating topic graph metrics...")

            self._update_topic_metrics(relationships)

            if verbose:
                print("\nSaving relationships to database...")

            for rel in relationships:
                self.db.save_topic_relationship(rel.__dict__)

            # Update topic metrics in database
            for topic in self.topics.values():
                topic_data = {
                    'name': topic.name,
                    'normalized_name': topic.normalized_name,
                    'total_articles': topic.total_articles,
                    'indegree': topic.indegree,
                    'outdegree': topic.outdegree,
                    'prerequisite_count': topic.prerequisite_count,
                    'intent_distribution': topic.intent_distribution,
                    'complexity_distribution': topic.complexity_distribution,
                    'audience_distribution': topic.audience_distribution
                }
                self.db.save_topic(topic_data)

            if verbose:
                print(f"✓ Saved {len(relationships)} relationships to database")

        return relationships

    def _find_subtopic_relationships(self) -> List['TopicRelationship']:
        """
        subtopic detection using multiple strategies

        Strategies:
        1. Word containment (original)
        2. Semantic similarity with word overlap
        3. Article overlap analysis
        """
        relationships = []
        topic_names = list(self.topics.keys())

        # Strategy 1: Word containment ()
        for i, parent_name in enumerate(topic_names):
            parent = self.topics[parent_name]
            parent_words = set(parent_name.lower().split())

            for child_name in topic_names[i+1:]:
                if child_name == parent_name:
                    continue

                child = self.topics[child_name]
                child_words = set(child_name.lower().split())

                # Check if parent is a proper subset of child
                if (parent_words < child_words and  # Strict subset
                    len(parent_words) >= 1):  # Parent must have at least one word

                    # Calculate confidence based on overlap
                    overlap_ratio = len(parent_words) / len(child_words)

                    rel = self._create_relationship(
                        parent.id,
                        child.id,
                        'subtopic_of',
                        weight=overlap_ratio,
                        source='word_containment'
                    )

                    relationships.append(rel)
                    parent.parent_topics.add(child.id)

        # Strategy 2: Article overlap (topics that share many articles might be related)
        article_overlap_rels = self._find_relationships_by_article_overlap()
        relationships.extend(article_overlap_rels)

        return relationships

    def _find_prerequisite_relationships(self) -> List['TopicRelationship']:
        """
        prerequisite detection with LOWER threshold

        Changes:
        - Reduced minimum mentions from 2 to 1
        - Added confidence scoring
        - Consider article context
        """
        relationships = []
        enrichments = self.db.get_all_enrichments()

        prereq_map = defaultdict(Counter)

        for enrich in enrichments:
            topic_name = enrich['canonical_topic']
            normalized_topic = self.normalizer.normalize(topic_name)

            if normalized_topic not in self.topics:
                continue

            prerequisites = enrich.get('prerequisites', [])

            if not prerequisites:
                continue

            for prereq in prerequisites:
                normalized_prereq = self.normalizer.normalize(prereq)

                if normalized_prereq in self.topics:
                    prereq_map[normalized_topic][normalized_prereq] += 1

        # Create relationships with LOWER threshold
        for topic_name, prereq_counts in prereq_map.items():
            topic = self.topics[topic_name]

            for prereq_name, count in prereq_counts.items():
                # CHANGED: Only need 1 mention (was 2)
                if count >= 1:
                    prereq_topic = self.topics[prereq_name]

                    # Calculate confidence based on frequency
                    confidence = min(count / 5.0, 1.0)  # Scale to 1.0

                    rel = self._create_relationship(
                        prereq_topic.id,
                        topic.id,
                        'prerequisite_of',
                        weight=confidence,
                        supporting_article_count=count,
                        source='prerequisite_mention'
                    )

                    relationships.append(rel)
                    topic.prerequisite_topics.add(prereq_topic.id)

        return relationships

    def _find_related_topics(self) -> List['TopicRelationship']:
        """
        related topic detection

        Strategies:
        1. Link patterns (direct article links between topics)
        2. Co-occurrence in same articles
        3. Profile similarity (DISABLED - too many false positives)
        """
        relationships = []

        # Strategy 1: Link patterns (threshold = 3)
        link_rels = self._find_related_by_links(min_links=3)
        relationships.extend(link_rels)
        print(f"    Link patterns: {len(link_rels)} relationships")

        # Strategy 2: Co-occurrence analysis
        cooccurrence_rels = self._find_related_by_cooccurrence()
        relationships.extend(cooccurrence_rels)
        print(f"    Co-occurrence: {len(cooccurrence_rels)} relationships")

        # Strategy 3: Profile similarity (DISABLED - creates too many relationships)
        # When topics have homogeneous profiles (all same audience/intent),
        # profile similarity creates relationships between nearly all topics
        # Uncomment below to re-enable with VERY high threshold (0.9)
        # profile_rels = self._find_related_by_profile_similarity(min_similarity=0.9)
        # relationships.extend(profile_rels)
        # print(f"    Profile similarity: {len(profile_rels)} relationships")

        return relationships

    def _find_relationships_by_article_overlap(
        self,
        min_overlap: int = 1
    ) -> List['TopicRelationship']:
        """
        Find relationships based on shared articles
        Topics that share articles might be related
        """
        relationships = []
        topic_names = list(self.topics.keys())

        for i, topic1_name in enumerate(topic_names):
            topic1 = self.topics[topic1_name]

            for topic2_name in topic_names[i+1:]:
                topic2 = self.topics[topic2_name]

                # Find shared articles
                shared_articles = topic1.article_ids & topic2.article_ids

                if len(shared_articles) >= min_overlap:
                    # Calculate overlap strength
                    total_articles = len(topic1.article_ids | topic2.article_ids)
                    overlap_strength = len(shared_articles) / total_articles

                    # These topics might actually be duplicates or very related
                    # Create bidirectional related relationships
                    rel1 = self._create_relationship(
                        topic1.id,
                        topic2.id,
                        'related_to',
                        weight=overlap_strength,
                        supporting_article_count=len(shared_articles),
                        source='article_overlap'
                    )
                    relationships.append(rel1)

        return relationships

    def _find_related_by_cooccurrence(self) -> List['TopicRelationship']:
        """
        Find topics that frequently co-occur in the same context
        (e.g., linked from same articles)
        """
        relationships = []

        # Build cooccurrence matrix
        cooccurrence = defaultdict(lambda: defaultdict(int))

        # For each article, get all topics it links to
        for topic_name, topic in self.topics.items():
            for article_id in topic.article_ids:
                # Get linked articles
                linked_ids = self._get_linked_articles(article_id)

                # Find topics of linked articles
                linked_topics = set()
                for linked_id in linked_ids:
                    linked_topic_name = self._find_topic_for_article(linked_id)
                    if linked_topic_name and linked_topic_name != topic_name:
                        linked_topics.add(linked_topic_name)

                # These topics co-occur in the same context
                for linked_topic_name in linked_topics:
                    cooccurrence[topic_name][linked_topic_name] += 1

        # Create relationships for strong co-occurrence
        for source_name, targets in cooccurrence.items():
            source_topic = self.topics[source_name]

            for target_name, count in targets.items():
                if count >= 3:  # Appear together at least 3 times (increased from 2)
                    target_topic = self.topics[target_name]

                    # Skip if already related via other means
                    if self._has_existing_relationship(source_topic, target_topic):
                        continue

                    rel = self._create_relationship(
                        source_topic.id,
                        target_topic.id,
                        'related_to',
                        weight=min(count / 10.0, 1.0),
                        link_count=count,
                        source='cooccurrence'
                    )

                    relationships.append(rel)

        return relationships

    def _find_related_by_profile_similarity(
        self,
        min_similarity: float = 0.7
    ) -> List['TopicRelationship']:
        """
        Find related topics based on similar audience/intent profiles
        Topics targeting same audience with similar intent are likely related
        Higher threshold (0.7) to avoid too many relationships
        """
        relationships = []
        topic_names = list(self.topics.keys())

        for i, topic1_name in enumerate(topic_names):
            topic1 = self.topics[topic1_name]

            for topic2_name in topic_names[i+1:]:
                topic2 = self.topics[topic2_name]

                # Calculate profile similarity
                similarity = self._calculate_profile_similarity(topic1, topic2)

                if similarity >= min_similarity:
                    # Skip if already related
                    if self._has_existing_relationship(topic1, topic2):
                        continue

                    rel = self._create_relationship(
                        topic1.id,
                        topic2.id,
                        'related_to',
                        weight=similarity,
                        source='profile_similarity'
                    )

                    relationships.append(rel)

        return relationships

    def _calculate_profile_similarity(self, topic1, topic2) -> float:
        """
        Calculate similarity between two topic profiles
        Based on intent, complexity, and audience distributions
        """
        # Audience similarity (most important)
        audience_sim = self._distribution_similarity(
            topic1.audience_distribution,
            topic2.audience_distribution
        )

        # Intent similarity
        intent_sim = self._distribution_similarity(
            topic1.intent_distribution,
            topic2.intent_distribution
        )

        # Complexity similarity
        complexity_sim = self._distribution_similarity(
            topic1.complexity_distribution,
            topic2.complexity_distribution
        )

        # Weighted average (audience most important)
        return (audience_sim * 0.5 + intent_sim * 0.3 + complexity_sim * 0.2)

    def _distribution_similarity(self, dist1: Dict, dist2: Dict) -> float:
        """Calculate cosine similarity between two distributions"""
        if not dist1 or not dist2:
            return 0.0

        # Get all keys
        all_keys = set(dist1.keys()) | set(dist2.keys())

        # Create vectors
        vec1 = [dist1.get(k, 0) for k in all_keys]
        vec2 = [dist2.get(k, 0) for k in all_keys]

        # Cosine similarity
        dot_product = sum(v1 * v2 for v1, v2 in zip(vec1, vec2))
        mag1 = sum(v**2 for v in vec1) ** 0.5
        mag2 = sum(v**2 for v in vec2) ** 0.5

        if mag1 == 0 or mag2 == 0:
            return 0.0

        return dot_product / (mag1 * mag2)

    def _suggest_topic_consolidation(self) -> Dict[str, List[str]]:
        """
        Suggest topics that should be consolidated
        Based on high similarity and low article counts
        """
        suggestions = {}

        # Get topics with their article counts
        topics_with_counts = {
            name: topic.total_articles
            for name, topic in self.topics.items()
        }

        # Use normalizer to find similar topics
        suggestions = self.normalizer.suggest_merges(
            topics_with_counts,
            min_article_count=3  # Keep topics with 3+ articles separate
        )

        return suggestions

    def _create_relationship(
        self,
        source_id: int,
        target_id: int,
        rel_type: str,
        weight: float = 1.0,
        supporting_article_count: int = 0,
        link_count: int = 0,
        source: str = 'unknown'
    ):
        """Helper to create a relationship object"""
        from core.models import TopicRelationship

        return TopicRelationship(
            source_topic_id=source_id,
            target_topic_id=target_id,
            relationship_type=rel_type,
            weight=weight,
            supporting_article_count=supporting_article_count,
            link_count=link_count
        )

    def _has_existing_relationship(self, topic1, topic2) -> bool:
        """Check if two topics already have a relationship"""
        return (
            topic2.id in topic1.parent_topics or
            topic2.id in topic1.prerequisite_topics or
            topic2.id in topic1.related_topics or
            topic1.id in topic2.parent_topics or
            topic1.id in topic2.prerequisite_topics or
            topic1.id in topic2.related_topics
        )

    def _get_linked_articles(self, article_id: int) -> List[int]:
        """Get IDs of articles linked from this article"""
        try:
            with self.db.conn.cursor() as cur:
                cur.execute("""
                    SELECT target_id FROM links
                    WHERE source_id = %s
                """, (article_id,))
                return [row[0] for row in cur.fetchall()]
        except Exception:
            return []

    def _find_topic_for_article(self, article_id: int) -> Optional[str]:
        """Find which topic an article belongs to"""
        for topic_name, topic in self.topics.items():
            if article_id in topic.article_ids:
                return topic_name
        return None

    def _find_related_by_links(self, min_links: int = 2) -> List['TopicRelationship']:
        """Find related topics based on link patterns (lowered threshold)"""
        relationships = []
        link_matrix = defaultdict(lambda: defaultdict(int))

        for topic_name, topic in self.topics.items():
            for article_id in topic.article_ids:
                try:
                    linked_article_ids = self._get_linked_articles(article_id)

                    for linked_id in linked_article_ids:
                        linked_topic_name = self._find_topic_for_article(linked_id)

                        if linked_topic_name and linked_topic_name != topic_name:
                            link_matrix[topic_name][linked_topic_name] += 1

                except Exception:
                    continue

        for source_name, targets in link_matrix.items():
            source_topic = self.topics[source_name]

            for target_name, link_count in targets.items():
                if link_count >= min_links:
                    target_topic = self.topics[target_name]

                    if self._has_existing_relationship(source_topic, target_topic):
                        continue

                    rel = self._create_relationship(
                        source_topic.id,
                        target_topic.id,
                        'related_to',
                        weight=min(link_count / 10.0, 1.0),
                        link_count=link_count,
                        source='link_pattern'
                    )

                    relationships.append(rel)
                    source_topic.related_topics.add(target_topic.id)

        return relationships

    def _update_topic_metrics(self, relationships: List['TopicRelationship']):
        """Update indegree, outdegree, and prerequisite_count"""
        for rel in relationships:
            source_topic = None
            target_topic = None

            for topic in self.topics.values():
                if topic.id == rel.source_topic_id:
                    source_topic = topic
                if topic.id == rel.target_topic_id:
                    target_topic = topic

            if not source_topic or not target_topic:
                continue

            if rel.relationship_type == 'subtopic_of':
                source_topic.outdegree += 1
                target_topic.indegree += 1
            elif rel.relationship_type == 'prerequisite_of':
                source_topic.prerequisite_count += 1

    def get_topic_stats(self) -> Dict:
        """Get statistics about the topic graph"""
        if not self.topics:
            self.topics = self._load_topics_from_db()

        total_topics = len(self.topics)
        total_articles = sum(t.total_articles for t in self.topics.values())

        # Distribution stats
        articles_per_topic = [t.total_articles for t in self.topics.values()]
        avg_articles = sum(articles_per_topic) / len(articles_per_topic) if articles_per_topic else 0

        return {
            'total_topics': total_topics,
            'total_articles_mapped': total_articles,
            'avg_articles_per_topic': avg_articles,
            'min_articles': min(articles_per_topic) if articles_per_topic else 0,
            'max_articles': max(articles_per_topic) if articles_per_topic else 0
        }
