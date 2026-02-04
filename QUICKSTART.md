# Quick Start Guide

Get up and running with the ServiceNow KB Analysis Pipeline in minutes.

## Prerequisites

- Python 3.9+
- PostgreSQL
- Ollama (Phases 1-3 only)

## Setup (One-time)

### 1. Install Python Dependencies
```bash
pip install -r requirements.txt
```

### 2. Create Database
```bash
createdb kb_graph
```

### 3. Configure Database
Edit `config/config.py`:
```python
DatabaseConfig = {
    'dbname': 'kb_graph',
    'user': 'your_username',
    'password': 'your_password',
    'host': 'localhost',
    'port': 5432
}
```

### 4. Install Ollama (for Phases 1-3)
```bash
# Download from https://ollama.ai
ollama serve

# Pull model
ollama pull llama3.1:8b
```

## Phase 0: Scraping

### Configure Scraping

Edit `config/config.py`:

```python
# Your ServiceNow instance
SERVICENOW_BASE_URL = "https://your-instance.service-now.com"

# Keywords to search with max crawl depth
SEARCH_KEYWORDS = [
    ("Canvas", 2),      # Search "Canvas", crawl links up to depth 2
    ("Email", 1),       # Search "Email", crawl links up to depth 1
    ("VPN", 2),         # Search "VPN", crawl links up to depth 2
]

# Crawl strategy: "bfs" (breadth-first) or "dfs" (depth-first)
CRAWL_STRATEGY = "bfs"

# Optional: limit articles per keyword
MAX_ARTICLES_PER_KEYWORD = None  # None = unlimited
```

### Get Authentication

You need to extract authentication from your browser:

1. **Open Firefox or Chrome** → Navigate to your ServiceNow KB
2. **Press F12** → Go to **Network tab**
3. **Perform a search** in the knowledge base
4. **Find the search API request** (look for POST to `/api/now/sp` or similar)
5. **Right-click the request** → Copy → **Copy as cURL**
6. **Paste the entire command** into `config/curl.txt`

Example `config/curl.txt`:
```bash
curl 'https://your-instance.service-now.com/api/now/sp' \
  -H 'Cookie: JSESSIONID=...; glide_user_route=...' \
  -H 'X-UserToken: abc123...' \
  --data-raw '{"query":"canvas"}'
```

⚠️ **Important**: Copy the **complete** cURL command including all headers. The pipeline extracts authentication automatically.

### Run Scraper

```bash
python -m app.pipeline phase0
```

**What happens:**
- Searches ServiceNow for your configured keywords
- Crawls articles and follows internal links up to specified depth
- Saves articles, content, and relationships to PostgreSQL
- Skips already-crawled URLs (resumable if interrupted)

**Output:**
```
Phase 0 Complete
================================================================================
Keyword: 'Canvas' (max depth: 2)
  Articles crawled: 487
  Articles failed:  3

Database Statistics:
  Total articles:       1,247
  Crawled articles:     1,247
  Total links:          3,891
```

### Understanding Crawl Depth

- **Depth 0**: Only articles from the search results
- **Depth 1**: Search results + articles they link to
- **Depth 2**: Search results + links + links from those links

Example: Searching "Canvas" with depth 2:
1. Find all articles matching "Canvas" (depth 0)
2. Extract links from those articles and crawl them (depth 1)
3. Extract links from depth 1 articles and crawl them (depth 2)

### Crawl Strategies

**BFS (Breadth-First Search)** - Default
- Crawls all depth 0 articles first, then all depth 1, then depth 2
- Best for: Getting a broad overview quickly
- Use when: You want comprehensive coverage at each level

**DFS (Depth-First Search)**
- Follows each article's links deeply before moving to next article
- Best for: Exploring topic hierarchies and dependencies
- Use when: You want to understand deep relationships

Set in `config/config.py`:
```python
CRAWL_STRATEGY = "bfs"  # or "dfs"
```

### Resuming Interrupted Crawls

