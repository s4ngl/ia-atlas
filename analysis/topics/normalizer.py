"""
 Topic Normalizer with Hierarchical Fallback

This version ensures 100% article coverage by:
1. Aggressive consolidation (as before)
2. Hierarchical categorization for orphaned topics
3. Smart fallback to parent categories

Result: ~100-200 topics with 100% article coverage
"""
import re
from typing import Dict, List, Set, Tuple
from collections import defaultdict, Counter


class TopicNormalizer:
    """
    Topic normalizer with hierarchical fallback for 100% article coverage
    """

    def __init__(self):
        """Initialize normalizer with consolidation rules and hierarchies"""

        # Terms to remove from topic names
        self.removal_terms = {
            'at iu', 'at indiana university', 'iu ', ' iu',
            'indiana university', 'at indiana',
        }

        # Suffixes that indicate sub-topics (should be merged with parent)
        self.merge_suffixes = {
            'configuration', 'settings', 'setup', 'installation',
            'policy', 'policies', 'guidelines', 'guide',
            'management', 'administration', 'admin',
            'tools', 'utilities', 'resources',
            'storage', 'access', 'permissions',
            'troubleshooting', 'support', 'help',
            'documentation', 'docs', 'reference',
            'migration', 'transition', 'upgrade',
            'integration', 'api', 'interface',
            'security', 'authentication', 'authorization',
            'monitoring', 'logging', 'reporting',
            'backup', 'recovery', 'restore',
            'performance', 'optimization', 'tuning',
        }

        # Specific topic consolidations
        self.consolidation_map = {
            # Email
            'email': 'Email',
            'email management': 'Email',
            'email migration': 'Email',
            'email forwarding': 'Email',
            'exchange email': 'Email',
            'outlook': 'Email',

            # Authentication
            'two-step login': 'Authentication',
            'two-factor authentication': 'Authentication',
            'multi-factor authentication': 'Authentication',
            'password': 'Authentication',
            'password management': 'Authentication',
            'password reset': 'Authentication',

            # Storage
            'network storage': 'Network Storage',
            'file storage': 'File Storage',
            'cloud storage': 'Cloud Storage',
            'data storage': 'Data Storage',

            # Web/CMS
            'wcms': 'Web Content Management',
            'web development': 'Web Development',
            'web hosting': 'Web Development',

            # Adobe
            'adobe creative cloud': 'Adobe Creative Cloud',
            'adobe software': 'Adobe Creative Cloud',

            # Collaboration
            'zoom': 'Video Conferencing',
            'microsoft teams': 'Video Conferencing',
            'webex': 'Video Conferencing',

            # Accessibility
            'accessibility': 'Accessibility',
            'wcag': 'Accessibility',
            'vpat': 'Accessibility',

            # Data Management
            'data management': 'Data Management',
        }

        # Hierarchical category mappings for orphaned topics
        # These are broader categories to catch topics that don't have enough articles
        self.category_hierarchy = {
            # Computing & Infrastructure
            'computing': ['compute', 'cluster', 'hpc', 'supercomputer', 'server', 'virtual machine', 'vm'],
            'infrastructure': ['network', 'dns', 'vpn', 'firewall', 'router', 'switch'],

            # Storage & Data
            'storage': ['drive', 'disk', 'backup', 'archive', 'file system', 'nas', 'san'],
            'data management': ['data', 'database', 'sql', 'metadata', 'dataset'],

            # Software & Development
            'software': ['application', 'program', 'software', 'app'],
            'development': ['code', 'programming', 'git', 'repository', 'ide', 'compiler'],
            'web development': ['html', 'css', 'javascript', 'web', 'website', 'cms'],

            # Security & Access
            'security': ['security', 'encrypt', 'certificate', 'ssl', 'tls', 'firewall'],
            'authentication': ['login', 'password', 'authentication', 'authorization', 'access control', 'permissions'],

            # Communication & Collaboration
            'communication': ['email', 'messaging', 'chat', 'notification'],
            'collaboration': ['teams', 'sharepoint', 'collaborate', 'meeting', 'conference'],
            'video conferencing': ['zoom', 'webex', 'video', 'conferencing', 'meeting'],

            # Academic & Research
            'research computing': ['research', 'academic', 'scholarly', 'publication', 'grant'],
            'student services': ['student', 'course', 'enrollment', 'registration', 'advising', 'academic planning'],

            # Media & Design
            'media': ['video', 'audio', 'image', 'media', 'multimedia'],
            'design': ['design', 'graphics', 'adobe', 'creative', 'photoshop', 'illustrator'],

            # IT Services
            'it support': ['support', 'help', 'troubleshooting', 'ticket', 'service desk'],
            'training': ['training', 'tutorial', 'workshop', 'documentation', 'guide'],

            # Specific Services
            'canvas': ['canvas', 'lms', 'learning management'],
            'google workspace': ['google', 'gmail', 'drive', 'docs', 'sheets'],
            'microsoft 365': ['office 365', 'microsoft 365', 'onedrive', 'outlook'],
        }

    def normalize(self, topic_name: str) -> str:
        """
        Normalize a single topic name with aggressive consolidation

        Args:
            topic_name: Raw topic name

        Returns:
            Normalized topic name
        """
        if not topic_name:
            return "General"

        # Convert to lowercase for processing
        normalized = topic_name.lower().strip()

        # Remove common noise terms
        normalized = self._remove_noise_terms(normalized)

        # Check consolidation map first
        if normalized in self.consolidation_map:
            return self.consolidation_map[normalized]

        # Remove "at IU" and "IU" references
        normalized = self._remove_iu_references(normalized)

        # Check if this is a sub-topic that should be merged
        normalized = self._merge_subtopics(normalized)

        # Standardize formatting
        normalized = self._standardize_format(normalized)

        return normalized

    def normalize_with_fallback(
        self,
        topic_name: str,
        fallback: bool = True
    ) -> Tuple[str, str]:
        """
        Normalize with hierarchical fallback

        Args:
            topic_name: Raw topic name
            fallback: Whether to also return a fallback category

        Returns:
            (normalized_topic, fallback_category)
        """
        normalized = self.normalize(topic_name)

        if not fallback:
            return (normalized, None)

        # Find best fallback category
        fallback_category = self._find_fallback_category(normalized)

        return (normalized, fallback_category)

    def _find_fallback_category(self, normalized_topic: str) -> str:
        """
        Find the best fallback category for a topic

        Args:
            normalized_topic: Normalized topic name

        Returns:
            Fallback category name
        """
        topic_lower = normalized_topic.lower()

        # Check each category's keywords
        best_category = None
        best_score = 0

        for category, keywords in self.category_hierarchy.items():
            score = 0

            for keyword in keywords:
                # Exact match in topic name
                if keyword == topic_lower:
                    score += 10
                # Keyword is a word in the topic
                elif keyword in topic_lower.split():
                    score += 5
                # Keyword is a substring
                elif keyword in topic_lower:
                    score += 2

            if score > best_score:
                best_score = score
                best_category = category

        # If we found a good match, return it
        if best_score >= 2:
            return self._standardize_format(best_category)

        # Default fallback
        return "General"

    def _remove_noise_terms(self, text: str) -> str:
        """Remove common noise terms"""
        # Remove leading action verbs
        text = re.sub(r'^(accessing|using|managing|configuring)\s+', '', text, flags=re.IGNORECASE)

        # Remove " My " pattern
        text = re.sub(r'\s+my\s+', ' ', text, flags=re.IGNORECASE)

        # Remove parenthetical abbreviations
        text = re.sub(r'\s*\([^)]+\)\s*', ' ', text)

        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text).strip()

        return text

    def _remove_iu_references(self, text: str) -> str:
        """Remove all IU-specific references"""
        # Handle multi-word patterns
        text = re.sub(r'\bat\s+indiana\s+university\b', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\bindiana\s+university\b', '', text, flags=re.IGNORECASE)

        # Handle "at IU" patterns
        text = re.sub(r'\bat\s+iu\b', '', text, flags=re.IGNORECASE)

        # Handle "IU" at word boundaries
        text = re.sub(r'^iu\s+', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\s+iu$', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\s+iu\s+', ' ', text, flags=re.IGNORECASE)

        # Handle "on IU" pattern
        text = re.sub(r'\s+on\s+iu\b', '', text, flags=re.IGNORECASE)

        # Clean up extra spaces
        text = re.sub(r'\s+', ' ', text).strip()

        return text

    def _merge_subtopics(self, text: str) -> str:
        """Merge sub-topics with their parent topics"""
        words = text.split()
        if len(words) > 1:
            last_word = words[-1].lower()
            if last_word in self.merge_suffixes:
                text = ' '.join(words[:-1])

        return text

    def _standardize_format(self, text: str) -> str:
        """Standardize the format of topic names"""
        # Clean up spaces
        text = re.sub(r'\s+', ' ', text).strip()

        # Title case, but preserve acronyms
        words = []
        for word in text.split():
            if word.isupper() and len(word) >= 2:
                words.append(word)
            elif any(c.isupper() for c in word[1:]):
                words.append(word)
            else:
                words.append(word.capitalize())

        return ' '.join(words)

    def normalize_batch(self, topic_names: List[str]) -> Dict[str, str]:
        """Normalize a batch of topic names"""
        mapping = {}

        for name in topic_names:
            normalized = self.normalize(name)
            mapping[name] = normalized

        return mapping

    def normalize_batch_with_fallback(
        self,
        topic_names: List[str]
    ) -> Dict[str, Tuple[str, str]]:
        """
        Normalize a batch with fallbacks

        Returns:
            Dict of raw_topic -> (normalized_topic, fallback_category)
        """
        mapping = {}

        for name in topic_names:
            normalized, fallback = self.normalize_with_fallback(name)
            mapping[name] = (normalized, fallback)

        return mapping

    def suggest_merges(
        self,
        topics_with_counts: Dict[str, int],
        min_article_count: int = 2
    ) -> Dict[str, List[str]]:
        """
        Suggest topics that should be merged based on:
        1. Low article counts
        2. Similar names
        3. Semantic similarity

        Args:
            topics_with_counts: Dict of topic_name -> article_count
            min_article_count: Topics with fewer articles are candidates for merging

        Returns:
            Dict of canonical_topic -> [topics_to_merge]
        """
        suggestions = defaultdict(list)

        # Separate high and low count topics
        high_count = {t: c for t, c in topics_with_counts.items() if c >= min_article_count}
        low_count = {t: c for t, c in topics_with_counts.items() if c < min_article_count}

        # For each low-count topic, find best match in high-count topics
        for low_topic in low_count:
            best_match = self._find_best_merge_target(low_topic, high_count)

            if best_match:
                suggestions[best_match].append(low_topic)
            else:
                # If no good match, find other similar low-count topics
                similar_low = self._find_similar_topics(low_topic, low_count)
                if similar_low:
                    # Use the longest/most specific as canonical
                    canonical = max([low_topic] + similar_low, key=len)
                    for topic in [low_topic] + similar_low:
                        if topic != canonical:
                            suggestions[canonical].append(topic)

        return dict(suggestions)

    def _find_best_merge_target(
        self,
        topic: str,
        candidates: Dict[str, int]
    ) -> str:
        """
        Find the best topic to merge with from candidates

        Args:
            topic: Topic to find merge target for
            candidates: Potential merge targets

        Returns:
            Best matching topic name or None
        """
        topic_lower = topic.lower()
        topic_words = set(topic_lower.split())

        best_match = None
        best_score = 0

        for candidate in candidates:
            candidate_lower = candidate.lower()
            candidate_words = set(candidate_lower.split())

            # Calculate similarity score
            score = 0

            # Exact substring match (highest priority)
            if topic_lower in candidate_lower or candidate_lower in topic_lower:
                score = 10

            # High word overlap
            elif len(topic_words & candidate_words) / len(topic_words) >= 0.6:
                score = 5

            # Partial word overlap
            elif len(topic_words & candidate_words) >= 1:
                score = 2

            # Same starting word (for acronyms/prefixes)
            elif topic_words and candidate_words and list(topic_words)[0] == list(candidate_words)[0]:
                score = 1

            if score > best_score:
                best_score = score
                best_match = candidate

        # Only return if we found a good match
        return best_match if best_score >= 2 else None

    def _find_similar_topics(
        self,
        topic: str,
        candidates: Dict[str, int]
    ) -> List[str]:
        """Find topics similar to the given topic"""
        topic_lower = topic.lower()
        topic_words = set(topic_lower.split())

        similar = []

        for candidate in candidates:
            if candidate == topic:
                continue

            candidate_lower = candidate.lower()
            candidate_words = set(candidate_lower.split())

            # Check for high overlap
            overlap = len(topic_words & candidate_words) / min(len(topic_words), len(candidate_words))

            if overlap >= 0.5:
                similar.append(candidate)

        return similar


def test_fallback_system():
    """Test the hierarchical fallback system"""

    normalizer = TopicNormalizer()

    print("=" * 80)
    print("HIERARCHICAL FALLBACK TEST")
    print("=" * 80)
    print()

    # Test cases representing orphaned topics
    test_topics = [
        "3D Printing",
        "Academic Planning",
        "Supercomputer Access",
        "Network Configuration",
        "Data Backup",
        "Google Drive Storage",
        "Adobe Photoshop",
        "Student Email",
        "Research Grant Management",
        "Video Editing",
        "Troubleshooting Guide",
        "Canvas LMS",
        "Microsoft Office",
        "VPN Access",
        "Database Administration",
    ]

    print("Topic → Normalized → Fallback Category")
    print("-" * 80)

    for topic in test_topics:
        normalized, fallback = normalizer.normalize_with_fallback(topic)
        print(f"{topic:30} → {normalized:25} → {fallback}")

    print("\n" + "=" * 80)
    print("This ensures orphaned topics get assigned to broader categories")
    print("=" * 80)


if __name__ == '__main__':
    test_fallback_system()
