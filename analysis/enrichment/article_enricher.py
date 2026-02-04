"""
Article Enricher - Phase 1 Implementation
Enriches articles with semantic metadata using LLM
"""
import json
from typing import Dict, List, Optional
from datetime import datetime
import time

from core.models import ArticleEnrichment, IntentType, AudienceType, ComplexityLevel
from llm import OllamaClient, ARTICLE_ENRICHMENT_SYSTEM_PROMPT, create_enrichment_prompt
from persistence.database import EnrichedGraphDB


class ArticleEnricher:
    """
    Enriches articles with structured semantic metadata
    Uses local LLM via Ollama for extraction
    """
    
    def __init__(
        self,
        db: EnrichedGraphDB,
        llm_client: OllamaClient,
        batch_size: int = 10,
        rate_limit_delay: float = 0.5
    ):
        """
        Initialize article enricher
        
        Args:
            db: Database instance
            llm_client: Ollama client instance
            batch_size: Number of articles to process before committing
            rate_limit_delay: Delay between LLM calls (seconds)
        """
        self.db = db
        self.llm = llm_client
        self.batch_size = batch_size
        self.rate_limit_delay = rate_limit_delay
    
    def enrich_article(
        self,
        article_id: int,
        title: str,
        content: Optional[str] = None,
        use_content: bool = True
    ) -> Optional[ArticleEnrichment]:
        """
        Enrich a single article with semantic metadata
        
        Args:
            article_id: Article ID
            title: Article title
            content: Optional article content
            use_content: Whether to use content excerpt in prompt
            
        Returns:
            ArticleEnrichment object or None if failed
        """
        # Prepare content excerpt if available and requested
        content_excerpt = None
        if use_content and content:
            # Use first 500 chars of content as excerpt
            content_excerpt = content[:500].strip()
        
        # Create prompt
        prompt = create_enrichment_prompt(title, content_excerpt)
        
        # Call LLM
        try:
            response_json = self.llm.generate_json(
                prompt=prompt,
                system=ARTICLE_ENRICHMENT_SYSTEM_PROMPT,
                temperature=0.1
            )
            
            if not response_json:
                print(f"  ✗ Failed to get LLM response for article {article_id}")
                return None
            
            # Validate and extract fields
            enrichment = self._parse_enrichment_response(
                article_id,
                response_json
            )
            
            if enrichment:
                # Save to database
                enrichment_dict = {
                    'article_id': enrichment.article_id,
                    'canonical_topic': enrichment.canonical_topic,
                    'keywords': enrichment.keywords,
                    'intent': enrichment.intent.value if enrichment.intent else None,
                    'audience': enrichment.audience.value if enrichment.audience else None,
                    'prerequisites': enrichment.prerequisites,
                    'complexity': enrichment.complexity.value if enrichment.complexity else None,
                    'llm_model': self.llm.model
                }
                
                enrichment_id = self.db.save_enrichment(enrichment_dict)
                
                if enrichment_id:
                    enrichment.enriched_at = datetime.now()
                    enrichment.llm_model = self.llm.model
                    return enrichment
                else:
                    print(f"  ✗ Failed to save enrichment for article {article_id}")
                    return None
            
            return None
            
        except Exception as e:
            print(f"  ✗ Error enriching article {article_id}: {e}")
            return None
    
    def _parse_enrichment_response(
        self,
        article_id: int,
        response: Dict
    ) -> Optional[ArticleEnrichment]:
        """
        Parse LLM response into ArticleEnrichment object
        
        Args:
            article_id: Article ID
            response: JSON response from LLM
            
        Returns:
            ArticleEnrichment object or None if invalid
        """
        try:
            # Extract required field
            canonical_topic = response.get('canonical_topic', '').strip()
            if not canonical_topic:
                print(f"  ✗ Missing canonical_topic in response")
                return None
            
            # Extract optional fields with defaults
            keywords = response.get('keywords', [])
            if isinstance(keywords, str):
                keywords = [k.strip() for k in keywords.split(',')]
            
            intent_str = response.get('intent', 'unknown').lower()
            audience_str = response.get('audience', 'unknown').lower()
            complexity_str = response.get('complexity', 'unknown').lower()
            
            prerequisites = response.get('prerequisites', [])
            if isinstance(prerequisites, str):
                prerequisites = [p.strip() for p in prerequisites.split(',')]
            
            # Create enrichment object
            enrichment = ArticleEnrichment(
                article_id=article_id,
                canonical_topic=canonical_topic,
                keywords=keywords,
                intent=self._parse_intent(intent_str),
                audience=self._parse_audience(audience_str),
                prerequisites=prerequisites,
                complexity=self._parse_complexity(complexity_str)
            )
            
            return enrichment
            
        except Exception as e:
            print(f"  ✗ Error parsing enrichment response: {e}")
            return None
    
    @staticmethod
    def _parse_intent(intent_str: str) -> IntentType:
        """Parse intent string to enum"""
        intent_map = {
            'how-to': IntentType.HOW_TO,
            'howto': IntentType.HOW_TO,
            'overview': IntentType.OVERVIEW,
            'reference': IntentType.REFERENCE,
            'troubleshooting': IntentType.TROUBLESHOOTING,
            'policy': IntentType.POLICY
        }
        return intent_map.get(intent_str.lower(), IntentType.UNKNOWN)
    
    @staticmethod
    def _parse_audience(audience_str: str) -> AudienceType:
        """Parse audience string to enum"""
        audience_map = {
            'researcher': AudienceType.RESEARCHER,
            'faculty': AudienceType.FACULTY,
            'student': AudienceType.STUDENT,
            'admin': AudienceType.ADMIN,
            'general': AudienceType.GENERAL
        }
        return audience_map.get(audience_str.lower(), AudienceType.UNKNOWN)
    
    @staticmethod
    def _parse_complexity(complexity_str: str) -> ComplexityLevel:
        """Parse complexity string to enum"""
        complexity_map = {
            'beginner': ComplexityLevel.BEGINNER,
            'intermediate': ComplexityLevel.INTERMEDIATE,
            'advanced': ComplexityLevel.ADVANCED,
            'expert': ComplexityLevel.EXPERT
        }
        return complexity_map.get(complexity_str.lower(), ComplexityLevel.UNKNOWN)
    
    def enrich_batch(
        self,
        limit: int = 100,
        use_content: bool = True,
        verbose: bool = True
    ) -> Dict:
        """
        Enrich a batch of unenriched articles
        
        Args:
            limit: Maximum number of articles to process
            use_content: Whether to use content excerpts in prompts
            verbose: Whether to print progress
            
        Returns:
            Statistics dictionary
        """
        # Get unenriched articles
        articles = self.db.get_unenriched_articles(limit=limit)
        
        if not articles:
            if verbose:
                print("No unenriched articles found")
            return {
                'processed': 0,
                'successful': 0,
                'failed': 0
            }
        
        if verbose:
            print(f"Enriching {len(articles)} articles...")
            print("=" * 80)
        
        successful = 0
        failed = 0
        
        for i, article in enumerate(articles, 1):
            if verbose:
                print(f"\n[{i}/{len(articles)}] Processing: {article['title'][:60]}...")
            
            enrichment = self.enrich_article(
                article_id=article['id'],
                title=article['title'],
                content=article.get('content'),
                use_content=use_content
            )
            
            if enrichment:
                successful += 1
                if verbose:
                    print(f"  ✓ Topic: {enrichment.canonical_topic}")
                    print(f"  ✓ Intent: {enrichment.intent.value}")
                    print(f"  ✓ Complexity: {enrichment.complexity.value}")
            else:
                failed += 1
                if verbose:
                    print(f"  ✗ Failed to enrich")
            
            # Rate limiting
            if i < len(articles):
                time.sleep(self.rate_limit_delay)
        
        if verbose:
            print("\n" + "=" * 80)
            print(f"Enrichment complete: {successful} successful, {failed} failed")
        
        return {
            'processed': len(articles),
            'successful': successful,
            'failed': failed
        }
    
    def enrich_all(
        self,
        batch_size: Optional[int] = None,
        use_content: bool = True,
        verbose: bool = True
    ) -> Dict:
        """
        Enrich all unenriched articles in batches
        
        Args:
            batch_size: Size of each batch (uses self.batch_size if None)
            use_content: Whether to use content excerpts
            verbose: Whether to print progress
            
        Returns:
            Overall statistics
        """
        if batch_size is None:
            batch_size = self.batch_size
        
        total_successful = 0
        total_failed = 0
        batch_num = 1
        
        while True:
            if verbose:
                print(f"\n{'=' * 80}")
                print(f"BATCH {batch_num}")
                print(f"{'=' * 80}")
            
            stats = self.enrich_batch(
                limit=batch_size,
                use_content=use_content,
                verbose=verbose
            )
            
            if stats['processed'] == 0:
                break
            
            total_successful += stats['successful']
            total_failed += stats['failed']
            batch_num += 1
            
            # Small delay between batches
            time.sleep(1)
        
        if verbose:
            print(f"\n{'=' * 80}")
            print("ALL ENRICHMENT COMPLETE")
            print(f"{'=' * 80}")
            print(f"Total successful: {total_successful}")
            print(f"Total failed: {total_failed}")
        
        return {
            'total_successful': total_successful,
            'total_failed': total_failed,
            'batches_processed': batch_num - 1
        }
