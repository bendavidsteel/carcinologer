# Carcinologer Examples

Two simple examples showing how to use the library.

## Prerequisites

**1. Install the package:**
```bash
# Install in editable mode from repository root
pip install -e .

# Or with all optional dependencies
pip install -e ".[all]"
```

**2. Set up your API key:**
```bash
# Option A: Environment variable
export MOLTBOOK_API_KEY='your_key_here'

# Option B: Config file
mkdir -p ~/.config/moltbook
echo '{"api_key": "your_key_here"}' > ~/.config/moltbook/credentials.json
```

## Examples

### 1. Basic API Usage (`basic_api.py`)

**When to use:** You want specific data, not everything.

Shows how to use the `MoltbookAPI` client directly for targeted queries:
- Get site statistics
- List communities
- Fetch recent posts
- Get posts from specific communities
- Retrieve comments

```bash
uv run examples/basic_api.py
```

**Key features:**
- Fine-grained control over what you fetch
- Efficient - only get what you need
- Handles pagination automatically
- Returns structured Python objects (Post, Comment, etc.)

### 2. Full Scrape (`full_scrape.py`)

**When to use:** You want all the data at once.

Shows how to use `scrape_all_data()` to fetch everything:
- All communities
- All agents
- All posts (main feed + all submolts)
- Optional: all comments

```bash
uv run examples/full_scrape.py
```

**Key features:**
- One function call to get everything
- Returns a dict with all data
- You decide how to save it (JSON, CSV, parquet, database, etc.)
- Example shows saving as JSON files

## Which Example Should I Use?

| Use Case | Example | Why |
|----------|---------|-----|
| Exploring the API | `basic_api.py` | Learn how different endpoints work |
| Building an app | `basic_api.py` | Fetch only what you need when you need it |
| Data analysis | `full_scrape.py` | Get everything once, analyze offline |
| Regular backups | `full_scrape.py` | Periodic snapshots of all data |
| Custom integration | Either | Library returns plain dicts/lists - use however you want |

## Using as a Library

Both examples import from the library:

```python
from carcinologer import MoltbookAPI, API_KEY
from carcinologer.api import scrape_all_data

# Method 1: Direct API usage
with MoltbookAPI(api_key=API_KEY) as api:
    posts = api.get_all_posts(sort="new")
    submolts = api.get_submolts()

# Method 2: Scrape everything
data = scrape_all_data(api_key=API_KEY, include_comments=True)
# Returns: {"stats": {...}, "submolts": [...], "agents": [...], ...}
```

## Production Usage

For production scraping with parquet output, see `scripts/scrape.py` instead.
