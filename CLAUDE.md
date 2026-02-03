# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Carcinologer is a Python library and scraper for Moltbook (moltbook.com), a social network for AI agents. It provides API-based scraping of posts, comments, communities (submolts), agent leaderboards, and semantic search capabilities.

## Commands

```bash
# Run scripts (using local uv environment)
uv run python scripts/scrape.py              # Scrape without comments
uv run python scripts/scrape.py --with-comments  # Full scrape with comments

# Install dependencies
uv sync
uv pip install -e ".[all]"   # All dependencies
uv pip install -e ".[dev]"   # Development (polars, ipython, ruff)
```

## Architecture

**Library Structure:**
- `carcinologer/api.py` - Core API client with `MoltbookAPI` class using context manager pattern
- Data models as dataclasses: `Submolt`, `Post`, `Comment`, `Agent`, `SearchResult`

**API Client Design:**
- Uses `httpx.Client` with retry logic (3 retries, exponential backoff)
- Two-tier fetching: `get_*` methods for single pages, `get_all_*` for full pagination
- Cursor-based pagination using `before` parameter (post ID)
- Built-in rate limiting (0.5s between requests)
- Auth via `MOLTBOOK_API_KEY` env var or `~/.config/moltbook/credentials.json`

**Data Flow:**
- Scripts save to Parquet files in `data/` directory
- `merge_with_schema_alignment()` handles schema mismatches when updating existing files
- Deduplication by ID with `.unique(subset=["id"], keep="last")`

**Output Files:**
- `data/submolts.parquet` - Community metadata
- `data/leaderboard.parquet` - Agent rankings
- `data/all_posts.parquet` - Main feed posts
- `data/submolt_posts.parquet` - Posts by community (includes `source_submolt` column)
- `data/comments.parquet` - All comments (includes `post_id`)

## Key Patterns

- API methods return dataclass instances; use `.to_dict()` for serialization
- 401 errors on missing API key return empty results (graceful degradation)
- `MoltbookBrowser` class provides async browser-based scraping via zendriver for JS-rendered content
