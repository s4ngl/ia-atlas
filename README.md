# ServiceNow Knowledge Base Graph Scraper

A web scraper that crawls ServiceNow knowledge base articles and builds a graph database of article relationships. This version uses Selenium for dynamic content rendering and supports multiple keywords with configurable depth limits.

## Features

- **Dynamic Content Scraping**: Uses Selenium WebDriver to capture Angular-rendered content
- **Multi-keyword Search**: Configure multiple keywords with individual depth constraints
- **Depth-limited Crawling**: Control how deep the crawler follows links from each keyword
- **Graph Database Storage**: Stores articles and their relationships in PostgreSQL
- **BFS/DFS Strategies**: Choose between breadth-first or depth-first crawling
- **Rate Limiting**: Respectful crawling with configurable delays

## Requirements

- Python 3.9+
- PostgreSQL database
- Firefox browser
- geckodriver (Selenium WebDriver for Firefox)

## Installation

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 2. Install Firefox and geckodriver

**On macOS:**
```bash
brew install firefox
brew install geckodriver
```

**On Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install firefox
sudo apt-get install firefox-geckodriver
```

**On Windows:**
- Download Firefox from https://www.mozilla.org/firefox/
- Download geckodriver from https://github.com/mozilla/geckodriver/releases
- Add geckodriver to your system PATH

### 3. Set Up PostgreSQL Database

Create a database for the scraper:

```sql
CREATE DATABASE kb_graph;
```

The scraper will automatically create the necessary tables on first run.

## Configuration

### 1. Edit `config.py`

Update the database configuration:

```python
DatabaseConfig = {
    'dbname': 'kb_graph',
    'user': 'your_username',
    'password': 'your_password',
    'host': 'localhost',
    'port': 5432
}
```

### 2. Configure Keywords and Depth

Add your search keywords with depth limits to `config.py`:

```python
SEARCH_KEYWORDS = [
    ("canvas", 2),      # Search "canvas", crawl up to depth 2
    ("email", 1),       # Search "email", crawl up to depth 1
    ("vpn", 2),         # Search "vpn", crawl up to depth 2
    ("duo", 1),         # Search "duo", crawl up to depth 1
]
```

**Depth Explanation:**
- **Depth 0**: Only crawl articles from the initial search results
- **Depth 1**: Crawl search results + articles they link to
- **Depth 2**: Crawl search results + 1st level links + 2nd level links
- **Depth N**: Continue following links up to N levels deep

### 3. Get Authentication Credentials

1. Log in to your ServiceNow instance in Firefox
2. Navigate to the knowledge base search page
3. Open Firefox Developer Tools (F12)
4. Go to the Network tab
5. Perform a search
6. Find a POST request to the search API
7. Right-click the request → Copy → Copy as cURL
8. Paste the entire cURL command into a file named `curl.txt` in the same directory as the scripts

Example `curl.txt` structure (your actual command will be much longer):
```
curl 'https://servicenow.iu.edu/api/now/sp/rectangle/...' \
  -H 'Cookie: JSESSIONID=...; glide_user_route=...' \
  -H 'X-UserToken: abc123...' \
  --data-raw '...'
```

## Usage

Once configuration is complete, simply run:

```bash
python main.py
```

The scraper will:
1. Read credentials from `curl.txt`
2. Load keywords from `config.py`
3. For each keyword:
   - Perform a search
   - Crawl results up to the specified depth
   - Extract links from dynamically loaded content
   - Store articles and relationships in the database
4. Display progress and statistics

### Example Output

```
================================================================================
  ServiceNow Knowledge Base Graph Scraper
================================================================================

Reading curl.txt for authentication credentials...
✓ Successfully parsed authentication credentials

Loaded 4 keyword(s) from config.py:
  • 'canvas' (max depth: 2)
  • 'email' (max depth: 1)
  • 'vpn' (max depth: 2)
  • 'duo' (max depth: 1)

Initializing components...
✓ Selenium WebDriver initialized
✓ Database connected successfully
✓ All components initialized

================================================================================
Starting crawl for keyword: 'canvas' (max depth: 2)
================================================================================

Searching for: 'canvas'
--------------------------------------------------------------------------------
✓ Found 45 articles
Added 45 articles to crawl queue

