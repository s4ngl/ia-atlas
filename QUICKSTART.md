# Quick Start Guide

## Setup (One-time)

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Install Firefox & geckodriver
**macOS:**
```bash
brew install firefox geckodriver
```

**Ubuntu/Debian:**
```bash
sudo apt-get install firefox firefox-geckodriver
```

### 3. Test Selenium Setup
```bash
python test_selenium.py
```
If this succeeds, you're ready to go!

### 4. Create Database
```sql
CREATE DATABASE kb_graph;
```

### 5. Configure Database
Edit `config.py` and update:
```python
DatabaseConfig = {
    'dbname': 'kb_graph',
    'user': 'your_username',
    'password': 'your_password',
    'host': 'localhost',
    'port': 5432
}
```

## Configuration

### Set Keywords (Required)
Edit `config.py` and set your keywords:
```python
SEARCH_KEYWORDS = [
    ("Slate", 1),
    ("Quartz", 2),
    ("Big Red 200", 2),
]
```

**Depth levels:**
- 0 = Only search results
- 1 = Search results + their links
- 2 = Search results + 2 levels of links
- etc.

### Get Authentication (Required)
1. Open Firefox and go to ServiceNow knowledge base
2. Press F12 (Developer Tools)
3. Go to Network tab
4. Search for something
5. Find the POST request to the search API
6. Right-click → Copy → Copy as cURL
7. Paste entire cURL command into `curl.txt`

## Running

```bash
python main.py
```

That's it! The scraper will:
- Read your auth from `curl.txt`
- Process each keyword from `config.py`
- Use Selenium to capture dynamic content
- Store everything in PostgreSQL

## Key Features

✓ **Dynamic Content**: Uses Selenium to capture Angular-rendered links
✓ **Multi-keyword**: Process multiple keywords in one run
✓ **Depth Control**: Set max depth per keyword
✓ **No User Input**: Everything configured in files
✓ **Graph Storage**: Articles and links in PostgreSQL

## Troubleshooting

**"geckodriver not found"**
→ Install geckodriver and add to PATH

**"Database connection failed"**
→ Check `config.py` DB settings and ensure PostgreSQL is running

**"Could not extract cookies"**
→ Make sure you copied the COMPLETE cURL command including all headers

**No links found**
→ Selenium may need more time to load; increase `SELENIUM_WAIT_TIMEOUT` in config.py

## File Structure

```
├── main.py              # Main entry point
├── fetcher.py           # HTTP + Selenium fetching
├── parser.py            # HTML parsing
├── frontier.py          # URL queue management
├── database.py          # PostgreSQL operations
├── config.py            # Configuration (edit this!)
├── curl.txt             # Auth credentials (edit this!)
├── requirements.txt     # Python dependencies
├── test_selenium.py     # Test Selenium setup
└── README.md            # Full documentation
```

## Configuration Reference

### config.py Options

| Variable | Description | Default |
|----------|-------------|---------|
| `SERVICENOW_BASE_URL` | Your ServiceNow URL | - |
| `DatabaseConfig` | Database connection | - |
| `SEARCH_KEYWORDS` | List of (keyword, depth) | [] |
| `REQUEST_DELAY` | Seconds between requests | 1.0 |
| `SELENIUM_HEADLESS` | Run browser hidden | True |
| `MAX_ARTICLES_PER_KEYWORD` | Safety limit | 1000 |
| `CRAWL_STRATEGY` | "bfs" or "dfs" | "bfs" |

## Example Output

```
================================================================================
  ServiceNow Knowledge Base Graph Scraper
================================================================================

Loaded 3 keyword(s) from config.py:
  • 'canvas' (max depth: 2)
  • 'email' (max depth: 1)
  • 'vpn' (max depth: 2)

Initializing components...
✓ Selenium WebDriver initialized
✓ Database connected successfully

================================================================================
Starting crawl for keyword: 'canvas' (max depth: 2)
================================================================================

✓ Found 45 articles

[1] Crawling article...
  Depth: 0
  ✓ Saved article (ID: 1)
    Title: Getting Started with Canvas
    Links found: 8
  ✓ Added 8 new articles to queue (depth 1)
  Progress: 1 visited, 52 pending

...
```

## Database Schema

**articles** table:
- url, title, content, number, display_number
- snippet, score, can_read, depth
- crawled_at, updated_at

**links** table:
- source_id → target_id (article relationships)

Query examples:
```sql
-- Articles by depth
SELECT depth, COUNT(*) FROM articles GROUP BY depth;

-- Most linked articles
SELECT a.title, COUNT(*) as link_count
FROM links l
JOIN articles a ON l.target_id = a.id
GROUP BY a.id, a.title
ORDER BY link_count DESC
LIMIT 10;

-- Articles from specific keyword/depth
SELECT * FROM articles WHERE depth = 0;  -- Search results
SELECT * FROM articles WHERE depth = 1;  -- 1st level links
```
