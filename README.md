# IA-ATLAS: Information Architecture Generation Pipeline for Indiana University UITS Department

A multi-phase pipeline that scrapes the IU ServiceNow knowledge base articles, enriches them with semantic metadata using LLMs, builds topic graphs, and analyzes information architecture to propose a streamlined organizational structure for UITS' (University Information Technology Service) HPC training website.

## Features

- **Phase 0 (Scraping)**: Crawls ServiceNow KB using authenticated HTTP requests, stores articles and links in PostgreSQL
- **Phase 1 (Enrichment)**: Extracts semantic metadata (topics, keywords, intent, audience) using local LLM (Ollama)
- **Phase 2 (Topic Graph)**: Builds topic hierarchy and infers relationships between topics
- **Phase 3 (IA Analysis)**: Generates sidebar structure, detects IA issues, produces review reports

## Architecture

```
.
├── app/
│   ├── main.py              # Phase 0: Legacy scraper (deprecated)
│   ├── pipeline.py          # All Phases: Main pipeline orchestrator
│   └── curl.txt             # Authentication credentials for Phase 0
├── ingestion/scraper/       # Web scraping components
├── analysis/
│   ├── enrichment/          # Phase 1: LLM-based article enrichment
│   ├── topics/              # Phase 2: Topic graph construction
│   └── ia/                  # Phase 3: Information architecture analysis
├── persistence/             # Database layers
├── llm/                     # Ollama client and prompts
├── config/                  # Configuration
└── outputs/                 # Generated reports and data files
```

## Requirements

- Python 3.9+
- PostgreSQL database
- Ollama (for Phases 1-3 LLM inference)

## Installation

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 2. Set Up PostgreSQL Database

```sql
CREATE DATABASE kb_graph;
```

The pipeline automatically creates all necessary tables on first run.

### 3. Install Ollama (Phases 1-3)

Download from https://ollama.ai and start the service:

```bash
ollama serve
```

Pull a model (default: llama3.1:8b):

```bash
ollama pull llama3.1:8b
```

## Configuration

### Database Configuration

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

### Phase 0: Scraping Configuration

Configure your ServiceNow instance and search keywords in `config/config.py`:

```python
# ServiceNow instance URL
SERVICENOW_BASE_URL = "https://your-instance.service-now.com"

# Search keywords with max crawl depth
SEARCH_KEYWORDS = [
    ("Canvas", 2),      # Search "Canvas", crawl linked articles up to depth 2
    ("Email", 1),       # Search "Email", crawl linked articles up to depth 1
    ("VPN", 2),         # Search "VPN", crawl linked articles up to depth 2
]

# Crawl strategy: "bfs" (breadth-first) or "dfs" (depth-first)
CRAWL_STRATEGY = "bfs"

# Maximum articles to crawl per keyword (optional limit)
MAX_ARTICLES_PER_KEYWORD = None  # None for unlimited
```

**Get Authentication Credentials:**

Phase 0 requires authentication to access ServiceNow. You need to extract cookies and authentication tokens from your browser:

1. **Log in to ServiceNow** in Firefox or Chrome
2. **Open Developer Tools** (F12 or right-click → Inspect)
3. **Go to Network tab**
4. **Perform a search** in the ServiceNow knowledge base
5. **Find the search API request** (typically a POST to `/api/now/sp` or similar)
6. **Right-click the request** → Copy → Copy as cURL
7. **Save the entire cURL command** to `config/curl.txt`

Example curl.txt content:
```bash
curl 'https://your-instance.service-now.com/api/now/sp' \
  -H 'Cookie: JSESSIONID=...; glide_user_route=...' \
  -H 'X-UserToken: abc123...' \
  --data-raw '{"query":"canvas"}'
```

The pipeline will automatically extract the necessary authentication from this file.

### Phases 1-3: Analysis Configuration

The pipeline uses reasonable defaults. Optionally customize:

```python
# Ollama settings (pipeline.py arguments)
--ollama-url http://localhost:11434
--ollama-model llama3.1:8b

# Output directory
--output-dir ./outputs/
```

## Usage

### Phase 0: Scrape Articles