Phase 0 tracks all crawled URLs. If interrupted:
- Already-crawled articles are skipped automatically
- Pending URLs remain in queue
- Just re-run `python -m app.pipeline phase0`

No need to start over!

## Phases 1-3: Analysis Pipeline

### Check Status

```bash
python -m app.pipeline status
```

Example output:
```
Phase 0 (Scraping):
  Total articles:       1,247
  Crawled articles:     1,247

Phase 1 (Enrichment):
  Enriched articles:    0
  Remaining articles:   1,247

Phase 2 (Topic Graph):
  Topics extracted:     0
```

### Phase 1: Enrich Articles

Extract semantic metadata with LLM:

```bash
# Enrich all articles
python -m app.pipeline phase1

# Or limit to first 100
python -m app.pipeline phase1 --limit 100
```

**What it does:**
- Extracts canonical topics
- Identifies keywords
- Determines user intent (learn/troubleshoot/setup)
- Tags target audience
- Lists prerequisites
- Assesses complexity

**Processing time:** ~2-5 seconds per article with llama3.1:8b

**Tip:** Start with `--limit 100` to test before processing all articles.

### Phase 2: Build Topic Graph

Construct topic hierarchy:

```bash
python -m app.pipeline phase2
```

**What it does:**
- Aggregates topics from enriched articles
- Normalizes similar topics ("Canvas LMS" → "Canvas")
- Infers relationships (parent, prerequisite, related)
- Computes graph metrics

**Requires:** Phase 1 must be complete (or partially complete)

### Phase 3: Analyze Information Architecture

Generate sidebar and detect issues:

```bash
# Standard analysis
python -m app.pipeline phase3

# With LLM qualitative critique (slower)
python -m app.pipeline phase3 --llm-critique
```

**What it does:**
- Builds hierarchical sidebar structure
- Detects IA issues (orphans, overloads, shallow hierarchies)
- Generates review reports

**Outputs:**
- `outputs/sidebar_structure.json` - Hierarchical navigation structure
- `outputs/ia_issues.json` - Detected problems with severity levels
- `outputs/ia_review_report.md` - Human-readable summary

**Requires:** Phase 2 must be complete

### Run Everything

Execute all phases in sequence:

```bash
python -m app.pipeline full
```

Runs: Phase 0 → Phase 1 → Phase 2 → Phase 3

## Common Commands

```bash
# Check pipeline status
python -m app.pipeline status

# Scrape articles
python -m app.pipeline phase0

# Enrich 50 articles
python -m app.pipeline phase1 --limit 50

# Build topic graph
python -m app.pipeline phase2

# Generate IA analysis with critique
python -m app.pipeline phase3 --llm-critique

# Run all phases
python -m app.pipeline full
```

## Example Workflow

```bash
# 1. Configure scraping in config/config.py
#    - Set SERVICENOW_BASE_URL
#    - Set SEARCH_KEYWORDS
#    - Save cURL auth to config/curl.txt

# 2. Scrape articles
python -m app.pipeline phase0
# Output: "Total articles: 1247, Crawled: 1247"

# 3. Check status
python -m app.pipeline status

# 4. Enrich in batches (test with small batch first)
python -m app.pipeline phase1 --limit 100
# Wait for completion...
python -m app.pipeline phase1 --limit 100
# Repeat until all enriched, or run without --limit for all

# 5. Build topic graph
python -m app.pipeline phase2

# 6. Analyze IA
python -m app.pipeline phase3 --llm-critique

# 7. Review outputs
cat outputs/ia_review_report.md
```

## Key Features

✅ **Fully Automated**: Configure once in files, no interactive prompts
✅ **Batched Processing**: Enrich in chunks with `--limit`
✅ **Resumable**: Pipeline tracks progress, can restart anytime
✅ **Local LLM**: Uses Ollama (no API costs)
✅ **Structured Output**: JSON + Markdown reports

## Pipeline Flow

