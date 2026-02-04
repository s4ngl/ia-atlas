"""
IA Reviewer - Generates human-readable review reports
Optionally uses LLM for qualitative critique
"""
import sys
from typing import List, Dict, Optional
from datetime import datetime

sys.path.append('/mnt/project')
from core.models import SidebarNode, IAIssue


class Reviewer:
    """
    Generates human-readable review reports for IA analysis
    Can optionally use LLM for qualitative insights
    """

    def __init__(self, db, llm_client=None):
        """
        Initialize reviewer

        Args:
            db: Database instance
            llm_client: Optional LLM client for qualitative analysis
        """
        self.db = db
        self.llm = llm_client

    def generate_review_report(
        self,
        sidebar_roots: List[SidebarNode],
        issues: List[IAIssue],
        output_path: str,
        include_llm_critique: bool = False
    ) -> bool:
        """
        Generate comprehensive review report

        Args:
            sidebar_roots: Sidebar structure
            issues: Detected IA issues
            output_path: Path to output markdown file
            include_llm_critique: Whether to include LLM analysis

        Returns:
            True if successful
        """
        print("\n" + "=" * 80)
        print("GENERATING REVIEW REPORT")
        print("=" * 80 + "\n")

        try:
            with open(output_path, 'w') as f:
                # Header
                f.write("# Information Architecture Review Report\n\n")
                f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write("---\n\n")

                # Executive Summary
                f.write("## Executive Summary\n\n")
                self._write_executive_summary(f, sidebar_roots, issues)
                f.write("\n---\n\n")

                # Sidebar Structure
                f.write("## Proposed Sidebar Structure\n\n")
                self._write_sidebar_structure(f, sidebar_roots)
                f.write("\n---\n\n")

                # Issues & Recommendations
                f.write("## Issues & Recommendations\n\n")
                self._write_issues_section(f, issues)
                f.write("\n---\n\n")

                # Topic Statistics
                f.write("## Topic Statistics\n\n")
                self._write_topic_statistics(f)
                f.write("\n---\n\n")

                # LLM Critique (optional)
                if include_llm_critique and self.llm:
                    f.write("## LLM Qualitative Analysis\n\n")
                    self._write_llm_critique(f, sidebar_roots, issues)
                    f.write("\n---\n\n")

                # Appendix
                f.write("## Appendix: Detailed Topic List\n\n")
                self._write_topic_appendix(f)

            print(f"✓ Review report generated: {output_path}")
            return True

        except Exception as e:
            print(f"✗ Failed to generate report: {e}")
            return False

    def _write_executive_summary(
        self,
        f,
        sidebar_roots: List[SidebarNode],
        issues: List[IAIssue]
    ):
        """Write executive summary section"""
        # Count total nodes
        total_nodes = sum(self._count_nodes(node) for node in sidebar_roots)

        # Count articles
        total_articles = sum(
            node.metrics.get('article_count', 0)
            for node in sidebar_roots
        )

        # Issue summary
        issue_counts = {
            'high': sum(1 for i in issues if i.severity == 'high'),
            'medium': sum(1 for i in issues if i.severity == 'medium'),
            'low': sum(1 for i in issues if i.severity == 'low')
        }

        f.write(f"### Overview\n\n")
        f.write(f"- **Top-level sections:** {len(sidebar_roots)}\n")
        f.write(f"- **Total sidebar nodes:** {total_nodes}\n")
        f.write(f"- **Articles organized:** {total_articles}\n")
        f.write(f"- **IA issues detected:** {len(issues)}\n")
        f.write(f"  - High severity: {issue_counts['high']}\n")
        f.write(f"  - Medium severity: {issue_counts['medium']}\n")
        f.write(f"  - Low severity: {issue_counts['low']}\n\n")

        # Key findings
        f.write("### Key Findings\n\n")

        if issue_counts['high'] > 0:
            f.write("⚠️  **Action Required:** High-severity issues detected that may impact usability.\n\n")

        # Find largest sections
        sections_by_size = sorted(
            sidebar_roots,
            key=lambda n: n.metrics.get('article_count', 0),
            reverse=True
        )[:3]

        if sections_by_size:
            f.write("**Largest sections:**\n")
            for node in sections_by_size:
                count = node.metrics.get('article_count', 0)
                f.write(f"- {node.title} ({count} articles)\n")
            f.write("\n")

    def _write_sidebar_structure(self, f, sidebar_roots: List[SidebarNode]):
        """Write sidebar structure section"""
        f.write("This section shows the recommended sidebar hierarchy.\n\n")

        for i, root in enumerate(sidebar_roots, 1):
            f.write(f"### {i}. {root.title}\n\n")
            f.write(f"**Articles:** {root.metrics.get('article_count', 0)}\n\n")

            # Write tree structure
            self._write_node_tree(f, root, indent=0)
            f.write("\n")

    def _write_node_tree(self, f, node: SidebarNode, indent: int = 0):
        """Recursively write node tree structure"""
        indent_str = "  " * indent

        for child in node.children:
            article_count = child.metrics.get('article_count', len(child.article_ids))
            f.write(f"{indent_str}- **{child.title}** ({article_count} articles)\n")

            if child.children:
                self._write_node_tree(f, child, indent + 1)

    def _write_issues_section(self, f, issues: List[IAIssue]):
        """Write issues and recommendations section"""
        if not issues:
            f.write("✓ No significant issues detected.\n\n")
            return

        # Group by severity
        issues_by_severity = {
            'high': [i for i in issues if i.severity == 'high'],
            'medium': [i for i in issues if i.severity == 'medium'],
            'low': [i for i in issues if i.severity == 'low']
        }

        for severity in ['high', 'medium', 'low']:
            severity_issues = issues_by_severity[severity]

            if not severity_issues:
                continue

            f.write(f"### {severity.upper()} Severity Issues\n\n")

            for i, issue in enumerate(severity_issues, 1):
                f.write(f"#### {i}. {issue.issue_type.replace('_', ' ').title()}\n\n")
                f.write(f"**Description:** {issue.description}\n\n")
                f.write(f"**Recommendation:** {issue.recommendation}\n\n")

                if issue.topic_id:
                    f.write(f"**Topic ID:** {issue.topic_id}\n\n")

                if issue.affected_articles:
                    f.write(f"**Affected items:** {len(issue.affected_articles)}\n\n")

                f.write("---\n\n")

    def _write_topic_statistics(self, f):
        """Write topic statistics section"""
        topics = self.db.get_all_topics()

        if not topics:
            f.write("No topic statistics available.\n\n")
            return

        # Calculate statistics
        total_topics = len(topics)
        total_articles = sum(t['total_articles'] for t in topics)
        avg_articles = total_articles / total_topics if total_topics > 0 else 0

        f.write(f"- **Total topics:** {total_topics}\n")
        f.write(f"- **Total articles:** {total_articles}\n")
        f.write(f"- **Average articles per topic:** {avg_articles:.1f}\n\n")

        # Top topics by article count
        top_topics = sorted(
            topics,
            key=lambda t: t['total_articles'],
            reverse=True
        )[:10]

        f.write("**Top 10 Topics by Article Count:**\n\n")
        f.write("| Rank | Topic | Articles |\n")
        f.write("|------|-------|----------|\n")

        for i, topic in enumerate(top_topics, 1):
            f.write(f"| {i} | {topic['name']} | {topic['total_articles']} |\n")

        f.write("\n")

    def _write_llm_critique(
        self,
        f,
        sidebar_roots: List[SidebarNode],
        issues: List[IAIssue]
    ):
        """Write LLM-generated qualitative critique"""
        if not self.llm:
            f.write("*LLM critique not available (no LLM client provided)*\n\n")
            return

        try:
            # Build context for LLM
            context = self._build_llm_context(sidebar_roots, issues)

            # Generate critique
            prompt = f"""You are an information architecture expert reviewing a documentation sidebar structure.

Context:
{context}

Please provide a qualitative critique covering:
1. Overall organization quality
2. Clarity and discoverability
3. Potential user navigation issues
4. Suggestions for improvement

Be specific and actionable. Focus on user experience."""

            response = self.llm.generate(prompt)

            if response:
                f.write(response)
                f.write("\n\n")
            else:
                f.write("*LLM critique generation failed*\n\n")

        except Exception as e:
            f.write(f"*Error generating LLM critique: {e}*\n\n")

    def _build_llm_context(
        self,
        sidebar_roots: List[SidebarNode],
        issues: List[IAIssue]
    ) -> str:
        """Build context string for LLM"""
        lines = []

        lines.append("SIDEBAR STRUCTURE:")
        for root in sidebar_roots[:5]:  # Top 5 sections
            lines.append(f"\n{root.title} ({root.metrics.get('article_count', 0)} articles)")
            for child in root.children[:3]:  # Top 3 children
                lines.append(f"  - {child.title}")

        lines.append("\n\nKEY ISSUES:")
        for issue in issues[:5]:  # Top 5 issues
            lines.append(f"- [{issue.severity}] {issue.description}")

        return "\n".join(lines)

    def _write_topic_appendix(self, f):
        """Write detailed topic list appendix"""
        topics = self.db.get_all_topics()

        if not topics:
            f.write("No topics available.\n\n")
            return

        # Sort alphabetically
        topics = sorted(topics, key=lambda t: t['name'])

        f.write("Complete list of all topics in alphabetical order:\n\n")
        f.write("| Topic | Articles | Intent Distribution |\n")
        f.write("|-------|----------|---------------------|\n")

        for topic in topics:
            intent_dist = topic.get('intent_distribution', {})
            intent_str = ", ".join(
                f"{k}: {v}" for k, v in sorted(intent_dist.items())
            ) if intent_dist else "N/A"

            f.write(f"| {topic['name']} | {topic['total_articles']} | {intent_str} |\n")

        f.write("\n")

    def _count_nodes(self, node: SidebarNode) -> int:
        """Recursively count nodes"""
        count = 1
        for child in node.children:
            count += self._count_nodes(child)
        return count

    def print_summary(
        self,
        sidebar_roots: List[SidebarNode],
        issues: List[IAIssue]
    ):
        """Print a quick summary to console"""
        print("\n" + "=" * 80)
        print("IA ANALYSIS SUMMARY")
        print("=" * 80)

        # Sidebar stats
        total_nodes = sum(self._count_nodes(node) for node in sidebar_roots)
        print(f"\nSidebar Structure:")
        print(f"  Top-level sections: {len(sidebar_roots)}")
        print(f"  Total nodes: {total_nodes}")

        # Issues stats
        print(f"\nIssues Detected: {len(issues)}")
        for severity in ['high', 'medium', 'low']:
            count = sum(1 for i in issues if i.severity == severity)
            if count > 0:
                print(f"  {severity.capitalize()}: {count}")

        # Top sections
        print("\nTop 3 Largest Sections:")
        sections = sorted(
            sidebar_roots,
            key=lambda n: n.metrics.get('article_count', 0),
            reverse=True
        )[:3]

        for i, section in enumerate(sections, 1):
            count = section.metrics.get('article_count', 0)
            print(f"  {i}. {section.title} ({count} articles)")

        print("\n" + "=" * 80)
