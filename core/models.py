"""
Core data models for the knowledge graph pipeline
Defines the domain objects used throughout the system
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Set
from datetime import datetime
from enum import Enum


class IntentType(Enum):
    """Types of article intent"""
    HOW_TO = "how-to"
    OVERVIEW = "overview"
    REFERENCE = "reference"
    TROUBLESHOOTING = "troubleshooting"
    POLICY = "policy"
    UNKNOWN = "unknown"


class AudienceType(Enum):
    """Types of target audience"""
    RESEARCHER = "researcher"
    FACULTY = "faculty"
    STUDENT = "student"
    ADMIN = "admin"
    GENERAL = "general"
    UNKNOWN = "unknown"


class ComplexityLevel(Enum):
    """Complexity levels"""
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"
    UNKNOWN = "unknown"


@dataclass
class Article:
    """
    Represents a knowledge base article
    """
    id: int
    url: str
    title: str
    content: str
    sys_kb_id: Optional[str] = None
    number: Optional[str] = None
    display_number: Optional[str] = None
    snippet: Optional[str] = None
    score: float = 0.0
    can_read: str = "Public"
    depth: int = 0
    crawled_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    # Links
    outbound_links: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Ensure mutable defaults"""
        if self.outbound_links is None:
            self.outbound_links = []


@dataclass
class ArticleEnrichment:
    """
    Semantic enrichment data for an article
    Extracted using LLM analysis
    """
    article_id: int
    canonical_topic: str
    keywords: List[str] = field(default_factory=list)
    intent: IntentType = IntentType.UNKNOWN
    audience: AudienceType = AudienceType.UNKNOWN
    prerequisites: List[str] = field(default_factory=list)
    complexity: ComplexityLevel = ComplexityLevel.UNKNOWN
    
    # Metadata
    enriched_at: Optional[datetime] = None
    llm_model: Optional[str] = None
    
    def __post_init__(self):
        """Ensure mutable defaults and convert enums"""
        if self.keywords is None:
            self.keywords = []
        if self.prerequisites is None:
            self.prerequisites = []
        
        # Convert string to enum if needed
        if isinstance(self.intent, str):
            try:
                self.intent = IntentType(self.intent)
            except ValueError:
                self.intent = IntentType.UNKNOWN
        
        if isinstance(self.audience, str):
            try:
                self.audience = AudienceType(self.audience)
            except ValueError:
                self.audience = AudienceType.UNKNOWN
        
        if isinstance(self.complexity, str):
            try:
                self.complexity = ComplexityLevel(self.complexity)
            except ValueError:
                self.complexity = ComplexityLevel.UNKNOWN


@dataclass
class Topic:
    """
    Represents an abstract topic derived from articles
    Topics are the nodes in our topic graph
    """
    id: Optional[int]
    name: str
    normalized_name: str
    article_ids: Set[int] = field(default_factory=set)
    
    # Relationships
    parent_topics: Set[int] = field(default_factory=set)  # topic_ids that this is a subtopic of
    subtopics: Set[int] = field(default_factory=set)  # topic_ids that are subtopics of this
    related_topics: Set[int] = field(default_factory=set)  # topic_ids that are related
    prerequisite_topics: Set[int] = field(default_factory=set)  # topic_ids that are prerequisites
    
    # Aggregated metrics
    total_articles: int = 0
    intent_distribution: Dict[str, int] = field(default_factory=dict)
    complexity_distribution: Dict[str, int] = field(default_factory=dict)
    audience_distribution: Dict[str, int] = field(default_factory=dict)
    
    # Graph metrics (computed)
    indegree: int = 0  # How many topics point to this
    outdegree: int = 0  # How many subtopics
    prerequisite_count: int = 0  # How often this is a prerequisite
    
    def __post_init__(self):
        """Ensure mutable defaults"""
        if self.article_ids is None:
            self.article_ids = set()
        if self.parent_topics is None:
            self.parent_topics = set()
        if self.subtopics is None:
            self.subtopics = set()
        if self.related_topics is None:
            self.related_topics = set()
        if self.prerequisite_topics is None:
            self.prerequisite_topics = set()
        if self.intent_distribution is None:
            self.intent_distribution = {}
        if self.complexity_distribution is None:
            self.complexity_distribution = {}
        if self.audience_distribution is None:
            self.audience_distribution = {}


@dataclass
class TopicRelationship:
    """
    Represents a relationship between two topics
    """
    source_topic_id: int
    target_topic_id: int
    relationship_type: str  # 'subtopic_of', 'related_to', 'prerequisite_of'
    weight: float = 1.0  # Strength of the relationship
    
    # Evidence for this relationship
    supporting_article_count: int = 0
    link_count: int = 0


@dataclass
class SidebarNode:
    """
    Represents a node in the sidebar hierarchy
    """
    title: str
    topic_id: Optional[int] = None
    article_ids: List[int] = field(default_factory=list)
    children: List['SidebarNode'] = field(default_factory=list)
    depth: int = 0
    
    # Metrics
    metrics: Dict = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        return {
            'title': self.title,
            'topic_id': self.topic_id,
            'article_ids': self.article_ids,
            'depth': self.depth,
            'metrics': self.metrics,
            'children': [child.to_dict() for child in self.children]
        }
    
    def __post_init__(self):
        """Ensure mutable defaults"""
        if self.article_ids is None:
            self.article_ids = []
        if self.children is None:
            self.children = []
        if self.metrics is None:
            self.metrics = {}


@dataclass
class IAIssue:
    """
    Represents an information architecture issue or 'smell'
    """
    issue_type: str  # 'orphan', 'overloaded', 'mixed_intent', 'duplicate'
    severity: str  # 'low', 'medium', 'high'
    topic_id: Optional[int] = None
    description: str = ""
    recommendation: str = ""
    affected_articles: List[int] = field(default_factory=list)
    
    def __post_init__(self):
        """Ensure mutable defaults"""
        if self.affected_articles is None:
            self.affected_articles = []
