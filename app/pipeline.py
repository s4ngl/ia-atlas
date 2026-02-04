"""
Main Pipeline Orchestration
Coordinates the execution of all pipeline phases
"""
import sys, os
import argparse
from typing import Optional

# Add project root to path
sys.path.append('/mnt/project')

from config import DatabaseConfig
from persistence import EnrichedGraphDB
from llm import OllamaClient
from analysis.enrichment.article_enricher import ArticleEnricher
from analysis.topics.topic_graph import TopicGraphBuilder
from analysis.ia.analyzer import Analyzer
from analysis.ia.reviewer import Reviewer


class Pipeline:
    """
    Main pipeline orchestrator
    Runs Phases 1-3 of the knowledge graph construction
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
            ollama_url: URL for Ollama API
            ollama_model: Model name to use
        """
        self.db = None
        self.llm = None
        self.enricher = None
        self.graph_builder = None

        # Configuration
        self.ollama_url = ollama_url
        self.ollama_model = ollama_model
        self.output_dir = output_dir

        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)

    def initialize(self) -> bool:
        """
        Initialize all components

        Returns:
            True if successful
        """
        print("Initializing pipeline components...")
        print("=" * 80)

        # Initialize database
        try:
            self.db = EnrichedGraphDB()
            print("✓ Database initialized")
        except Exception as e:
            print(f"✗ Failed to initialize database: {e}")
            return False

        # Initialize LLM client
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
        # use_predetermined=True enables custom category structure
        self.ia_analyzer = Analyzer(db=self.db, use_predetermined=True)
        self.ia_reviewer = Reviewer(db=self.db, llm_client=self.llm)
        print("✓ IA analyzer and reviewer initialized (predetermined structure mode)")


        print("\n" + "=" * 80)
        print("All components initialized successfully")
        print("=" * 80 + "\n")

        return True

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
        print(f"Articles with content: {stats['total_articles']}")
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

    def run_full_pipeline(self, enrich_limit: Optional[int] = None):
        """
        Run the complete pipeline: Phase 1 -> Phase 2

        Args:
            enrich_limit: Optional limit for Phase 1 enrichment
        """
        print("\n" + "=" * 80)
        print("RUNNING FULL PIPELINE")
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
        enrich_stats = self.db.get_enrichment_stats()

        print("Phase 0 (Scraping):")
        print(f"  Total articles: {enrich_stats['total_articles']}")
        print()

        print("Phase 1 (Enrichment):")
        print(f"  Enriched: {enrich_stats['enriched_articles']}")
        print(f"  Remaining: {enrich_stats['unenriched_articles']}")
        completion = (enrich_stats['enriched_articles'] / enrich_stats['total_articles'] * 100
                     if enrich_stats['total_articles'] > 0 else 0)
        print(f"  Completion: {completion:.1f}%")
        print()

        print("Phase 2 (Topic Graph):")
        print(f"  Topics: {enrich_stats['total_topics']}")
        print(f"  Relationships: {enrich_stats['total_relationships']}")
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
        description="Knowledge Graph Pipeline for IU Documentation"
    )

    parser.add_argument(
        'command',
        choices=['status', 'phase1', 'phase2', 'phase3', 'full'],
        help='Command to run'
    )

    parser.add_argument(
        '--limit',
        type=int,
        help='Limit number of articles to process in Phase 1'
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
        ollama_model=args.ollama_model
    )

    # Initialize
    if not pipeline.initialize():
        print("\n✗ Pipeline initialization failed")
        return 1

    try:
        # Execute command
        if args.command == 'status':
            pipeline.show_status()

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
