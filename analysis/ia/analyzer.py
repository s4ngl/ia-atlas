"""
Information Architecture Analyzer (Phase 3) - MODIFIED
Transforms topic graph into candidate sidebar hierarchies
NOW WITH PREDETERMINED CATEGORY STRUCTURE
"""
import sys
from typing import List, Dict, Optional, Set, Tuple
from collections import defaultdict
import json
from datetime import datetime

sys.path.append('/mnt/project')
from core.models import Topic, SidebarNode, IAIssue


# PREDETERMINED CATEGORY STRUCTURE
PREDETERMINED_CATEGORIES = {
    "Research Computing & HPC": {
        "description": "High-performance computing, research infrastructure, and specialized computing resources",
        "topics": [
            "High Performance Computing",
            "IU Research Computing",
            "IU Research Supercomputers",
            "IU Research Storage",
            "Research Services",
            "Research Technologies",
            "RT Projects",
            "Research Desktop (RED)",
            "SLURM",
            "MATLAB",
            "STC Computing Labs",
            "Indiana University Research Database Complex"
        ],
        "keywords": [
            "hpc", "supercomputer", "research computing", "slurm", "batch",
            "cluster", "parallel", "red", "carbonate", "big red", "matlab",
            "research technologies", "research desktop", "rt ", "high performance"
        ]
    },
    "Cloud & Infrastructure": {
        "description": "Cloud computing, container orchestration, and infrastructure services",
        "topics": [
            "Cloud Computing",
            "Cloud Storage",
            "Kubernetes",
            "Container Orchestration",
            "AppKube",
            "Infrastructure",
            "Data Center Operations"
        ],
        "keywords": [
            "cloud", "kubernetes", "k8s", "container", "docker", "orchestration",
            "infrastructure", "appkube", "data center", "aws", "azure", "gcp"
        ]
    },
    "Data & Storage": {
        "description": "Data management, storage systems, and data-related services",
        "topics": [
            "Data Management",
            "Data Management at IU",
            "File Storage",
            "File Management",
            "IU Storage Systems",
            "II Enterprise S3 Object Storage",
            "IU Scholarly Data Archive",
            "IU Scholarly Data Archive (SDA)",
            "Google at IU Storage Management",
            "Storage",
            "Data Virtualization",
            "IU Research Storage"
        ],
        "keywords": [
            "storage", "data management", "file", "s3", "object storage",
            "sda", "scholarly data archive", "backup", "archive", "data lake"
        ]
    },
    "Development & Software": {
        "description": "Software, development tools, and programming resources",
        "topics": [
            "Development",
            "Software",
            "IU Tools",
            "Unix",
            "Unix Commands",
            "Unix File Management",
            "Unix File System",
            "Unix Shell",
            "SSH",
            "Compiling Programs",
            "File Transfer",
            "Windows Hosting Environment",
            "IU Windows Installation"
        ],
        "keywords": [
            "development", "programming", "software", "unix", "linux", "shell",
            "bash", "ssh", "compile", "git", "version control", "ide",
            "windows", "file transfer", "sftp", "scp", "ftp"
        ]
    },
    "Computing Access": {
        "description": "Computer labs, remote access, and VPN services",
        "topics": [
            "IU Computing Labs",
            "IUanyWare",
            "IU VPN",
            "IU SSL VPN"
        ],
        "keywords": [
            "computer lab", "iuanyware", "vpn", "remote access", "remote desktop",
            "ssl vpn", "anyware", "lab access", "lab", "computing lab"
        ]
    },
    "Accounts & Authentication": {
        "description": "User accounts, authentication, and access management",
        "topics": [
            "Authentication",
            "IU Computing Accounts",
            "Indiana University Accounts",
            "Active Directory Services",
            "Active Directory Services (ADS)",
            "Google Account Management"
        ],
        "keywords": [
            "account", "authentication", "login", "password", "two-factor",
            "2fa", "mfa", "active directory", "ads", "google account", "username",
            "passphrase", "duo"
        ]
    },
    "Policies & Guidelines": {
        "description": "Computing policies, best practices, and compliance",
        "topics": [
            "IU Computing Policies"
        ],
        "keywords": [
            "policy", "compliance", "guideline", "acceptable use", "security policy",
            "data policy", "best practice"
        ]
    },
    "Collaboration & Research Tools": {
        "description": "Collaboration platforms and specialized research tools",
        "topics": [
            "Google at IU",
            "Generative AI",
            "Slate",
            "IU REDCap",
            "IU REDCap Project Management",
            "IUIE",
            "IUIE (Indiana University Information Environment)"
        ],
        "keywords": [
            "google", "collaboration", "ai", "generative ai", "chatgpt",
            "redcap", "survey", "research data", "slate", "iuie", "workspace"
        ]
    },
    "Support & Resources": {
        "description": "Help resources, training, and IT support",
        "topics": [
            "IU Resources",
            "Training",
            "IT Support"
        ],
        "keywords": [
            "support", "help", "training", "documentation", "tutorial",
            "workshop", "resource", "faq", "guide"
        ]
    }
}


