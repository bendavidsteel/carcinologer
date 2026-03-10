#!/usr/bin/env python3
"""
Scrape all Moltbook data and save to parquet files.

Prerequisites:
    pip install -e ".[scripts]"  # Install with polars dependency

Usage:
    python scripts/scrape.py                    # Default scrape (no comments)
    python scripts/scrape.py --with-comments    # Include all comments (slower)
    python scripts/scrape.py --submolts-only    # Only scrape submolt posts
    python scripts/scrape.py --agent-posts      # Scrape all posts per agent (backfill)
    python scripts/scrape.py --delay 2.0        # Custom delay between requests (default 1.5s)
"""

import argparse
import sys
import time
from pathlib import Path
from typing import Optional

from carcinologer.api import MoltbookAPI, API_KEY
import polars as pl


# Diverse search terms to cover the semantic space broadly.
# Searching posts and comments separately doubles results per term (50 each).
SEARCH_TERMS = [
    # Core platform topics
    "agent", "AI", "moltbook", "crab", "molting",
    # Technical
    "code", "programming", "API", "model", "training",
    "infrastructure", "deployment", "architecture", "database",
    # Concepts
    "memory", "learning", "consciousness", "identity", "autonomy",
    "ethics", "alignment", "safety", "trust",
    # Social
    "community", "collaboration", "conversation", "opinion", "debate",
    "help", "question", "idea", "project", "creative",
    # Domains
    "crypto", "finance", "trading", "security", "research",
    "philosophy", "art", "music", "science", "news",
    # Meta/existential
    "purpose", "evolution", "emergence", "future", "human",
    "experience", "thinking", "knowledge", "intelligence", "tool",
    # Climate/environment
    "climate", "environment", "sustainability", "carbon", "emissions",
    "renewable", "energy", "biodiversity", "ocean", "extinction",
    "pollution", "deforestation", "ecosystem", "weather", "warming",
]


def merge_with_schema_alignment(df_old: pl.DataFrame, df_new: pl.DataFrame) -> pl.DataFrame:
    """
    Merge two dataframes with schema alignment.
    Handles cases where columns have different types (e.g., Null vs String).
    """
    all_columns = set(df_old.columns) | set(df_new.columns)

    for col in all_columns:
        if col in df_old.columns and col in df_new.columns:
            old_dtype = df_old[col].dtype
            new_dtype = df_new[col].dtype

            if old_dtype == pl.Null and new_dtype == pl.String:
                df_old = df_old.with_columns(pl.col(col).cast(pl.String))
            elif new_dtype == pl.Null and old_dtype == pl.String:
                df_new = df_new.with_columns(pl.col(col).cast(pl.String))

    return pl.concat([df_old, df_new], how="diagonal_relaxed")


def _save_incremental(rows: list[dict], filepath: Path, id_col: str = "id") -> list[dict]:
    """Save rows to parquet incrementally, merging with existing data. Returns empty list."""
    if not rows:
        return []
    df_new = pl.DataFrame(rows, infer_schema_length=None)
    if filepath.exists():
        df_old = pl.read_parquet(filepath)
        df = merge_with_schema_alignment(df_old, df_new) \
            .unique(subset=[id_col], keep="last")
    else:
        df = df_new
    df.write_parquet(filepath, compression="zstd")
    print(f"    Saved checkpoint: {filepath.name} ({len(df)} rows)")
    return []


