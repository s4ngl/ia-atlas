"""
LLM module - handles all interactions with local language models via Ollama
"""
from .ollama_client import OllamaClient
from .prompts import (
    ARTICLE_ENRICHMENT_SYSTEM_PROMPT,
    create_enrichment_prompt,
    TOPIC_NORMALIZATION_SYSTEM_PROMPT,
    create_topic_normalization_prompt,
    TOPIC_RELATIONSHIP_SYSTEM_PROMPT,
    create_relationship_prompt
)

__all__ = [
    'OllamaClient',
    'ARTICLE_ENRICHMENT_SYSTEM_PROMPT',
    'create_enrichment_prompt',
    'TOPIC_NORMALIZATION_SYSTEM_PROMPT',
    'create_topic_normalization_prompt',
    'TOPIC_RELATIONSHIP_SYSTEM_PROMPT',
    'create_relationship_prompt'
]