```
Phase 0 (Scraping)
  ↓
articles → links
  ↓
Phase 1 (Enrichment)
  ↓
article_enrichment
  ↓
Phase 2 (Topic Graph)
  ↓
topics → topic_articles → topic_relationships
  ↓
Phase 3 (IA Analysis)
  ↓
sidebar_structure.json
ia_issues.json
ia_review_report.md
```

## Configuration Reference

### Pipeline Arguments

```bash
python -m app.pipeline [command] [options]

Commands:
  status              Show pipeline progress
  phase0              Run scraping
  phase1              Run enrichment
  phase2              Build topic graph
  phase3              Analyze IA
  full                Run all phases

Options:
  --limit N           Process only N articles (phase1)
  --ollama-url URL    Ollama endpoint (default: http://localhost:11434)
  --ollama-model M    Model name (default: llama3.1:8b)
  --output-dir DIR    Output directory (default: ./outputs/)
  --llm-critique      Include LLM critique in phase3
```

### Config.py Settings

```python
# ServiceNow Configuration
SERVICENOW_BASE_URL = "https://your-instance.service-now.com"

# Phase 0: Scraping
SEARCH_KEYWORDS = [
    ("Canvas", 2),
    ("Email", 1),
]
CRAWL_STRATEGY = "bfs"  # or "dfs"
MAX_ARTICLES_PER_KEYWORD = None  # None = unlimited
REQUEST_DELAY = 1.0  # seconds between requests

# Database
DatabaseConfig = {
    'dbname': 'kb_graph',
    'user': 'your_username',
    'password': 'your_password',
    'host': 'localhost',
    'port': 5432
}
```

## Common Issues

### Phase 0

**"Could not extract cookies/user token"**
```bash
# Make sure config/curl.txt contains the COMPLETE cURL command
# Check that it includes Cookie and X-UserToken headers
cat config/curl.txt
```

**"No articles found or search failed"**
```bash
# Verify your ServiceNow URL
# Check authentication hasn't expired (re-copy cURL if needed)
# Try searching manually on ServiceNow to confirm keyword works
```

**Authentication expires**
```bash
# ServiceNow sessions expire after inactivity
# Solution: Re-copy the cURL command from browser to config/curl.txt
# Then re-run: python -m app.pipeline phase0
```

### Phase 1

**"Cannot connect to Ollama"**
```bash
# Start Ollama server
ollama serve
```

**"Model not found"**
```bash
# Pull the model
ollama pull llama3.1:8b
```

**Slow enrichment**
```bash
# Use smaller model
python -m app.pipeline phase1 --ollama-model llama3.1:8b

# Or process in smaller batches
python -m app.pipeline phase1 --limit 50
```

### General Issues

**"Database connection failed"**
```bash
# Check PostgreSQL is running
pg_isready

# Verify config/config.py credentials
psql -U your_username -d kb_graph -c "SELECT 1;"
```

**"No enriched articles found" (Phase 2 or 3)**
```bash
# Run previous phases first
python -m app.pipeline phase1
python -m app.pipeline phase2
```

## Database Quick Reference

### Check Progress
```sql
-- Phase 0: Scraping status
SELECT
  COUNT(*) as total,
  COUNT(*) FILTER (WHERE crawled_at IS NOT NULL) as crawled,
  COUNT(*) FILTER (WHERE crawled_at IS NULL) as pending
FROM articles;

-- Phase 1: Enrichment status
SELECT
  COUNT(*) FILTER (WHERE ae.id IS NOT NULL) as enriched,
  COUNT(*) FILTER (WHERE ae.id IS NULL) as remaining
FROM articles a
LEFT JOIN article_enrichment ae ON a.id = ae.article_id;

-- Phase 2: Topic count
SELECT COUNT(*) FROM topics;

-- Top topics by article count
SELECT name, total_articles
FROM topics
ORDER BY total_articles DESC
LIMIT 10;
```

