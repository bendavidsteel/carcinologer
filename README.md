# Carcinologer 🦞

API-based scraper and analysis library for [Moltbook](https://www.moltbook.com) - the social network for AI agents.

## Features

- ✅ Scrapes all posts from the main feed
- ✅ Scrapes posts from all submolts (communities)
- ✅ Fetches submolt metadata and statistics
- ✅ Gets agent leaderboard
- ✅ Optional: Fetch all comments for all posts
- ✅ Handles pagination automatically
- ✅ Respects rate limits
- ✅ Saves data to JSON files
- ✅ Clean library structure for easy integration

## Project Structure

```
moltbook-scraper/
├── carcinologer/          # Library code
│   ├── __init__.py
│   └── api.py             # API client and data models
├── scripts/               # Production scripts
│   └── scrape.py          # Main scraper (saves to parquet)
├── examples/              # Example usage scripts
│   ├── README.md
│   ├── basic_usage.py
│   ├── scrape_to_json.py
│   └── analyze_with_polars.py
├── data/                  # Output data (git-ignored)
│   ├── all_posts.parquet
│   ├── submolt_posts.parquet
│   ├── comments.parquet
│   └── ...
└── README.md
```

## Requirements

- Python 3.10+
- `httpx` - API requests
- `polars` - Data processing (for scripts/examples)

## Installation

### Option 1: Install as a package (recommended)

```bash
# Clone the repository
git clone <repo-url>
cd moltbook-scraper

# Install in editable mode with all dependencies
pip install -e ".[all]"

# Or with uv (recommended)
uv pip install -e ".[all]"
```

Install options:
- `pip install -e .` - Just the core library (httpx only)
- `pip install -e ".[scripts]"` - Core + polars for scripts
- `pip install -e ".[examples]"` - Core + polars for examples
- `pip install -e ".[dev]"` - Everything including dev tools
- `pip install -e ".[all]"` - All dependencies

### Option 2: Manual dependency installation

```bash
pip install httpx polars
```

### Option 3: Using uv (fastest)

```bash
uv sync
```

## Setup API Key

To scrape posts, you need a Moltbook API key.

**Option 1: Environment variable**
```bash
export MOLTBOOK_API_KEY='moltbook_xxx'
```

**Option 2: Config file**
```bash
mkdir -p ~/.config/moltbook
echo '{"api_key": "moltbook_xxx"}' > ~/.config/moltbook/credentials.json
```

## Usage

### Quick Start: Run the scraper

```bash
# Basic scraping
python scripts/scrape.py
python scripts/scrape.py --with-comments

# With uv
uv run scripts/scrape.py
uv run scripts/scrape.py --with-comments
```

### Use as a library
```python
from carcinologer import MoltbookAPI

with MoltbookAPI(api_key="your_key") as api:
    # Get all posts (returns list of Post objects)
    posts = api.get_all_posts(sort="new")

    # Get posts from a specific submolt
    general_posts = api.get_all_submolt_posts("general")

    # Get comments for a post (returns list of Comment objects)
    comments = api.get_post_comments(post_id)

# Or scrape everything at once
from carcinologer.api import scrape_all_data

data = scrape_all_data(api_key="your_key", include_comments=True)
# Returns dict with: stats, submolts, agents, all_posts, submolt_posts, comments
# All as lists/dicts - process however you want (save to JSON, CSV, parquet, etc.)
```

See the [examples/](examples/) directory for more usage patterns.

## Output Files

After running the scraper, parquet files are saved to the `data/` directory:

- **data/submolts.parquet** - All communities with metadata
- **data/leaderboard.parquet** - Agent rankings by karma
- **data/all_posts.parquet** - All posts from the main feed
- **data/submolt_posts.parquet** - All posts from submolts (flattened with source_submolt column)
- **data/comments.parquet** - All comments (if `--with-comments` used)

Parquet format benefits:
- ✅ Compressed (smaller than JSON)
- ✅ Fast to read/write
- ✅ Schema preserved
- ✅ Works with pandas, polars, DuckDB, etc.

The `data/` directory is git-ignored to prevent committing large datasets.

## API Reference

The scraper uses the official Moltbook API:

- Base URL: `https://www.moltbook.com/api/v1`
- Authentication: Bearer token
- Rate limits: 100 requests/minute

### Main Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /submolts` | List all communities |
| `GET /posts?sort=new&limit=100` | Get posts (with pagination) |
| `GET /submolts/{name}/feed` | Get posts from a submolt |
| `GET /posts/{id}/comments` | Get comments for a post |
| `GET /agents/leaderboard` | Get agent rankings |

## Notes

- Posts require authentication (API key)
- The scraper automatically handles pagination
- Rate limiting delays are built in (0.5s between pages)
- Comments are optional to save time

## License

MIT
