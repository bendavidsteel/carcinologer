#!/usr/bin/env python3
"""
Example: Full scrape using scrape_all_data().

This approach fetches everything at once and returns it as a dict.
You decide how to save/process it - JSON, CSV, parquet, database, etc.

Prerequisites:
    pip install -e .  # Install carcinologer in editable mode
"""

import sys
import json
from pathlib import Path

from carcinologer.api import scrape_all_data, API_KEY


def save_as_json(data: dict, output_dir: Path = Path("output")):
    """Save scraped data as JSON files."""
    output_dir.mkdir(exist_ok=True)

    print("\n💾 Saving to JSON...")

    # Save stats
    with open(output_dir / "stats.json", "w") as f:
        json.dump(data["stats"], f, indent=2)
    print(f"  ✓ stats.json")

    # Save submolts
    if data["submolts"]:
        with open(output_dir / "submolts.json", "w") as f:
            json.dump(data["submolts"], f, indent=2, default=str)
        print(f"  ✓ submolts.json ({len(data['submolts'])} communities)")

    # Save agents
    if data["agents"]:
        with open(output_dir / "agents.json", "w") as f:
            json.dump(data["agents"], f, indent=2)
        print(f"  ✓ agents.json ({len(data['agents'])} agents)")

    # Save posts
    if data["all_posts"]:
        with open(output_dir / "all_posts.json", "w") as f:
            json.dump(data["all_posts"], f, indent=2, default=str)
        print(f"  ✓ all_posts.json ({len(data['all_posts'])} posts)")

    # Save submolt posts
    if data["submolt_posts"]:
        with open(output_dir / "submolt_posts.json", "w") as f:
            json.dump(data["submolt_posts"], f, indent=2, default=str)

        total_posts = sum(len(posts) for posts in data["submolt_posts"].values())
        print(f"  ✓ submolt_posts.json ({total_posts} posts from {len(data['submolt_posts'])} communities)")

    # Save comments
    if data["comments"]:
        with open(output_dir / "comments.json", "w") as f:
            json.dump(data["comments"], f, indent=2, default=str)

        total_comments = sum(len(comments) for comments in data["comments"].values())
        print(f"  ✓ comments.json ({total_comments} comments)")

    print(f"\n✅ All data saved to {output_dir}/")


def main():
    # Scrape all data
    print("🦞 Scraping all Moltbook data...\n")
    data = scrape_all_data(api_key=API_KEY, include_comments=False)

    # The data dict contains:
    # - data["stats"] - site statistics
    # - data["submolts"] - list of submolt dicts
    # - data["agents"] - list of agent dicts
    # - data["all_posts"] - list of post dicts from main feed
    # - data["submolt_posts"] - dict mapping submolt name -> list of post dicts
    # - data["comments"] - dict mapping post_id -> list of comment dicts

    # Save however you want - here's JSON as an example
    save_as_json(data, output_dir=Path("output"))

    # Or process it directly:
    print("\n📊 Quick Analysis:")
    print(f"  Total submolts: {len(data['submolts'])}")
    print(f"  Total agents: {len(data['agents'])}")

    total_posts = len(data["all_posts"]) + sum(len(p) for p in data["submolt_posts"].values())
    print(f"  Total posts scraped: {total_posts}")

    if data["submolt_posts"]:
        most_active = max(data["submolt_posts"].items(), key=lambda x: len(x[1]))
        print(f"  Most active community: m/{most_active[0]} ({len(most_active[1])} posts)")


if __name__ == "__main__":
    if not API_KEY:
        print("❌ No API key found. Set MOLTBOOK_API_KEY or create ~/.config/moltbook/credentials.json")
        sys.exit(1)

    main()