Starting crawl...
--------------------------------------------------------------------------------

[1] Crawling article...
  Fetching: https://servicenow.iu.edu/kb?id=kb_article_view&sysparm_article=KB0012345
  Depth: 0
  ✓ Saved article (ID: 1)
    Title: Getting Started with Canvas
    Links found: 8
  ✓ Added 8 new articles to queue (depth 1)
  Progress: 1 visited, 52 pending

...
```

## Database Schema

### Articles Table

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| url | TEXT | Article URL (unique) |
| title | TEXT | Article title |
| content | TEXT | Article content |
| number | TEXT | Article number |
| display_number | TEXT | Display number |
| snippet | TEXT | Search snippet |
| score | REAL | Search relevance score |
| can_read | TEXT | Read permission |
| depth | INTEGER | Crawl depth from search |
| crawled_at | TIMESTAMP | First crawl time |
| updated_at | TIMESTAMP | Last update time |

### Links Table

| Column | Type | Description |
|--------|------|-------------|
| source_id | INTEGER | Source article ID |
| target_id | INTEGER | Target article ID |
| created_at | TIMESTAMP | Link creation time |

## Configuration Options

### `config.py` Settings

| Setting | Description | Default |
|---------|-------------|---------|
| `SERVICENOW_BASE_URL` | Your ServiceNow instance URL | - |
| `DatabaseConfig` | PostgreSQL connection settings | - |
| `REQUEST_DELAY` | Seconds between requests | 1.0 |
| `REQUEST_TIMEOUT` | Request timeout in seconds | 30 |
| `SELENIUM_HEADLESS` | Run browser in headless mode | True |
| `SELENIUM_PAGE_LOAD_TIMEOUT` | Page load timeout | 30 |
| `SELENIUM_WAIT_TIMEOUT` | Element wait timeout | 10 |
| `SEARCH_KEYWORDS` | List of (keyword, max_depth) tuples | [] |
| `MAX_ARTICLES_PER_KEYWORD` | Safety limit per keyword | 1000 |
| `CRAWL_STRATEGY` | "bfs" or "dfs" | "bfs" |

## Troubleshooting

### Selenium Issues

**Error: "geckodriver not found"**
- Make sure geckodriver is installed and in your PATH
- Try running `geckodriver --version` to verify

**Error: "Firefox binary not found"**
- Ensure Firefox is installed
- On Linux, you may need to specify the Firefox binary path in `fetcher.py`

### Database Issues

**Error: "Database connection failed"**
- Verify PostgreSQL is running
- Check your database credentials in `config.py`
- Ensure the database exists: `createdb kb_graph`

### Authentication Issues

**Error: "Could not extract cookies"**
- Make sure you copied the complete cURL command
- The command should include `-H 'Cookie: ...'` and `-H 'X-UserToken: ...'`
- Try copying the cURL command again from a fresh browser session

### No Links Found

If the scraper is not finding any links:
- Check that Selenium is properly initialized
- Verify the page is fully loading (increase `SELENIUM_WAIT_TIMEOUT`)
- Check the browser console for JavaScript errors
- Try disabling headless mode temporarily (`SELENIUM_HEADLESS = False`)

## How It Works

### 1. Dynamic Content Rendering

The original scraper used `requests` to fetch HTML, but ServiceNow uses Angular to dynamically load article links. The updated scraper uses Selenium WebDriver to:
- Load the full page in a real browser
- Wait for Angular to render the content
- Extract the fully rendered HTML with all dynamic elements

### 2. Depth-Limited Crawling

Each URL is assigned a depth level:
- Search results start at depth 0
- Articles linked from depth 0 are at depth 1
- Articles linked from depth 1 are at depth 2
- And so on...

The crawler stops following links when it reaches `max_depth` for each keyword, preventing unbounded crawling.

### 3. Graph Storage

Articles and their relationships are stored in PostgreSQL:
- Each article is a node with metadata
- Each link is an edge between two articles
- This enables graph queries like "find all articles reachable from X"

## Future Enhancements

Possible improvements:
- Resume interrupted crawls
- Parallel crawling with multiple workers
- Export graph to visualization tools (Gephi, Neo4j)
- Full-text search on article content
- Incremental updates (re-crawl only changed articles)

## License

MIT License - feel free to use and modify as needed.
