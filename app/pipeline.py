"""
Main Pipeline Orchestration
Coordinates the execution of all pipeline phases (0-3)
- Phase 0: Web scraping and article collection
- Phase 1: Article enrichment with LLM
- Phase 2: Topic graph construction
- Phase 3: Information architecture analysis
"""
import sys
import os
import argparse
import time
from typing import Optional, Dict, List

# Add project root to path
sys.path.append('/mnt/project')

from config import (
    DatabaseConfig,
    ServiceNowConfig,
    RequestConfig,
    CrawlConfig
)
from persistence import EnrichedGraphDB
from llm import OllamaClient
from analysis.enrichment.article_enricher import ArticleEnricher
from analysis.topics.topic_graph import TopicGraphBuilder
from analysis.ia.analyzer import Analyzer
from analysis.ia.reviewer import Reviewer


class Pipeline:
    """
    Unified pipeline orchestrator for all phases (0-3)
    Supports both scraping and analysis workflows
    """

    def __init__(
        self,
        ollama_url: str = "http://localhost:11434",
        ollama_model: str = "llama3.1:8b",
        output_dir: str = "./outputs"
    ):
        """
        Initialize pipeline

        Args:
            ollama_url: URL for Ollama API (Phases 1-3 only)
            ollama_model: Model name to use (Phases 1-3 only)
            output_dir: Output directory for Phase 3 files
        """
        self.db = None
        self.llm = None
        self.enricher = None
        self.graph_builder = None
        self.ia_analyzer = None
        self.ia_reviewer = None

        # Configuration objects
        self.servicenow_config = ServiceNowConfig()
        self.db_config = DatabaseConfig()
        self.crawl_config = CrawlConfig()
        self.request_config = RequestConfig()

        # Configuration
        self.ollama_url = ollama_url
        self.ollama_model = ollama_model
        self.output_dir = output_dir

        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)

    def initialize(self, skip_llm: bool = False) -> bool:
        """
        Initialize pipeline components

        Args:
            skip_llm: Skip LLM initialization (for Phase 0 only)

        Returns:
            True if successful
        """
        print("Initializing pipeline components...")
        print("=" * 80)

        # Initialize database (required for all phases)
        try:
            self.db = EnrichedGraphDB()
            print("✓ Database initialized")
        except Exception as e:
            print(f"✗ Failed to initialize database: {e}")
            return False

        # Skip LLM initialization if requested (Phase 0 only)
        if skip_llm:
            print("✓ Phase 0 mode - skipping LLM initialization")
            print("\n" + "=" * 80)
            print("Components initialized for Phase 0 (scraping)")
            print("=" * 80 + "\n")
            return True

        # Initialize LLM client (required for Phases 1-3)
        try:
            self.llm = OllamaClient(
                base_url=self.ollama_url,
                model=self.ollama_model
            )

            # Check connection
            if not self.llm.check_connection():
                print(f"✗ Cannot connect to Ollama at {self.ollama_url}")
                print("  Make sure Ollama is running: ollama serve")
                return False

            print(f"✓ Ollama client initialized ({self.ollama_model})")

            # Check if model is available
            models = self.llm.list_models()
            if self.ollama_model not in models:
                print(f"  Model {self.ollama_model} not found")
                print(f"  Available models: {', '.join(models)}")

                response = input(f"  Pull {self.ollama_model}? (y/n): ")
                if response.lower() == 'y':
                    if not self.llm.pull_model(self.ollama_model):
                        return False
                else:
                    return False

        except Exception as e:
            print(f"✗ Failed to initialize LLM client: {e}")
            return False

        # Initialize enricher
        self.enricher = ArticleEnricher(
            db=self.db,
            llm_client=self.llm,
            batch_size=10,
            rate_limit_delay=0.5
        )
        print("✓ Article enricher initialized")

        # Initialize graph builder
        self.graph_builder = TopicGraphBuilder(db=self.db)
        print("✓ Topic graph builder initialized")

        # Initialize IA analyzer and reviewer
        self.ia_analyzer = Analyzer(db=self.db, use_predetermined=True)
        self.ia_reviewer = Reviewer(db=self.db, llm_client=self.llm)
        print("✓ IA analyzer and reviewer initialized (predetermined structure mode)")

        print("\n" + "=" * 80)
        print("All components initialized successfully")
        print("=" * 80 + "\n")

        return True

    # ========================================================================
    # PHASE 0: WEB SCRAPING
    # ========================================================================

    def phase_0_scrape_articles(self, curl_file: str = "curl.txt") -> dict:
        """
        Phase 0: Scrape articles from ServiceNow

        Args:
            curl_file: Path to file containing cURL command with credentials

        Returns:
            Statistics dictionary
        """
        # Import scraping modules
        try:
            from ingestion.scraper import Fetcher, Frontier, Parser
        except ImportError:
            print("✗ Failed to import scraper modules")
            print("  Make sure scraper modules are in ingestion/scraper/")
            return {}

        print("\n" + "=" * 80)
        print("PHASE 0: WEB SCRAPING")
        print("=" * 80 + "\n")

        # Get credentials
        cookies, user_token = self._get_curl_credentials(curl_file)
        if not cookies or not user_token:
            return {}

        # Load keywords
        if not self.crawl_config.search_keywords:
            print("✗ Error: No keywords defined in config.py")
            print("  Please add keywords to SEARCH_KEYWORDS in config.py")
            return {}

        print(f"Loaded {len(self.crawl_config.search_keywords)} keyword(s) from config.py:")
        for keyword, depth in self.crawl_config.search_keywords:
            print(f"  • '{keyword}' (max depth: {depth})")
        print()

        # Initialize scraper components
        print("Initializing scraper components...")
        fetcher = Fetcher()
        parser = Parser()
        print("✓ Scraper components initialized")
        print()

        # Initialize frontier
        print("Initializing frontier...")
        frontier = Frontier(strategy=self.crawl_config.strategy)
        url_depths: Dict[str, int] = {}

        # Load already-crawled articles
        print("Loading already-crawled articles from database...")
        crawled_urls = self.db.get_crawled_article_urls()
        if crawled_urls:
            frontier.load_visited_urls(crawled_urls)
            print(f"✓ Loaded {len(crawled_urls)} already-crawled articles")
            print("  These articles will be skipped if encountered again")
        else:
            print("  No previously crawled articles found")
        print()

        # Process each keyword
        all_results = []
        try:
            for keyword, max_depth in self.crawl_config.search_keywords:
                result = self._crawl_keyword(
                    keyword=keyword,
                    max_depth=max_depth,
                    cookies=cookies,
                    user_token=user_token,
                    fetcher=fetcher,
                    parser=parser,
                    frontier=frontier,
                    url_depths=url_depths
                )
                all_results.append(result)

        except KeyboardInterrupt:
            print("\n\n✗ Crawl interrupted by user")
        finally:
            fetcher.close()

        # Print summary
        print("\n" + "=" * 80)
        print("PHASE 0 COMPLETE")
        print("=" * 80)

        total_crawled = sum(r['crawled'] for r in all_results)
        total_failed = sum(r['failed'] for r in all_results)

        for result in all_results:
            print(f"\nKeyword: '{result['keyword']}' (max depth: {result['max_depth']})")
            print(f"  Articles crawled: {result['crawled']}")
            print(f"  Articles failed:  {result['failed']}")
            if 'frontier_stats' in result:
                print(f"  URLs visited:     {result['frontier_stats']['visited']}")
                print(f"  URLs pending:     {result['frontier_stats']['pending']}")

        print("\n" + "-" * 80)
        print(f"Total articles crawled: {total_crawled}")
        print(f"Total articles failed:  {total_failed}")

        db_stats = self.db.get_stats()
        print("\nDatabase Statistics:")
        print(f"  Total articles:       {db_stats['total_articles']}")
        print(f"  Crawled articles:     {db_stats['crawled_articles']}")
        print(f"  Pending articles:     {db_stats['pending_articles']}")
        print(f"  Total links:          {db_stats['total_links']}")
        print()

        return {
            'total_crawled': total_crawled,
            'total_failed': total_failed,
            'keywords_processed': len(all_results),
            'db_stats': db_stats
        }

    def _get_curl_credentials(self, curl_file: str) -> tuple:
        """Read cURL command and extract credentials"""
        print(f"Reading {curl_file} for authentication credentials...")

        try:
            with open(curl_file, "r") as f:
                curl_command = f.read().strip()
        except FileNotFoundError:
            print(f"✗ Error: {curl_file} not found")
            print(f"  Please create {curl_file} with your cURL command")
            return None, None

        if not curl_command:
            print(f"✗ Error: {curl_file} is empty")
            return None, None

        # Parse curl command
        from ingestion.scraper import Fetcher
        fetcher = Fetcher()
        cookies, user_token = fetcher.parse_curl_command(curl_command)

        if not cookies or not user_token:
            print("✗ Error: Could not extract cookies and user token from cURL command")
            print("  Make sure you copied the complete cURL command including headers")
            return None, None

        print("✓ Successfully parsed authentication credentials")
        print()
        return cookies, user_token

    def _crawl_keyword(
        self,
        keyword: str,
        max_depth: int,
        cookies: str,
        user_token: str,
        fetcher,
        parser,
        frontier,
        url_depths: Dict[str, int]
    ) -> dict:
        """Crawl articles for a single keyword"""
        print("\n" + "=" * 80)
        print(f"Starting crawl for keyword: '{keyword}' (max depth: {max_depth})")
        print("=" * 80 + "\n")

        # Search for keyword
        print(f"Searching for: '{keyword}'")
        print("-" * 80)

        search_results = fetcher.search_articles(keyword, cookies, user_token)

        if not search_results:
            print("✗ No articles found or search failed")
            return {
                'keyword': keyword,
                'crawled': 0,
                'failed': 0,
                'max_depth': max_depth,
                'frontier_stats': frontier.get_stats()
            }

        print(f"✓ Found {len(search_results)} articles")

        # Create metadata map
        metadata_map = {}
        for article in search_results:
            url = article.get('url', '')
            if url:
                normalized_url = frontier._normalize_url(url)
                metadata_map[normalized_url] = article
                frontier.add(url)
                url_depths[normalized_url] = 0

        print(f"Added {len(search_results)} articles to crawl queue")
        print()

        # Crawl loop
        print("Starting crawl...")
        print("-" * 80)
        print()

        crawled_count = 0
        failed_count = 0
        selenium_errors = 0

        try:
            while not frontier.is_empty():
                if self.crawl_config.max_articles_per_keyword and crawled_count >= self.crawl_config.max_articles_per_keyword:
                    print(f"\n✓ Reached maximum articles limit ({self.crawl_config.max_articles_per_keyword})")
                    break

                url = frontier.get_next()
                if not url:
                    break

                current_depth = url_depths.get(url, 0)

                # Check if article exists
                full_url = self._denormalize_url(url)
                existing_article = self.db.get_article_by_url(full_url)

                # Skip if already crawled
                if existing_article and existing_article.get('content') and existing_article['content'].strip():
                    content = existing_article.get('content', '')
                    if content.startswith('[BROKEN ARTICLE:') or content.startswith('[MINIMAL CONTENT:'):
                        print(f"\n[Skipped] Known broken/minimal article")
                        print(f"  URL: {url}")
                        continue

                    print(f"\n[Skipped] Article already crawled")
                    print(f"  URL: {url}")
                    print(f"  Title: {existing_article.get('title', 'Unknown')}")

                    # Add links to frontier if not at max depth
                    if current_depth < max_depth:
                        links = self.db.get_article_links(existing_article['id'])
                        added = 0
                        for link in links:
                            if frontier.add(link):
                                normalized_link = frontier._normalize_url(link)
                                url_depths[normalized_link] = current_depth + 1
                                added += 1

                        if added > 0:
                            print(f"  ✓ Added {added} linked articles to queue (depth {current_depth + 1})")

                    continue

                print(f"\n[{crawled_count + 1}] Crawling article...")

                # Get metadata
                metadata = metadata_map.get(url)

                # Crawl article
                try:
                    success, depth = self._crawl_article(
                        fetcher=fetcher,
                        parser=parser,
                        url=url,
                        cookies=cookies,
                        article_metadata=metadata,
                        current_depth=current_depth
                    )

                    if success:
                        crawled_count += 1
                        selenium_errors = 0

                        # Add links to frontier
                        article = self.db.get_article_by_url(full_url)
                        if article and current_depth < max_depth:
                            links = self.db.get_article_links(article['id'])
                            added = 0
                            for link in links:
                                if frontier.add(link):
                                    normalized_link = frontier._normalize_url(link)
                                    url_depths[normalized_link] = current_depth + 1
                                    added += 1

                            if added > 0:
                                print(f"  ✓ Added {added} new articles to queue (depth {current_depth + 1})")
                        elif current_depth >= max_depth:
                            print(f"  → Max depth reached, not adding linked articles")
                    else:
                        failed_count += 1

                except Exception as e:
                    print(f"  ✗ Error crawling article: {e}")
                    failed_count += 1
                    selenium_errors += 1

                    # Restart Selenium if multiple errors
                    if selenium_errors >= 3:
                        print("  → Multiple Selenium errors, attempting restart...")
                        try:
                            fetcher.close()
                            fetcher._init_selenium()
                            selenium_errors = 0
                            print("  ✓ Selenium driver restarted")
                        except Exception as restart_error:
                            print(f"  ✗ Failed to restart Selenium: {restart_error}")

                # Print progress
                stats = frontier.get_stats()
                print(f"  Progress: {stats['visited']} visited, {stats['pending']} pending")

        except KeyboardInterrupt:
            print("\n\n✗ Crawl interrupted by user")

        return {
            'keyword': keyword,
            'crawled': crawled_count,
            'failed': failed_count,
            'max_depth': max_depth,
            'frontier_stats': frontier.get_stats()
        }

    def _crawl_article(
        self,
        fetcher,
        parser,
        url: str,
        cookies: str,
        article_metadata: Optional[dict] = None,
        current_depth: int = 0
    ) -> tuple:
        """Crawl a single article"""
        full_url = self._denormalize_url(url)

        print(f"  Fetching: {url}")
        print(f"  Depth: {current_depth}")

        # Fetch HTML
        html = fetcher.fetch_article_html(full_url, cookies)
        if not html:
            print(f"  ✗ Failed to fetch article")
            return False, current_depth

        # Parse article
        article = parser.extract_article(html, full_url)

        # Check for generic error pages
        generic_titles = [
            "Knowledge Article View - IUKB",
            "Indiana University - ServiceNow",
            "Login",
            "Page Not Found",
            "Access Denied"
        ]

        if article['title'] in generic_titles:
            if article_metadata and article_metadata.get('title'):
                print(f"  ⚠ Warning: Generic page but article exists in search results")
                print(f"     This might be an authentication issue")
                print(f"  ⚠ Skipping without marking as broken")
                return False, current_depth
            else:
                print(f"  ⚠ Skipping generic redirect/error page: {article['title']}")
                article_stub = {
                    'url': full_url,
                    'title': article['title'],
                    'content': f"[BROKEN ARTICLE: {article['title']}]",
                    'links': [],
                    'depth': current_depth
                }
                if article_metadata:
                    article_stub.update({
                        'number': article_metadata.get('number', ''),
                        'display_number': article_metadata.get('display_number', ''),
                        'snippet': article_metadata.get('snippet', ''),
                        'score': article_metadata.get('score', 0),
                        'can_read': article_metadata.get('can_read', 'Public'),
                    })
                self.db.save_article(article_stub)
                return False, current_depth

        # Check for minimal content
        if len(article.get('content', '')) < 100:
            print(f"  ⚠ Skipping page with minimal content")
            article['content'] = f"[MINIMAL CONTENT: {len(article.get('content', ''))} chars]"
            if article_metadata:
                article.update({
                    'number': article_metadata.get('number', ''),
                    'display_number': article_metadata.get('display_number', ''),
                    'snippet': article_metadata.get('snippet', ''),
                    'score': article_metadata.get('score', 0),
                    'can_read': article_metadata.get('can_read', 'Public'),
                })
            article['depth'] = current_depth
            self.db.save_article(article)
            return False, current_depth

        # Add metadata
        if article_metadata:
            article.update({
                'number': article_metadata.get('number', ''),
                'display_number': article_metadata.get('display_number', ''),
                'snippet': article_metadata.get('snippet', ''),
                'score': article_metadata.get('score', 0),
                'can_read': article_metadata.get('can_read', 'Public'),
            })

        article['depth'] = current_depth

        # Save article
        article_id = self.db.save_article(article)
        if article_id:
            print(f"  ✓ Saved article (ID: {article_id})")
            print(f"    Title: {article['title']}")
            print(f"    Links found: {len(article['links'])}")
            return True, current_depth
        else:
            print(f"  ✗ Failed to save article")
            return False, current_depth

    def _denormalize_url(self, url: str) -> str:
        """Convert normalized URL to full URL"""
        if url.startswith('sys_kb_id:'):
            sys_kb_id = url.split(':', 1)[1]
            return f"{self.servicenow_config.base_url}/kb?id=kb_article_view&sys_kb_id={sys_kb_id}"
        return url

    # ========================================================================
    # PHASE 1: ARTICLE ENRICHMENT
    # ========================================================================

    def phase_1_enrich_articles(
        self,
        limit: Optional[int] = None,
        use_content: bool = True
    ) -> dict:
        """
        Phase 1: Article Enrichment
        Extracts semantic metadata from articles using LLM

        Args:
            limit: Maximum number of articles to enrich (None for all)
            use_content: Whether to use content excerpts in prompts

        Returns:
            Statistics dictionary
        """
        print("\n" + "=" * 80)
        print("PHASE 1: ARTICLE ENRICHMENT")
        print("=" * 80 + "\n")

        # Show current stats
        stats = self.db.get_enrichment_stats()
        print(f"Articles with content: {stats['crawled_articles']}")
        print(f"Already enriched: {stats['enriched_articles']}")
        print(f"Remaining: {stats['unenriched_articles']}")
        print()

        if stats['unenriched_articles'] == 0:
            print("All articles already enriched!")
            return stats

        # Run enrichment
        if limit:
            result = self.enricher.enrich_batch(
                limit=limit,
                use_content=use_content,
                verbose=True
            )
        else:
            result = self.enricher.enrich_all(
                use_content=use_content,
                verbose=True
            )

        # Show final stats
        print("\n" + "=" * 80)
        print("PHASE 1 COMPLETE")
        print("=" * 80)

        final_stats = self.db.get_enrichment_stats()
        print(f"Total enriched: {final_stats['enriched_articles']}")
        print(f"Remaining: {final_stats['unenriched_articles']}")

        return result

    # ========================================================================
    # PHASE 2: TOPIC GRAPH CONSTRUCTION
    # ========================================================================

    def phase_2_build_topic_graph(self) -> dict:
        """
        Phase 2: Topic Graph Construction
        Builds topics and infers relationships

        Returns:
            Statistics dictionary
        """
        print("\n" + "=" * 80)
        print("PHASE 2: TOPIC GRAPH CONSTRUCTION")
        print("=" * 80 + "\n")

        # Check if enrichment is done
        stats = self.db.get_enrichment_stats()
        if stats['enriched_articles'] == 0:
            print("✗ No enriched articles found. Run Phase 1 first.")
            return {}

        print(f"Building topics from {stats['enriched_articles']} enriched articles...")
        print()

        # Build topics
        topics = self.graph_builder.build_topics_from_enrichment(
            save_to_db=True,
            verbose=True
        )

        # Infer relationships
        relationships = self.graph_builder.infer_topic_relationships(
            save_to_db=True,
            verbose=True
        )

        # Get statistics
        topic_stats = self.graph_builder.get_topic_stats()

        print("\n" + "=" * 80)
        print("PHASE 2 COMPLETE")
        print("=" * 80)
        print(f"Topics created: {topic_stats['total_topics']}")
        print(f"Relationships: {len(relationships)}")
        print(f"Avg articles per topic: {topic_stats['avg_articles_per_topic']:.1f}")

        return {
            'topics': len(topics),
            'relationships': len(relationships),
            'stats': topic_stats
        }

    # ========================================================================
    # PHASE 3: INFORMATION ARCHITECTURE ANALYSIS
    # ========================================================================

    def phase_3_analyze_ia(
        self,
        export_json: bool = True,
        export_markdown: bool = True,
        include_llm_critique: bool = False
    ) -> dict:
        """
        Phase 3: Information Architecture Analysis
        Generates sidebar structure and detects issues

        Args:
            export_json: Export sidebar and issues as JSON
            export_markdown: Export review report as Markdown
            include_llm_critique: Include LLM qualitative analysis

        Returns:
            Statistics dictionary
        """
        print("\n" + "=" * 80)
        print("PHASE 3: INFORMATION ARCHITECTURE ANALYSIS")
        print("=" * 80 + "\n")

        # Check prerequisites
        stats = self.db.get_enrichment_stats()
        if stats['total_topics'] == 0:
            print("✗ No topics found. Run Phase 2 first.")
            return {}

        # Load topic data
        if not self.ia_analyzer.load_topic_data():
            print("✗ Failed to load topic data")
            return {}

        # Build sidebar structure
        sidebar_roots = self.ia_analyzer.build_sidebar_tree(verbose=True)

        # Detect IA issues
        issues = self.ia_analyzer.detect_ia_issues()

        # Print preview
        self.ia_analyzer.print_sidebar_preview(sidebar_roots, max_items=5)

        # Export outputs
        outputs = []

        if export_json:
            # Export sidebar JSON
            sidebar_path = os.path.join(self.output_dir, "sidebar_structure.json")
            if self.ia_analyzer.export_sidebar_json(sidebar_roots, sidebar_path):
                outputs.append(sidebar_path)

            # Export issues JSON
            issues_path = os.path.join(self.output_dir, "ia_issues.json")
            if self.ia_analyzer.export_issues_report(issues, issues_path):
                outputs.append(issues_path)

        if export_markdown:
            # Export review report
            report_path = os.path.join(self.output_dir, "ia_review_report.md")
            if self.ia_reviewer.generate_review_report(
                sidebar_roots=sidebar_roots,
                issues=issues,
                output_path=report_path,
                include_llm_critique=include_llm_critique
            ):
                outputs.append(report_path)

        # Print summary
        self.ia_reviewer.print_summary(sidebar_roots, issues)

        print("\n" + "=" * 80)
        print("PHASE 3 COMPLETE")
        print("=" * 80)
        print(f"Sidebar sections: {len(sidebar_roots)}")
        print(f"Issues detected: {len(issues)}")
        print(f"Outputs generated: {len(outputs)}")
        for output in outputs:
            print(f"  - {output}")

        return {
            'sidebar_sections': len(sidebar_roots),
            'issues_detected': len(issues),
            'outputs': outputs
        }

    # ========================================================================
    # MULTI-PHASE WORKFLOWS
    # ========================================================================

    def run_full_pipeline(self, enrich_limit: Optional[int] = None):
        """
        Run the complete analysis pipeline: Phase 1 -> Phase 2 -> Phase 3

        Args:
            enrich_limit: Optional limit for Phase 1 enrichment
        """
        print("\n" + "=" * 80)
        print("RUNNING FULL ANALYSIS PIPELINE (Phases 1-3)")
        print("=" * 80 + "\n")

        # Phase 1
        phase1_result = self.phase_1_enrich_articles(limit=enrich_limit)

        # Phase 2
        phase2_result = self.phase_2_build_topic_graph()

        # Phase 3
        phase3_result = self.phase_3_analyze_ia()

        print("\n" + "=" * 80)
        print("PIPELINE COMPLETE")
        print("=" * 80)
        print("Phase 1 (Enrichment):")
        print(f"  Successful: {phase1_result.get('successful', phase1_result.get('total_successful', 0))}")
        print(f"  Failed: {phase1_result.get('failed', phase1_result.get('total_failed', 0))}")
        print("\nPhase 2 (Topic Graph):")
        print(f"  Topics: {phase2_result.get('topics', 0)}")
        print(f"  Relationships: {phase2_result.get('relationships', 0)}")
        print("\nPhase 3 (IA Analysis):")
        print(f"  Sidebar Sections: {phase3_result.get('sidebar_sections', 0)}")
        print(f"  Issues Detected: {phase3_result.get('issues_detected', 0)}")
        print(f"  Outputs Generated: {len(phase3_result.get('outputs', []))}")

    def show_status(self):
        """Display current pipeline status"""
        print("\n" + "=" * 80)
        print("PIPELINE STATUS")
        print("=" * 80 + "\n")

        # Database stats
        stats = self.db.get_stats()

        print("Phase 0 (Scraping):")
        print(f"  Total articles:       {stats['total_articles']}")
        print(f"  Crawled articles:     {stats['crawled_articles']}")
        print(f"  Pending articles:     {stats['pending_articles']}")
        print(f"  Total links:          {stats['total_links']}")
        print()

        print("Phase 1 (Enrichment):")
        print(f"  Enriched:             {stats['enriched_articles']}")
        print(f"  Remaining:            {stats['unenriched_articles']}")
        completion = (stats['enriched_articles'] / stats['crawled_articles'] * 100
                     if stats['crawled_articles'] > 0 else 0)
        print(f"  Completion:           {completion:.1f}%")
        print()

        print("Phase 2 (Topic Graph):")
        print(f"  Topics:               {stats['total_topics']}")
        print(f"  Relationships:        {stats['total_relationships']}")
        print()

        print("Phase 3 (IA Analysis):")
        print("  (Run Phase 3 to analyze information architecture)")
        print("=" * 80)
        print()

    def cleanup(self):
        """Clean up resources"""
        if self.db:
            self.db.close()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Knowledge Graph Pipeline for ServiceNow Documentation"
    )

    parser.add_argument(
        'command',
        choices=['status', 'phase0', 'phase1', 'phase2', 'phase3', 'full'],
        help='Command to run'
    )

    parser.add_argument(
        '--limit',
        type=int,
        help='Limit number of articles to process in Phase 1'
    )

    parser.add_argument(
        '--curl-file',
        default='curl.txt',
        help='Path to cURL credentials file for Phase 0'
    )

    parser.add_argument(
        '--ollama-url',
        default='http://localhost:11434',
        help='Ollama API URL'
    )

    parser.add_argument(
        '--ollama-model',
        default='llama3.1:8b',
        help='Ollama model name'
    )

    parser.add_argument(
        '--output-dir',
        default='./outputs/',
        help='Output directory for Phase 3 files'
    )

    parser.add_argument(
        '--llm-critique',
        action='store_true',
        help='Include LLM qualitative critique in Phase 3'
    )

    args = parser.parse_args()

    # Create pipeline
    pipeline = Pipeline(
        ollama_url=args.ollama_url,
        ollama_model=args.ollama_model,
        output_dir=args.output_dir
    )

    # Initialize based on command
    skip_llm = (args.command == 'phase0')
    if not pipeline.initialize(skip_llm=skip_llm):
        print("\n✗ Pipeline initialization failed")
        return 1

    try:
        # Execute command
        if args.command == 'status':
            pipeline.show_status()

        elif args.command == 'phase0':
            pipeline.phase_0_scrape_articles(curl_file=args.curl_file)

        elif args.command == 'phase1':
            pipeline.phase_1_enrich_articles(limit=args.limit)

        elif args.command == 'phase2':
            pipeline.phase_2_build_topic_graph()

        elif args.command == 'phase3':
            pipeline.phase_3_analyze_ia(
                export_json=True,
                export_markdown=True,
                include_llm_critique=args.llm_critique
            )

        elif args.command == 'full':
            pipeline.run_full_pipeline(enrich_limit=args.limit)

    finally:
        pipeline.cleanup()

    return 0


if __name__ == '__main__':
    sys.exit(main())
