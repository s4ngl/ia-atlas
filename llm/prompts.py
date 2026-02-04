
"""
Prompt templates for LLM-based article enrichment
"""

from typing import Optional

ARTICLE_ENRICHMENT_SYSTEM_PROMPT = """You are an expert in information architecture and knowledge organization for academic computing documentation.

Your task is to analyze article titles (and optional content excerpts) and extract structured metadata that will help organize these articles into a coherent documentation hierarchy.

You MUST respond with valid JSON only. Do not include any explanatory text before or after the JSON.

The JSON should follow this exact schema:
{
  "canonical_topic": "string - the main topic this article belongs to (e.g., 'Job Scheduling', 'File Transfer', 'Python Programming')",
  "keywords": ["array", "of", "strings - important terms and concepts"],
  "intent": "one of: how-to, overview, reference, troubleshooting, policy, unknown",
  "audience": "one of: researcher, faculty, student, admin, general, unknown",
  "prerequisites": ["array", "of", "strings - concepts/topics the reader should know first"],
  "complexity": "one of: beginner, intermediate, advanced, expert, unknown"
}

Guidelines:
- canonical_topic should be broad enough to group related articles but specific enough to be meaningful
- Keep canonical_topic names consistent and avoid redundancy (e.g., use "SLURM" not "SLURM Job Scheduling")
- keywords should include technical terms, tool names, and key concepts
- intent describes what the article aims to do (teach a task, provide overview, etc.)
- audience is the primary target reader
- prerequisites are concepts/topics needed BEFORE reading this article
- complexity is the technical level required to understand the article
"""


def create_enrichment_prompt(title: str, content_excerpt: Optional[str] = None) -> str:
    """
    Create a prompt for article enrichment

    Args:
        title: Article title
        content_excerpt: Optional content excerpt (first ~500 chars)

    Returns:
        Formatted prompt string
    """
    prompt = f"Article Title: {title}\n"

    if content_excerpt:
        # Truncate to reasonable length
        excerpt = content_excerpt[:500].strip()
        prompt += f"\nContent Excerpt:\n{excerpt}\n"

    prompt += "\nProvide the structured metadata as JSON:"

    return prompt


TOPIC_NORMALIZATION_SYSTEM_PROMPT = """You are an expert at normalizing and standardizing topic names for documentation hierarchies.

Your task is to take a list of raw topic names and produce normalized versions that:
1. Use consistent capitalization and formatting
2. Remove platform-specific details (e.g., cluster names like "Carbonate", "BigRed200")
3. Use standard terminology
4. Merge near-duplicates

Respond with valid JSON only:
{
  "normalized_topics": [
    {"original": "original topic name", "normalized": "standardized name"},
    ...
  ]
}

Examples:
- "Slurm job scheduling" → "Job Scheduling"
- "BigRed200 SLURM" → "Job Scheduling"
- "Python 3.9 on Carbonate" → "Python Programming"
- "GPU Computing" and "CUDA Programming" → keep separate (different enough)
"""


def create_topic_normalization_prompt(topic_names: list) -> str:
    """
    Create a prompt for topic normalization

    Args:
        topic_names: List of raw topic names

    Returns:
        Formatted prompt string
    """
    topics_text = "\n".join([f"- {name}" for name in topic_names])

    prompt = f"""Here are the raw topic names extracted from articles:

{topics_text}

Please provide normalized versions of these topics as JSON:"""

    return prompt


TOPIC_RELATIONSHIP_SYSTEM_PROMPT = """You are an expert at identifying relationships between documentation topics.

Given two topics and information about how articles in those topics link to each other, determine the relationship type.

Respond with valid JSON only:
{
  "relationship": "one of: subtopic_of, related_to, prerequisite_of, none",
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation"
}

Relationship definitions:
- subtopic_of: Topic A is a specific type or subset of Topic B (e.g., "SLURM Commands" is subtopic_of "Job Scheduling")
- prerequisite_of: Topic A must be understood before Topic B (e.g., "Linux Basics" prerequisite_of "Shell Scripting")
- related_to: Topics are related but neither is a subset or prerequisite (e.g., "Data Transfer" related_to "Storage Systems")
- none: No meaningful relationship
"""


def create_relationship_prompt(
    topic_a: str,
    topic_b: str,
    link_count: int,
    article_overlap: int
) -> str:
    """
    Create a prompt for determining topic relationships

    Args:
        topic_a: First topic name
        topic_b: Second topic name
        link_count: Number of links from A articles to B articles
        article_overlap: Number of articles that mention both topics

    Returns:
        Formatted prompt string
    """
    prompt = f"""Topic A: {topic_a}
Topic B: {topic_b}

Evidence:
- Articles in Topic A link to Topic B articles: {link_count} times
- Articles mention both topics: {article_overlap}

What is the relationship from Topic A to Topic B?
Provide your analysis as JSON:"""

    return prompt