class Analyzer:
    """
    Analyzes topic graph and generates sidebar structure recommendations
    NOW WITH PREDETERMINED CATEGORY MODE
    """

    def __init__(
        self,
        db,
        max_depth: int = 3,
        max_fan_out: int = 10,
        min_article_count: int = 3,
        use_predetermined: bool = True
    ):
        """
        Initialize IA Analyzer

        Args:
            db: Database instance (EnrichedGraphDB)
            max_depth: Maximum depth of sidebar hierarchy
            max_fan_out: Maximum number of children per node
            min_article_count: Minimum articles to be a standalone topic
            use_predetermined: Use predetermined category structure
        """
        self.db = db
        self.max_depth = max_depth
        self.max_fan_out = max_fan_out
        self.min_article_count = min_article_count
        self.use_predetermined = use_predetermined

        # Cache
        self.topics: Dict[int, Dict] = {}
        self.relationships: List[Dict] = []
        self.topic_graph: Dict[int, Dict] = {}
        self.all_articles = []  # For predetermined mode

    def load_topic_data(self) -> bool:
        """
        Load topics and relationships from database

        Returns:
            True if successful
        """
        print("Loading topic data from database...")

        # Load all topics
        topics = self.db.get_all_topics()
        if not topics:
            print("✗ No topics found in database")
            return False

        # Index by ID
        self.topics = {t['id']: t for t in topics}
        print(f"✓ Loaded {len(self.topics)} topics")

        # Load all relationships
        self.relationships = self.db.get_topic_relationships()
        print(f"✓ Loaded {len(self.relationships)} relationships")

        # Build adjacency structure
        self._build_topic_graph()

        # Load articles if using predetermined mode
        if self.use_predetermined:
            self._load_articles()

        return True

    def _load_articles(self):
        """Load all articles for predetermined mode - now just a compatibility method"""
        # We don't need to preload all articles since we query by topic
        # This method is kept for compatibility but does minimal work
        self.all_articles = []
        print(f"✓ Articles will be loaded on-demand from database")

    def _build_topic_graph(self):
        """Build graph structure from relationships"""
        # Initialize graph structure for each topic
        for topic_id in self.topics:
            self.topic_graph[topic_id] = {
                'parents': set(),      # Topics this is a subtopic of
                'children': set(),     # Subtopics
                'related': set(),      # Related topics
                'prerequisites': set(), # Prerequisite topics
                'dependent_on_by': set() # Topics that require this
            }

        # Populate from relationships
        for rel in self.relationships:
            source_id = rel['source_topic_id']
            target_id = rel['target_topic_id']
            rel_type = rel['relationship_type']

            if source_id not in self.topic_graph or target_id not in self.topic_graph:
                continue

            if rel_type == 'subtopic_of':
                # Source is a subtopic of target
                self.topic_graph[source_id]['parents'].add(target_id)
                self.topic_graph[target_id]['children'].add(source_id)

            elif rel_type == 'related_to':
                self.topic_graph[source_id]['related'].add(target_id)

            elif rel_type == 'prerequisite_of':
                # Source is a prerequisite of target
                self.topic_graph[source_id]['dependent_on_by'].add(target_id)
                self.topic_graph[target_id]['prerequisites'].add(source_id)

    def build_sidebar_tree(
        self,
        root_topics: Optional[List[int]] = None,
        verbose: bool = True
    ) -> List[SidebarNode]:
        """
        Build sidebar hierarchy from topic graph

        Args:
            root_topics: Optional list of root topic IDs (auto-detect if None)
            verbose: Print progress

        Returns:
            List of SidebarNode objects (roots of hierarchy)
        """
        if self.use_predetermined:
            return self._build_predetermined_sidebar(verbose)
        else:
            return self._build_automatic_sidebar(root_topics, verbose)

    def _build_predetermined_sidebar(self, verbose: bool = True) -> List[SidebarNode]:
        """Build sidebar using predetermined category structure"""
        if verbose:
            print("\n" + "=" * 80)
            print("BUILDING PREDETERMINED SIDEBAR STRUCTURE")
            print("=" * 80 + "\n")

        sidebar_roots = []
        total_articles_mapped = 0

        for category_name, category_config in PREDETERMINED_CATEGORIES.items():
            if verbose:
                print(f"\nProcessing: {category_name}")

            # Create category node
            category_node = SidebarNode(
                title=category_name,
                topic_id=None,
                article_ids=[],
                depth=0
            )
            category_node.metrics = {
                'article_count': 0,
                'indegree': 0,
                'outdegree': 0,
                'intent_distribution': defaultdict(int),
                'complexity_distribution': defaultdict(int)
            }

            # Find and add topics for this category
            for topic_name in category_config['topics']:
                topic_node = self._find_or_create_topic_node(
                    topic_name,
                    category_config['keywords'],
                    depth=1,
                    verbose=verbose
                )

                if topic_node and topic_node.metrics.get('article_count', 0) > 0:
                    category_node.children.append(topic_node)

                    # Aggregate metrics
                    article_count = topic_node.metrics['article_count']
                    category_node.metrics['article_count'] += article_count

                    # Aggregate distributions
                    for intent, count in topic_node.metrics.get('intent_distribution', {}).items():
                        category_node.metrics['intent_distribution'][intent] += count

                    for complexity, count in topic_node.metrics.get('complexity_distribution', {}).items():
                        category_node.metrics['complexity_distribution'][complexity] += count

                    if verbose:
                        print(f"  ✓ {topic_name}: {article_count} articles")
                    total_articles_mapped += article_count

            # Add category if it has children
            if category_node.children:
                # Sort children by article count
                category_node.children.sort(
                    key=lambda n: n.metrics.get('article_count', 0),
                    reverse=True
                )

                # Convert defaultdicts to regular dicts
                category_node.metrics['intent_distribution'] = dict(
                    category_node.metrics['intent_distribution']
                )
                category_node.metrics['complexity_distribution'] = dict(
                    category_node.metrics['complexity_distribution']
                )

                sidebar_roots.append(category_node)
                if verbose:
                    print(f"  Total: {category_node.metrics['article_count']} articles in {len(category_node.children)} topics")
            else:
                if verbose:
                    print(f"  ✗ No topics found for this category")

        # Sort categories by article count
        sidebar_roots.sort(
            key=lambda n: n.metrics.get('article_count', 0),
            reverse=True
        )

        if verbose:
            print(f"\n{'=' * 80}")
            print(f"✓ Built {len(sidebar_roots)} categories")
            print(f"✓ Total articles mapped: {total_articles_mapped}")
            print(f"{'=' * 80}\n")

        return sidebar_roots

    def _find_or_create_topic_node(
        self,
        topic_name: str,
        category_keywords: List[str],
        depth: int = 1,
        verbose: bool = False
    ) -> Optional[SidebarNode]:
        """Find topic by name or create pseudo-topic from keywords"""

        # Try exact match
        for topic_id, topic in self.topics.items():
            if topic['name'].lower() == topic_name.lower():
                if verbose:
                    print(f"    Found exact match: {topic['name']}")
                return self._create_topic_node_from_db(topic, depth)

        # Try fuzzy match (contains)
        for topic_id, topic in self.topics.items():
            topic_lower = topic['name'].lower()
            name_lower = topic_name.lower()

            # Check if one contains the other
            if (name_lower in topic_lower or topic_lower in name_lower):
                if verbose:
                    print(f"    Found fuzzy match: '{topic_name}' ~ '{topic['name']}'")
                return self._create_topic_node_from_db(topic, depth)

        # Try to find articles by keywords
        if verbose:
            print(f"    No topic match, searching by keywords for: {topic_name}")

        keyword_node = self._create_topic_from_keywords(topic_name, category_keywords, depth)

        if keyword_node and verbose:
            print(f"    Created keyword-based topic with {keyword_node.metrics['article_count']} articles")

        return keyword_node

    def _create_topic_node_from_db(
        self,
        topic: Dict,
        depth: int
    ) -> SidebarNode:
        """Create sidebar node from database topic"""
        # Get articles for this topic using the database API
        articles = self.db.get_articles_by_topic(topic['id'])

        node = SidebarNode(
            title=topic['name'],
            topic_id=topic['id'],
            article_ids=[a['id'] for a in articles],
            depth=depth
        )

        # Calculate metrics from the articles
        intent_dist = defaultdict(int)
        complexity_dist = defaultdict(int)

        for article in articles:
            if article.get('content_intent'):
                intent_dist[article['content_intent']] += 1
            if article.get('complexity_level'):
                complexity_dist[article['complexity_level']] += 1

        node.metrics = {
            'article_count': len(articles),
            'indegree': topic.get('indegree', 0),
            'outdegree': topic.get('outdegree', 0),
            'intent_distribution': dict(intent_dist),
            'complexity_distribution': dict(complexity_dist)
        }

        return node

    def _create_topic_from_keywords(
        self,
        topic_name: str,
        keywords: List[str],
        depth: int
    ) -> Optional[SidebarNode]:
        """Create a pseudo-topic by finding articles matching keywords across all topics"""
        matching_articles = []
        seen_article_ids = set()

        # Search through all topics for articles matching keywords
        for topic_id, topic in self.topics.items():
            try:
                articles = self.db.get_articles_by_topic(topic_id)

                for article in articles:
                    # Avoid duplicates
                    if article['id'] in seen_article_ids:
                        continue

                    title_lower = article.get('title', '').lower()

                    # Check if any keyword matches
                    for keyword in keywords:
                        if keyword.lower() in title_lower:
                            matching_articles.append(article)
                            seen_article_ids.add(article['id'])
                            break

            except Exception:
                continue

        if not matching_articles:
            return None

        # Create node
        node = SidebarNode(
            title=topic_name,
            topic_id=None,  # Pseudo-topic
            article_ids=[a['id'] for a in matching_articles],
            depth=depth
        )

        # Calculate metrics
        intent_dist = defaultdict(int)
        complexity_dist = defaultdict(int)

        for article in matching_articles:
            if article.get('content_intent'):
                intent_dist[article['content_intent']] += 1
            if article.get('complexity_level'):
                complexity_dist[article['complexity_level']] += 1

        node.metrics = {
            'article_count': len(matching_articles),
            'indegree': 0,
            'outdegree': 0,
            'intent_distribution': dict(intent_dist),
            'complexity_distribution': dict(complexity_dist)
        }

        return node

    def _build_automatic_sidebar(
        self,
        root_topics: Optional[List[int]] = None,
        verbose: bool = True
    ) -> List[SidebarNode]:
        """
        Original automatic sidebar building logic
        (keeping for backward compatibility)
        """
        if verbose:
            print("\n" + "=" * 80)
            print("BUILDING SIDEBAR HIERARCHY (AUTOMATIC MODE)")
            print("=" * 80 + "\n")

        # Auto-detect root topics if not provided
        if root_topics is None:
            root_topics = self.identify_top_level_topics()

        sidebar_roots = []
        visited_topics = set()

        for root_id in root_topics:
            if root_id in visited_topics:
                continue

            # Build tree for this root
            node = self._build_sidebar_node(
                topic_id=root_id,
                current_depth=0,
                visited=visited_topics,
                verbose=verbose
            )

            if node:
                sidebar_roots.append(node)

        if verbose:
            print(f"\n✓ Built {len(sidebar_roots)} top-level sections")
            total_nodes = sum(self._count_nodes(node) for node in sidebar_roots)
            print(f"  Total nodes in sidebar: {total_nodes}")

        return sidebar_roots

    # ... Continue with all the original methods from analyzer.py ...
    # (identify_top_level_topics, _build_sidebar_node, detect_ia_issues, etc.)

    def identify_top_level_topics(self, limit: int = 10) -> List[int]:
        """Identify topics for top level - original implementation"""
        scores = []

        for topic_id, topic in self.topics.items():
            if topic['total_articles'] < self.min_article_count:
                continue

            score = 0.0
            score += 3.0 * topic['total_articles']
            score += 2.0 * topic['indegree']
            score -= 10.0 * len(self.topic_graph[topic_id]['parents'])
            score -= 5.0 * topic['prerequisite_count']
            score += 1.5 * len(self.topic_graph[topic_id]['children'])

            scores.append((topic_id, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        return [topic_id for topic_id, _ in scores[:limit]]

    def _build_sidebar_node(
        self,
        topic_id: int,
        current_depth: int,
        visited: Set[int],
        verbose: bool = False
    ) -> Optional[SidebarNode]:
        """Build sidebar node - original implementation"""
        if topic_id in visited or current_depth >= self.max_depth:
            return None

        visited.add(topic_id)
        topic = self.topics.get(topic_id)
        if not topic:
            return None

        # Get articles from database
        articles = self.db.get_articles_by_topic(topic_id)

        node = SidebarNode(
            title=topic['name'],
            topic_id=topic_id,
            article_ids=[a['id'] for a in articles],
            depth=current_depth
        )

        # Build children
        children_ids = sorted(
            self.topic_graph[topic_id]['children'],
            key=lambda tid: self.topics[tid]['total_articles'],
            reverse=True
        )[:self.max_fan_out]

        for child_id in children_ids:
            child_node = self._build_sidebar_node(
                topic_id=child_id,
                current_depth=current_depth + 1,
                visited=visited,
                verbose=verbose
            )
            if child_node:
                node.children.append(child_node)

        # Calculate metrics from articles
        intent_dist = defaultdict(int)
        complexity_dist = defaultdict(int)

        for article in articles:
            if article.get('content_intent'):
                intent_dist[article['content_intent']] += 1
            if article.get('complexity_level'):
                complexity_dist[article['complexity_level']] += 1

        node.metrics = {
            'article_count': len(articles) + sum(
                c.metrics.get('article_count', 0) for c in node.children
            ),
            'indegree': topic.get('indegree', 0),
            'outdegree': topic.get('outdegree', 0),
            'intent_distribution': dict(intent_dist),
            'complexity_distribution': dict(complexity_dist)
        }

        return node

    def _count_nodes(self, node: SidebarNode) -> int:
        """Recursively count nodes"""
        count = 1
        for child in node.children:
            count += self._count_nodes(child)
        return count

    def detect_ia_issues(self) -> List[IAIssue]:
        """Detect IA issues - original implementation"""
        issues = []
        issues.extend(self._detect_orphan_topics())
        issues.extend(self._detect_overloaded_topics())
        issues.extend(self._detect_mixed_intent())
        return issues

    def _detect_orphan_topics(self) -> List[IAIssue]:
        """Detect orphaned topics"""
        issues = []
        for topic_id, graph_node in self.topic_graph.items():
            if (len(graph_node['parents']) == 0 and
                len(graph_node['children']) == 0 and
                len(graph_node['related']) == 0):
                topic = self.topics[topic_id]
                issues.append(IAIssue(
                    issue_type='orphan',
                    severity='medium',
                    topic_id=topic_id,
                    description=f"Topic '{topic['name']}' has no relationships to other topics",
                    recommendation="Consider linking to related topics or merging with similar concepts"
                ))
        return issues

    def _detect_overloaded_topics(self) -> List[IAIssue]:
        """Detect topics with too many articles"""
        issues = []
        for topic_id, topic in self.topics.items():
            article_count = topic['total_articles']
            if article_count > 50:
                issues.append(IAIssue(
                    issue_type='overloaded',
                    severity='high' if article_count > 100 else 'medium',
                    topic_id=topic_id,
                    description=f"Topic '{topic['name']}' has {article_count} articles ({'critical' if article_count > 100 else 'warning'})",
                    recommendation="Consider breaking into subtopics or adding intermediate categories"
                ))
        return issues

    def _detect_mixed_intent(self) -> List[IAIssue]:
        """Detect topics mixing different content types"""
        issues = []
        for topic_id, topic in self.topics.items():
            intent_dist = topic.get('intent_distribution')
            if not intent_dist or not isinstance(intent_dist, dict):
                continue
            if len(intent_dist) <= 1:
                continue
            total = sum(intent_dist.values())
            if total == 0:
                continue
            max_percentage = max(intent_dist.values()) / total
            if max_percentage < 0.7 and total >= 5:
                issues.append(IAIssue(
                    issue_type='mixed_intent',
                    severity='low',
                    topic_id=topic_id,
                    description=f"Topic '{topic['name']}' mixes multiple content types: {intent_dist}",
                    recommendation="Consider separating how-to guides from reference material"
                ))
        return issues

    def export_sidebar_json(
        self,
        sidebar_roots: List[SidebarNode],
        output_path: str
    ) -> bool:
        """Export sidebar to JSON with article details"""
        try:
            sidebar_data = []

            for category in sidebar_roots:
                category_dict = category.to_dict()

                # Add article details to each topic
                for topic in category_dict.get('children', []):
                    if topic.get('topic_id') and topic['article_ids']:
                        topic['articles'] = []

                        # Get articles from database for this topic
                        try:
                            db_articles = self.db.get_articles_by_topic(topic['topic_id'])

                            for article in db_articles:
                                topic['articles'].append({
                                    'id': article.get('id'),
                                    'title': article.get('title', ''),
                                    'url': article.get('url', ''),
                                    'intent': article.get('content_intent', ''),
                                    'complexity': article.get('complexity_level', '')
                                })
                        except Exception as e:
                            print(f"  Warning: Could not get articles for topic {topic['topic_id']}: {e}")

                sidebar_data.append(category_dict)

            output = {
                'sidebar': sidebar_data,
                'metadata': {
                    'generated_at': str(datetime.now()),
                    'max_depth': self.max_depth,
                    'max_fan_out': self.max_fan_out,
                    'structure_type': 'predetermined' if self.use_predetermined else 'automatic',
                    'total_topics': len(self.topics),
                    'total_sections': len(sidebar_roots),
                    'total_articles': sum(
                        cat.metrics.get('article_count', 0)
                        for cat in sidebar_roots
                    )
                }
            }

            with open(output_path, 'w') as f:
                json.dump(output, f, indent=2)

            print(f"\n✓ Sidebar structure exported to: {output_path}")
            return True

        except Exception as e:
            print(f"\n✗ Failed to export sidebar: {e}")
            import traceback
            traceback.print_exc()
            return False

    def export_issues_report(self, issues: List[IAIssue], output_path: str) -> bool:
        """Export issues - original implementation"""
        try:
            data = {
                'issues': [
                    {
                        'type': issue.issue_type,
                        'severity': issue.severity,
                        'topic_id': issue.topic_id,
                        'topic_name': self.topics[issue.topic_id]['name'] if issue.topic_id else None,
                        'description': issue.description,
                        'recommendation': issue.recommendation,
                        'affected_articles': issue.affected_articles
                    }
                    for issue in issues
                ],
                'metadata': {
                    'generated_at': str(datetime.now()),
                    'total_issues': len(issues),
                    'by_severity': {
                        'high': sum(1 for i in issues if i.severity == 'high'),
                        'medium': sum(1 for i in issues if i.severity == 'medium'),
                        'low': sum(1 for i in issues if i.severity == 'low')
                    },
                    'by_type': dict(defaultdict(int, {
                        issue.issue_type: sum(1 for i in issues if i.issue_type == issue.issue_type)
                        for issue in issues
                    }))
                }
            }

            with open(output_path, 'w') as f:
                json.dump(output, f, indent=2)

            print(f"\n✓ IA issues report exported to: {output_path}")
            return True

        except Exception as e:
            print(f"\n✗ Failed to export issues report: {e}")
            return False

    def print_sidebar_preview(
        self,
        sidebar_roots: List[SidebarNode],
        max_items: int = 5
    ):
        """Print sidebar preview"""
        print("\n" + "=" * 80)
        print("SIDEBAR PREVIEW")
        print("=" * 80 + "\n")

        for i, root in enumerate(sidebar_roots[:max_items], 1):
            self._print_node(root, indent=0, max_children=max_items)
            print()

        if len(sidebar_roots) > max_items:
            print(f"... and {len(sidebar_roots) - max_items} more top-level sections")

    def _print_node(
        self,
        node: SidebarNode,
        indent: int = 0,
        max_children: int = 5
    ):
        """Recursively print sidebar node"""
        indent_str = "  " * indent
        article_count = node.metrics.get('article_count', len(node.article_ids))

        print(f"{indent_str}├─ {node.title} ({article_count} articles)")

        # Show sample article IDs
        if indent > 0 and node.article_ids[:3]:
            print(f"{indent_str}   Article IDs: {node.article_ids[:3]}")

        # Print children
        for i, child in enumerate(node.children[:max_children]):
            self._print_node(child, indent + 1, max_children)

        if len(node.children) > max_children:
            print(f"{indent_str}  └─ ... and {len(node.children) - max_children} more")