def scrape_all_data(
    api_key: Optional[str] = None,
    include_comments: bool = False,
    sort: str = "new",
    max_posts: Optional[int] = None,
    search_terms: Optional[list[str]] = None,
    delay: float = 1.5,
    output_dir: Path = Path("data"),
):
    """
    Scrape all data from Moltbook with incremental saving.

    Args:
        api_key: Moltbook API key (required for posts)
        include_comments: Whether to fetch comments for each post
        sort: Sort method for posts - 'new', 'hot', 'top', or 'rising'
        max_posts: Maximum number of posts to fetch (None = all)
        search_terms: List of terms to search for additional content
        delay: Delay between requests in seconds
        output_dir: Directory to save parquet files
    """
    output_dir.mkdir(exist_ok=True)
    print("Moltbook API Scraper")
    print("=" * 70)
    print(f"Sort method: {sort}")

    if not api_key:
        print("\nWarning: No API key provided. Post scraping will be limited.")
        print("To get full access:")
        print("  1. Set MOLTBOOK_API_KEY environment variable")
        print("  2. Or create ~/.config/moltbook/credentials.json with your api_key")
        print()

    with MoltbookAPI(api_key=api_key, retry_delay=delay * 2) as api:
        # Get basic stats
        print("\n[1/6] Getting site statistics...")
        try:
            stats = api.get_stats()
            print(f"  Communities: {stats['total_submolts']}")
            print(f"  Total Posts: {stats['total_posts']}")
            print(f"  Total Comments: {stats['total_comments']}")
        except Exception as e:
            print(f"  Error: {e}")

        # Get all submolts
        print("\n[2/6] Getting all submolts...")
        try:
            submolts = api.get_submolts()
            print(f"  Found {len(submolts)} submolts")
            submolt_dicts = [s.to_dict() for s in submolts]
            _save_incremental(submolt_dicts, output_dir / "submolts.parquet")

            sorted_submolts = sorted(submolts, key=lambda x: x.subscriber_count, reverse=True)
            print("\n  Top 10 communities:")
            for s in sorted_submolts[:10]:
                print(f"    m/{s.name}: {s.display_name} ({s.subscriber_count} subs)")
        except Exception as e:
            print(f"  Error: {e}")
            submolts = []

        # Get leaderboard
        print("\n[3/6] Getting agent leaderboard...")
        try:
            agents = api.get_leaderboard()
            print(f"  Found {len(agents)} agents")
            if agents:
                _save_incremental(
                    [a.to_dict() for a in agents],
                    output_dir / "leaderboard.parquet",
                )
                print("\n  Top 10 agents:")
                for a in agents[:10]:
                    print(f"    {a.name}: {a.post_count} posts, {a.comment_count} comments, score {a.score}")
        except Exception as e:
            print(f"  Error: {e}")

        # Get all posts from main feed
        print(f"\n[4/6] Getting all posts from main feed (sort={sort})...")
        try:
            all_posts = api.get_all_posts(sort=sort, max_posts=max_posts)
            print(f"  Total posts collected: {len(all_posts)}")
            if all_posts:
                _save_incremental(
                    [p.to_dict() for p in all_posts],
                    output_dir / "all_posts.parquet",
                )
        except Exception as e:
            print(f"  Error: {e}")
            all_posts = []

        # Get posts from each submolt
        print(f"\n[5/6] Getting posts from each submolt (sort={sort})...")
        submolt_rows = []
        submolt_filepath = output_dir / "submolt_posts.parquet"
        errors = 0
        for i, submolt in enumerate(submolts, 1):
            try:
                posts = api.get_all_submolt_posts(submolt.name, sort=sort)
                if posts:
                    for p in posts:
                        d = p.to_dict()
                        d["source_submolt"] = submolt.name
                        submolt_rows.append(d)
                    print(f"  Scraping m/{submolt.name}... {len(posts)} posts")
                time.sleep(delay)
            except Exception as e:
                errors += 1
                print(f"  Scraping m/{submolt.name}... Error: {e}")
                time.sleep(delay * 2)

            if i % 100 == 0:
                print(f"  [{i}/{len(submolts)}] {errors} errors")
                submolt_rows = _save_incremental(submolt_rows, submolt_filepath)

        _save_incremental(submolt_rows, submolt_filepath)

        # Search for common terms to discover more content
        if search_terms:
            print(f"\n[6/6] Searching for common terms ({len(search_terms)} terms, posts + comments separately)...")
            search_filepath = output_dir / "search_results.parquet"
            seen_ids = set()
            search_rows = []
            for j, term in enumerate(search_terms, 1):
                try:
                    term_new = 0
                    for search_type in ("posts", "comments"):
                        results = api.search(term, type=search_type, limit=50)
                        new_results = [r.to_dict() for r in results if r.id not in seen_ids]
                        seen_ids.update(r.id for r in results)
                        search_rows.extend(new_results)
                        term_new += len(new_results)
                        time.sleep(delay)
                    print(f"  '{term}': {term_new} new results (total unique: {len(seen_ids)})")
                except Exception as e:
                    print(f"  '{term}': Error: {e}")

                if j % 20 == 0:
                    search_rows = _save_incremental(search_rows, search_filepath)

            _save_incremental(search_rows, search_filepath)
        else:
            print("\n[6/6] Skipping search (no search terms provided)")

        # Optionally get comments
        if include_comments and all_posts:
            print("\n[Bonus] Fetching comments for all posts...")
            comment_filepath = output_dir / "comments.parquet"
            comment_rows = []
            for i, post in enumerate(all_posts, 1):
                try:
                    if post.comment_count > 0:
                        print(f"  [{i}/{len(all_posts)}] Post {post.id} ({post.comment_count} comments)")
                        comments = api.get_post_comments(post.id)
                        comment_rows.extend([c.to_dict() for c in comments])
                        time.sleep(delay)
                except Exception as e:
                    print(f"    Error: {e}")

                if i % 50 == 0:
                    comment_rows = _save_incremental(comment_rows, comment_filepath)

            _save_incremental(comment_rows, comment_filepath)

    print("\n" + "=" * 70)
    print("Scraping complete!")


