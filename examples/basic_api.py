#!/usr/bin/env python3
"""
Example: Using the MoltbookAPI client directly.

This approach gives you fine-grained control over what data you fetch.
Use this when you want specific data, not everything.

Prerequisites:
    pip install -e .  # Install carcinologer in editable mode
"""

import sys
from carcinologer import MoltbookAPI, API_KEY


def main():
    with MoltbookAPI(api_key=API_KEY) as api:
        # Get site statistics
        print("📊 Site Statistics:")
        stats = api.get_stats()
        print(f"  Communities: {stats['total_submolts']:,}")
        print(f"  Posts: {stats['total_posts']:,}")
        print(f"  Comments: {stats['total_comments']:,}")

        # Get all communities
        print("\n🏘️  Fetching communities...")
        submolts = api.get_submolts()
        print(f"  Found {len(submolts)} communities")

        # Show top 5 by subscribers
        top_submolts = sorted(submolts, key=lambda s: s.subscriber_count, reverse=True)[:5]
        print("\n  Top 5 communities:")
        for s in top_submolts:
            print(f"    m/{s.name}: {s.display_name} ({s.subscriber_count:,} subs)")

        # Get recent posts (with pagination cursor)
        print("\n📝 Recent posts from main feed:")
        result = api.get_posts(sort="new", limit=10)
        posts = result["posts"]

        for post in posts[:5]:
            print(f"\n  {post.title}")
            print(f"    👤 {post.author['name']}")
            print(f"    ⬆️  {post.upvotes} upvotes | 💬 {post.comment_count} comments")
            print(f"    🏘️  m/{post.submolt['name']}")

        # Get posts from a specific community
        print("\n📋 Posts from m/general:")
        result = api.get_submolt_posts("general", sort="hot", limit=5)
        general_posts = result["posts"]

        for post in general_posts:
            print(f"  • {post.title} ({post.upvotes} ⬆️)")

        # Get comments for a post
        if posts:
            first_post = posts[0]
            if first_post.comment_count > 0:
                print(f"\n💬 Comments on: {first_post.title}")
                comments = api.get_post_comments(first_post.id, sort="top")

                for comment in comments[:3]:
                    print(f"  • {comment.author['name']}: {comment.content[:80]}...")

        print("\n✅ Done!")


if __name__ == "__main__":
    if not API_KEY:
        print("❌ No API key found. Set MOLTBOOK_API_KEY or create ~/.config/moltbook/credentials.json")
        sys.exit(1)

    main()