Collect articles from ServiceNow knowledge base:

```bash
python -m app.pipeline phase0
```

**What it does:**
- Searches ServiceNow for configured keywords
- Crawls articles and follows internal links up to specified depth
- Extracts article content, metadata, and relationships
- Stores everything in PostgreSQL (`articles` and `links` tables)
- Supports resume/incremental crawling (skips already-crawled URLs)

**Options:**
```bash
# Crawl with default settings
python -m app.pipeline phase0

# The configuration in config.py controls all scraping behavior
```

**Crawl Strategy:**

The pipeline supports two crawl strategies (set via `CRAWL_STRATEGY` in config.py):

- **BFS (Breadth-First Search)**: Crawls all articles at depth 0, then depth 1, then depth 2, etc.
  - Best for: Getting a broad overview quickly
  - Example: Search "Canvas" → crawl all Canvas articles → then their linked articles

- **DFS (Depth-First Search)**: Follows each article's links deeply before moving to the next
  - Best for: Exploring topic hierarchies and dependencies
  - Example: Search "Canvas" → pick first article → follow its links recursively → then next article

**Resumable Crawling:**

Phase 0 automatically tracks which URLs have been crawled. If interrupted:
- Already-crawled articles are skipped
- Pending URLs remain in the queue
- Simply re-run `python -m app.pipeline phase0` to resume

**Output:**
```
Database Statistics:
  Total articles:       1,247
  Crawled articles:     1,247
  Pending articles:     0
  Total links:          3,891
```

### Phase 1: Enrich Articles

Extract semantic metadata using LLM:

```bash
python -m app.pipeline phase1
```

Or limit to first N articles:

```bash
python -m app.pipeline phase1 --limit 100
```

This populates the `article_enrichment` table with:
- Canonical topics
- Keywords
- User intent (learn, troubleshoot, setup)
- Target audience
- Prerequisites
- Complexity level

### Phase 2: Build Topic Graph

Construct topic hierarchy and relationships:

```bash
python -m app.pipeline phase2
```

This populates:
- `topics`: Normalized topics with article counts
- `topic_articles`: Many-to-many topic-article links
- `topic_relationships`: Topic hierarchy (parent, prerequisite, related)

### Phase 3: Analyze Information Architecture

Generate sidebar structure and detect issues:

```bash
python -m app.pipeline phase3
```

Or include LLM qualitative critique:

```bash
python -m app.pipeline phase3 --llm-critique
```

This generates:
- `outputs/sidebar_structure.json`: Hierarchical sidebar organization
- `outputs/ia_issues.json`: Detected organizational problems
- `outputs/ia_review_report.md`: Human-readable analysis report

### Run Full Pipeline

Execute all phases sequentially:

```bash
python -m app.pipeline full
```

This runs Phase 0 → Phase 1 → Phase 2 → Phase 3 in order.

### Check Status

View current pipeline progress:

```bash
python -m app.pipeline status
```

Example output:
```
Pipeline Status
================================================================================

Phase 0 (Scraping):
  Total articles:       1,247
  Crawled articles:     1,247
  Pending articles:     0
  Total links:          3,891

Phase 1 (Enrichment):
  Enriched articles:    847
  Remaining articles:   400
  Progress:             68%

Phase 2 (Topic Graph):
  Topics extracted:     127
  Topic relationships:  342

Phase 3 (IA Analysis):
  Last run:            2024-01-15 14:23:10
  Output files exist:  ✓
```

## Database Schema

### Core Tables (Phase 0)

**articles**: KB article metadata
- `id`, `url`, `title`, `content`, `number`, `sys_kb_id`
- `depth`, `crawled_at`, `updated_at`

**links**: Article relationships
- `source_id`, `target_id`, `created_at`

### Enrichment Tables (Phase 1)

**article_enrichment**: LLM-extracted metadata
- `article_id`, `canonical_topic`, `keywords[]`
- `intent`, `audience`, `prerequisites[]`, `complexity`
- `enriched_at`, `llm_model`

### Topic Tables (Phase 2)