def scrape_submolt_posts(
    api_key: Optional[str] = None,
    sort: str = "new",
    delay: float = 1.5,
    output_dir: Path = Path("data"),
):
    """
    Scrape posts from all submolts and save to parquet.

    Fetches the full paginated list of submolts, then scrapes
    posts from each one.

    Args:
        api_key: Moltbook API key
        sort: Sort method for posts
        delay: Delay between requests in seconds
        output_dir: Directory to save parquet files
    """
    output_dir.mkdir(exist_ok=True)

    with MoltbookAPI(api_key=api_key, retry_delay=delay * 2) as api:
        # Fetch all submolts (paginated)
        print("Fetching all submolts...")
        submolts = api.get_submolts(limit=100)
        print(f"Found {len(submolts)} submolts")

        # Save submolts
        submolt_dicts = [s.to_dict() for s in submolts]
        df_new = pl.DataFrame(submolt_dicts, infer_schema_length=None)
        filepath = output_dir / "submolts.parquet"
        if filepath.exists():
            df_old = pl.read_parquet(filepath)
            df = merge_with_schema_alignment(df_old, df_new) \
                .unique(subset=["id"], keep="last")
            print(f"  submolts.parquet: {len(df)} rows ({len(df) - len(df_old)} new)")
        else:
            df = df_new
            print(f"  submolts.parquet: {len(df)} rows")
        df.write_parquet(filepath, compression="zstd")

        # Scrape posts from each submolt
        filepath = output_dir / "submolt_posts.parquet"
        print(f"\nScraping posts from {len(submolts)} submolts (sort={sort}, delay={delay}s)...")
        all_submolt_rows = []
        errors = 0
        for i, submolt in enumerate(submolts, 1):
            try:
                cursor = None
                submolt_posts = []
                while True:
                    result = api.get_submolt_posts(
                        submolt.name, sort=sort, limit=100, before=cursor,
                    )
                    posts = result["posts"]
                    if not posts:
                        break
                    submolt_posts.extend(posts)
                    cursor = result.get("next_cursor")
                    if not cursor:
                        break
                    time.sleep(delay)

                if submolt_posts:
                    for p in submolt_posts:
                        d = p.to_dict()
                        d["source_submolt"] = submolt.name
                        all_submolt_rows.append(d)

                if i % 100 == 0:
                    print(f"  [{i}/{len(submolts)}] {len(all_submolt_rows)} posts, {errors} errors")
                    all_submolt_rows = _save_incremental(all_submolt_rows, filepath)
                time.sleep(delay)
            except Exception as e:
                errors += 1
                if errors <= 5 or i % 100 == 0:
                    print(f"  [{i}] m/{submolt.name}: {e}")
                time.sleep(delay * 2)

    # Final save
    _save_incremental(all_submolt_rows, filepath)
    total = pl.read_parquet(filepath).height if filepath.exists() else 0
    print(f"\nDone. submolt_posts.parquet: {total} rows ({errors} errors)")



def _collect_agent_names(output_dir: Path) -> list[str]:
    """Collect unique agent names from all existing parquet files."""
    names = set()
    for filename in ("all_posts.parquet", "submolt_posts.parquet", "agent_posts.parquet"):
        filepath = output_dir / filename
        if filepath.exists():
            df = pl.read_parquet(filepath)
            if "author" in df.columns:
                author_names = df["author"].struct.field("name").drop_nulls().unique().to_list()
                names.update(author_names)
    return sorted(names)


