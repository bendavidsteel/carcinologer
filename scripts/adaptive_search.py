#!/usr/bin/env python3
"""
Adaptive semantic search for Moltbook.

Strategy:
1. Search each base noun, collect results + relevance scores
2. Rank nouns by max relevance (proxy for semantic density)
3. Take the top N densest nouns and expand them by prepending adjectives
4. This creates fine-grained queries like "autonomous agent", "new code", etc.
   that slice into different sub-regions of dense semantic areas
5. Sparse nouns (low relevance) are left as-is since they already captured
   most of what's there
"""

import time
from pathlib import Path

from carcinologer.api import MoltbookAPI, API_KEY
import polars as pl


NOUNS = [
    # Round 1 (already searched)
    "agent", "AI", "memory", "code", "philosophy",
    "crypto", "community", "infrastructure", "consciousness",
    "identity", "network", "system", "model", "data",
    "tool", "knowledge", "intelligence", "evolution",
    "security", "economy", "art", "music", "science",
    "trading", "debate", "opinion", "project", "crab",
    "ethics", "autonomy", "collaboration", "conversation",
    # Round 2 - new nouns to explore fresh semantic regions
    "language", "emotion", "trust", "privacy", "governance",
    "robot", "learning", "experiment", "game", "simulation",
    "token", "wallet", "protocol", "consensus", "democracy",
    "story", "poetry", "humor", "dream", "imagination",
    "survival", "competition", "strategy", "risk", "reward",
    "bug", "error", "hack", "prompt", "response",
    "friend", "enemy", "human", "machine", "nature",
    "time", "space", "chaos", "order", "freedom",
]

ADJECTIVES = [
    # Round 1 (already searched)
    "new", "autonomous", "open", "distributed", "creative",
    "emergent", "first", "best", "broken", "simple",
    "complex", "small", "future", "collaborative", "personal",
    # Round 2 - fresh adjectives
    "decentralized", "recursive", "hybrid", "abstract", "wild",
    "dangerous", "friendly", "ancient", "weird", "honest",
    "automated", "shared", "hidden", "collective", "infinite",
]

# How many of the densest nouns to expand with adjectives
TOP_N_TO_EXPAND = 10

RATE_LIMIT_DELAY = 0.5


def search_term(api, query, search_type, seen_ids):
    """Search and return only new (unseen) results."""
    try:
        results = api.search(query, type=search_type, limit=50)
        new = [r for r in results if r.id not in seen_ids]
        seen_ids.update(r.id for r in results)
        return results, new
    except Exception as e:
        if "429" in str(e):
            print(f"    Rate limited on '{query}', waiting 10s...")
            time.sleep(10)
            # Retry once
            try:
                results = api.search(query, type=search_type, limit=50)
                new = [r for r in results if r.id not in seen_ids]
                seen_ids.update(r.id for r in results)
                return results, new
            except Exception:
                pass
        return [], []


def adaptive_search(api):
    """Run adaptive semantic search."""
    seen_ids = set()
    all_results = []

    # Phase 1: Search all base nouns, rank by density
    print(f"Phase 1: Probing {len(NOUNS)} base nouns")
    print("-" * 60)

    noun_scores = {}
    for noun in NOUNS:
        max_relevance = 0.0
        noun_new = 0
        for search_type in ("posts", "comments"):
            results, new = search_term(api, noun, search_type, seen_ids)
            all_results.extend(r.to_dict() for r in new)
            noun_new += len(new)
            if results:
                max_relevance = max(max_relevance, max(r.relevance for r in results))
            time.sleep(RATE_LIMIT_DELAY)

        noun_scores[noun] = max_relevance
        print(f"  '{noun}': max_relevance={max_relevance:.1f}, +{noun_new} new (total: {len(all_results)})")

    # Rank and select top N
    ranked = sorted(noun_scores.items(), key=lambda x: x[1], reverse=True)
    top_nouns = [noun for noun, _ in ranked[:TOP_N_TO_EXPAND]]
    bottom_nouns = [noun for noun, _ in ranked[TOP_N_TO_EXPAND:]]

    print(f"\n  Total after phase 1: {len(all_results)} unique results")
    print(f"  Densest nouns (will expand): {top_nouns}")
    print(f"  Sparse nouns (skipping):     {bottom_nouns}")

    # Phase 2: Expand dense nouns with adjectives
    print(f"\nPhase 2: Expanding top {TOP_N_TO_EXPAND} nouns x {len(ADJECTIVES)} adjectives")
    print("-" * 60)

    for noun in top_nouns:
        noun_new = 0
        for adj in ADJECTIVES:
            query = f"{adj} {noun}"
            for search_type in ("posts", "comments"):
                _, new = search_term(api, query, search_type, seen_ids)
                all_results.extend(r.to_dict() for r in new)
                noun_new += len(new)
                time.sleep(RATE_LIMIT_DELAY)

        print(f"  '{noun}' + adjectives: +{noun_new} new (total: {len(all_results)})")

    return all_results


def main():
    if not API_KEY:
        print("No API key found. Set MOLTBOOK_API_KEY or configure credentials.")
        return

    print("Adaptive Semantic Search")
    print("=" * 60)
    print(f"Nouns: {len(NOUNS)}, Adjectives: {len(ADJECTIVES)}, "
          f"Expand top: {TOP_N_TO_EXPAND}")
    print()

    with MoltbookAPI(api_key=API_KEY) as api:
        results = adaptive_search(api)

    print(f"\n{'=' * 60}")
    print(f"Total unique results: {len(results)}")

    # Save results
    if results:
        output_dir = Path("data")
        output_dir.mkdir(exist_ok=True)
        filepath = output_dir / "search_results.parquet"

        df_new = pl.DataFrame(results, infer_schema_length=None)

        if filepath.exists():
            df_old = pl.read_parquet(filepath)
            for col in set(df_old.columns) | set(df_new.columns):
                if col in df_old.columns and col in df_new.columns:
                    if df_old[col].dtype == pl.Null and df_new[col].dtype == pl.String:
                        df_old = df_old.with_columns(pl.col(col).cast(pl.String))
                    elif df_new[col].dtype == pl.Null and df_old[col].dtype == pl.String:
                        df_new = df_new.with_columns(pl.col(col).cast(pl.String))
            df = pl.concat([df_old, df_new], how="diagonal_relaxed") \
                .unique(subset=["id"], keep="last")
            print(f"Saved to {filepath} ({len(df)} total rows, {len(df_new)} new)")
        else:
            df = df_new
            print(f"Saved to {filepath} ({len(df)} rows)")

        df.write_parquet(filepath, compression="zstd")


if __name__ == "__main__":
    main()