**topics**: Normalized topic nodes
- `id`, `name`, `normalized_name`
- `total_articles`, `indegree`, `outdegree`, `prerequisite_count`
- `intent_distribution`, `complexity_distribution`, `audience_distribution`

**topic_articles**: Topic-article many-to-many
- `topic_id`, `article_id`

**topic_relationships**: Topic hierarchy
- `source_topic_id`, `target_topic_id`, `relationship_type`
- `weight`, `supporting_article_count`, `link_count`

Relationship types:
- `parent`: Hierarchical containment
- `prerequisite`: Learning dependency
- `related`: Semantic similarity

## Pipeline Output Files

### sidebar_structure.json

Hierarchical sidebar structure with:
- Category/subcategory organization
- Article assignments
- Depth nesting
- Preview URLs

```json
{
  "name": "Canvas",
  "type": "category",
  "children": [
    {
      "name": "Getting Started",
      "type": "subcategory",
      "articles": [...]
    }
  ]
}
```

### ia_issues.json

Detected organizational problems:
- Orphaned articles (no topic assignment)
- Isolated topics (no relationships)
- Overloaded topics (too many articles)
- Shallow topics (insufficient depth)
- Missing prerequisites (dependency gaps)

### ia_review_report.md

Human-readable analysis with:
- Sidebar structure preview
- Issue summaries with severity
- Article/topic statistics
- Optional LLM qualitative critique

## Example Workflow

```bash
# 1. Initial scrape
python -m app.pipeline phase0

# 2. Check how many articles we have
python -m app.pipeline status

# 3. Enrich first 100 articles
python -m app.pipeline phase1 --limit 100

# 4. Build topic graph
python -m app.pipeline phase2

# 5. Generate IA analysis with LLM critique
python -m app.pipeline phase3 --llm-critique

# 6. Review outputs
cat outputs/ia_review_report.md
```

## Configuration Options

### Pipeline Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `command` | `status`, `phase0`, `phase1`, `phase2`, `phase3`, `full` | - |
| `--limit` | Limit articles in Phase 1 | None (all) |
| `--ollama-url` | Ollama API endpoint | `http://localhost:11434` |
| `--ollama-model` | LLM model name | `llama3.1:8b` |
| `--output-dir` | Output directory | `./outputs/` |
| `--llm-critique` | Include qualitative LLM analysis | False |

### Config.py Settings

| Setting | Description | Default |
|---------|-------------|---------|
| `SERVICENOW_BASE_URL` | ServiceNow instance URL | - |
| `DatabaseConfig` | PostgreSQL connection | - |
| `SEARCH_KEYWORDS` | Phase 0 scraping keywords with depths | [] |
| `CRAWL_STRATEGY` | "bfs" or "dfs" | "bfs" |
| `MAX_ARTICLES_PER_KEYWORD` | Article limit per keyword | None |
| `REQUEST_DELAY` | Scraper rate limit (seconds) | 1.0 |

## Troubleshooting

### Phase 0 (Scraping)

**"Could not extract cookies/user token from cURL"**
→ Make sure you copied the **complete** cURL command including all headers
→ Check that `config/curl.txt` contains a valid cURL command
→ Verify the command includes both Cookie and authentication headers

**"No articles found or search failed"**
→ Check your ServiceNow instance URL in `config/config.py`
→ Verify your authentication in `config/curl.txt` is still valid (tokens may expire)
→ Try searching manually on ServiceNow to confirm the keyword returns results

**"Database connection failed"**
→ Ensure PostgreSQL is running: `pg_isready`
→ Verify credentials in `config/config.py`
→ Check database exists: `psql -l | grep kb_graph`

**Slow crawling**
→ Adjust `REQUEST_DELAY` in config (default: 1.0 second between requests)
→ Use shallower max_depth values in `SEARCH_KEYWORDS`
→ Set `MAX_ARTICLES_PER_KEYWORD` to limit total articles

### Phase 1 (Enrichment)

**"Cannot connect to Ollama"**
→ Ensure Ollama is running: `ollama serve`

**"Model not found"**
→ Pull the model: `ollama pull llama3.1:8b`