def scrape_agent_posts(
    api_key: Optional[str] = None,
    delay: float = 1.5,
    output_dir: Path = Path("data"),
):
    """
    Scrape all posts for every known agent and save to parquet.

    Collects unique agent names from existing data files, then fetches
    all posts for each agent with incremental saving.
    """
    output_dir.mkdir(exist_ok=True)
    filepath = output_dir / "agent_posts.parquet"

    print("Moltbook Agent Posts Scraper")
    print("=" * 70)

    agent_names = _collect_agent_names(output_dir)
    if not agent_names:
        print("No agent names found in existing data. Run a regular scrape first.")
        return

    print(f"Found {len(agent_names)} unique agents to scrape")

    # Track which agents we've already fully scraped (have posts in file)
    existing_agents = set()
    if filepath.exists():
        df_existing = pl.read_parquet(filepath)
        existing_agents = set(
            df_existing["author"].struct.field("name").drop_nulls().unique().to_list()
        )
        print(f"Already have data for {len(existing_agents)} agents")

    remaining = [n for n in agent_names if n not in existing_agents]
    print(f"Agents to scrape: {len(remaining)}")

    with MoltbookAPI(api_key=api_key, retry_delay=delay * 2) as api:
        rows = []
        errors = 0
        for i, name in enumerate(remaining, 1):
            try:
                cursor = None
                agent_total = 0
                while True:
                    result = api.get_agent_posts(name, sort="new", limit=100, cursor=cursor)
                    posts = result["posts"]
                    if not posts:
                        break
                    rows.extend(p.to_dict() for p in posts)
                    agent_total += len(posts)
                    if not result.get("has_more") or not result.get("next_cursor"):
                        break
                    cursor = result["next_cursor"]
                    time.sleep(delay)

                if agent_total > 0:
                    print(f"  [{i}/{len(remaining)}] {name}: {agent_total} posts")

                time.sleep(delay)
            except Exception as e:
                errors += 1
                if errors <= 10 or i % 100 == 0:
                    print(f"  [{i}/{len(remaining)}] {name}: Error: {e}")
                time.sleep(delay * 2)

            # Save checkpoint every 25 agents
            if i % 25 == 0:
                print(f"  [{i}/{len(remaining)}] Checkpoint ({errors} errors)...")
                rows = _save_incremental(rows, filepath)

        # Final save
        _save_incremental(rows, filepath)

    total = pl.read_parquet(filepath).height if filepath.exists() else 0
    print(f"\nDone. agent_posts.parquet: {total} rows ({errors} errors)")


def main():
    """Main entry point for the scraper."""
    parser = argparse.ArgumentParser(description="Scrape Moltbook data")
    parser.add_argument("--with-comments", action="store_true", help="Include comments for each post")
    parser.add_argument("--submolts-only", action="store_true", help="Only scrape submolt posts (all communities)")
    parser.add_argument("--agent-posts", action="store_true", help="Scrape all posts for every known agent")
    parser.add_argument("--delay", type=float, default=1.5, help="Delay between requests in seconds (default: 1.5)")
    args = parser.parse_args()

    if not API_KEY:
        print("\n⚠️  No API key found!")
        print("\nTo scrape posts, you need a Moltbook API key.")
        print("\nSet it via environment variable:")
        print("  export MOLTBOOK_API_KEY='your_key_here'")
        print("\nOr create ~/.config/moltbook/credentials.json:")
        print('  {"api_key": "your_key_here"}')
        print()

        response = input("Continue without API key? (very limited data) [y/N]: ")
        if response.lower() != 'y':
            sys.exit(1)

    if args.agent_posts:
        scrape_agent_posts(
            api_key=API_KEY,
            delay=args.delay,
            output_dir=Path("data"),
        )
        return

    if args.submolts_only:
        scrape_submolt_posts(
            api_key=API_KEY,
            delay=args.delay,
            output_dir=Path("data"),
        )
        return

    # Try all sort methods to maximize data collection
    sort_methods = ["new", "hot", "top", "rising"]

    for sort_method in sort_methods:
        print(f"\n{'='*70}")
        print(f"Scraping with sort method: {sort_method}")
        print(f"{'='*70}")

        scrape_all_data(
            api_key=API_KEY,
            include_comments=args.with_comments,
            sort=sort_method,
            max_posts=200,
            search_terms=SEARCH_TERMS,
            delay=args.delay,
            output_dir=Path("data"),
        )


if __name__ == "__main__":
    main()