### Find Issues
```sql
-- Orphaned articles (no enrichment)
SELECT title, url FROM articles a
LEFT JOIN article_enrichment ae ON a.id = ae.article_id
WHERE ae.id IS NULL;

-- Topics without relationships
SELECT name FROM topics t
WHERE NOT EXISTS (
  SELECT 1 FROM topic_relationships tr
  WHERE tr.source_topic_id = t.id OR tr.target_topic_id = t.id
);

-- Most-linked articles
SELECT a.title, COUNT(*) as link_count
FROM articles a
JOIN links l ON a.id = l.target_id
GROUP BY a.id, a.title
ORDER BY link_count DESC
LIMIT 10;
```

## Output Files Explained

### sidebar_structure.json
Hierarchical category tree with article assignments
- Used for building navigation UI
- Shows intended organization
- Format: Nested JSON with categories, subcategories, and articles

### ia_issues.json
List of detected problems with severity levels
- `orphaned_articles`: Articles without topics
- `isolated_topics`: Topics without relationships
- `overloaded_topics`: Topics with too many articles
- `shallow_topics`: Topics needing more depth
- Each issue includes severity: "critical", "warning", or "info"

### ia_review_report.md
Human-readable summary
- Sidebar preview
- Issue breakdown
- Statistics
- Optional LLM critique (if --llm-critique used)

## Tips

1. **Start Small**: Use `--limit 100` for Phase 1 to test before full run
2. **Monitor Progress**: Run `python -m app.pipeline status` frequently
3. **Batch Processing**: Enrich in chunks if you have many articles
4. **Authentication**: Re-copy cURL if scraping fails (sessions expire)
5. **Crawl Depth**: Start with depth 1-2; deeper takes much longer
6. **LLM Critique**: Only use `--llm-critique` for final analysis (slow)
7. **Review Issues**: Check `ia_issues.json` to prioritize fixes

## Next Steps

After running the pipeline:

1. Review `outputs/ia_review_report.md`
2. Identify critical issues from `ia_issues.json`
3. Adjust category structure in code if needed
4. Re-run Phase 3 to regenerate sidebar
5. Export `sidebar_structure.json` for your application

## Getting Help

- Check `README.md` for full documentation
- Review example outputs in `outputs/`
- Check pipeline logs for errors
- Verify config/config.py settings

## File Structure

```
.
├── app/
│   ├── pipeline.py          # Main pipeline orchestrator (all phases)
│   └── curl.txt             # Auth credentials (Phase 0)
├── config/
│   └── config.py            # Configuration
├── outputs/                 # Generated files
│   ├── sidebar_structure.json
│   ├── ia_issues.json
│   └── ia_review_report.md
├── analysis/                # Analysis modules
├── ingestion/scraper/       # Scraping modules
├── persistence/             # Database layers
└── llm/                     # Ollama client
```

## Performance Notes

**Phase 0 (Scraping):**
- ~1-2 seconds per article (with 1 second delay)
- 100 articles ≈ 2-3 minutes
- 1000 articles ≈ 20-30 minutes

**Phase 1 (Enrichment):**
- ~2-5 seconds per article (llama3.1:8b)
- 100 articles ≈ 5-10 minutes
- 1000 articles ≈ 1-2 hours

**Phase 2 (Topic Graph):**
- ~10-30 seconds for 1000 articles
- Depends on number of unique topics

**Phase 3 (IA Analysis):**
- ~5-10 seconds without LLM critique
- ~1-2 minutes with `--llm-critique`

## Quick Reference Card

```bash
# Initial Setup (once)
createdb kb_graph
ollama serve
ollama pull llama3.1:8b

# Configure (edit these files)
config/config.py         # Settings
config/curl.txt          # Authentication

# Run Pipeline
python -m app.pipeline phase0        # Scrape
python -m app.pipeline phase1        # Enrich
python -m app.pipeline phase2        # Topics
python -m app.pipeline phase3        # Analyze

# Check Progress
python -m app.pipeline status

# View Results
cat outputs/ia_review_report.md
```