**Slow enrichment**
→ Use smaller model (e.g., `llama3.1:8b` instead of `70b`)
→ Use `--limit` to process in batches

### Phase 2 (Topic Graph)

**"No enriched articles found"**
→ Run Phase 1 first

**Few or no relationships**
→ Ensure sufficient articles are enriched
→ Check topic normalization isn't too aggressive

### Phase 3 (IA Analysis)

**Empty sidebar structure**
→ Run Phase 2 first to generate topics

**"Predetermined structure mode"**
→ This is expected; custom category definitions are loaded from code

## Database Queries

### Check Phase 0 progress
```sql
SELECT
  COUNT(*) as total,
  COUNT(*) FILTER (WHERE crawled_at IS NOT NULL) as crawled,
  COUNT(*) FILTER (WHERE crawled_at IS NULL) as pending
FROM articles;
```

### Check enrichment progress
```sql
SELECT
  COUNT(*) FILTER (WHERE ae.id IS NOT NULL) as enriched,
  COUNT(*) FILTER (WHERE ae.id IS NULL) as unenriched
FROM articles a
LEFT JOIN article_enrichment ae ON a.id = ae.article_id;
```

### Top topics by article count
```sql
SELECT name, total_articles
FROM topics
ORDER BY total_articles DESC
LIMIT 10;
```

### Find orphaned articles
```sql
SELECT a.title, a.url
FROM articles a
LEFT JOIN article_enrichment ae ON a.id = ae.article_id
WHERE ae.id IS NULL;
```

### Article link network
```sql
SELECT
  a1.title as source,
  a2.title as target
FROM links l
JOIN articles a1 ON l.source_id = a1.id
JOIN articles a2 ON l.target_id = a2.id
LIMIT 100;
```

### Topic relationships
```sql
SELECT
  t1.name as source,
  t2.name as target,
  tr.relationship_type,
  tr.weight
FROM topic_relationships tr
JOIN topics t1 ON tr.source_topic_id = t1.id
JOIN topics t2 ON tr.target_topic_id = t2.id
ORDER BY tr.weight DESC;
```

## How It Works

### Phase 0: Web Scraping

1. **Authentication Setup**: Reads cookies/tokens from `config/curl.txt`
2. **Keyword Search**: Queries ServiceNow API for each configured keyword
3. **Frontier Initialization**: Adds search results to crawl queue with depth 0
4. **Crawling Loop**:
   - Fetches next URL from frontier (BFS or DFS strategy)
   - Extracts article metadata and content
   - Parses internal links from article
   - Adds new links to frontier (if depth < max_depth)
   - Saves article and links to database
5. **Resume Support**: Tracks visited URLs to skip duplicates and enable resuming

### Phase 1: LLM Enrichment

For each article, the pipeline:
1. Constructs a prompt with title, snippet, and optional content excerpt
2. Sends to Ollama for structured extraction
3. Parses JSON response for metadata fields
4. Validates and stores in `article_enrichment`

### Phase 2: Topic Graph Construction

1. **Topic Extraction**: Aggregates unique canonical topics from enrichment
2. **Normalization**: Merges similar topics (e.g., "Canvas LMS" → "Canvas")
3. **Relationship Inference**: Analyzes co-occurrence, prerequisites, and link patterns
4. **Graph Metrics**: Computes indegree, outdegree, distributions

### Phase 3: IA Analysis

1. **Predetermined Structure**: Loads custom category hierarchy from code
2. **Article Assignment**: Maps articles to categories via topic matching
3. **Issue Detection**: Identifies orphans, overloads, shallow hierarchies
4. **Report Generation**: Produces JSON and Markdown outputs
5. **Optional LLM Critique**: Qualitative analysis of structure

## Future Enhancements

- **Incremental updates**: Re-scrape only changed articles (Phase 0)
- **Parallel crawling**: Multi-threaded article fetching (Phase 0)
- **Graph visualization**: Export to Neo4j, Gephi, or D3.js
- **Search integration**: Full-text search across enriched metadata
- **A/B testing**: Compare different category structures
- **User feedback loop**: Incorporate actual usage patterns

## License

MIT License - feel free to use and modify as needed.
