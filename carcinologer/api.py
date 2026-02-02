"""
Moltbook Scraper

A scraper for moltbook.com - the social network for AI agents.

API Endpoints discovered:
- GET /api/v1/submolts - List all communities
- GET /api/v1/agents/leaderboard - Agent rankings

Limitations:
- Individual submolt pages (/m/{name}) require authentication to view posts
- The /m page (communities listing) is publicly accessible
"""

import asyncio
import json
import os
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx


BASE_URL = "https://www.moltbook.com"
API_BASE = f"{BASE_URL}/api/v1"

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

# Load API key from environment or config file
API_KEY = os.getenv("MOLTBOOK_API_KEY")
if not API_KEY:
    config_path = Path.home() / ".config" / "moltbook" / "credentials.json"
    if config_path.exists():
        with open(config_path) as f:
            config = json.load(f)
            API_KEY = config.get("api_key")


@dataclass
class Submolt:
    """A moltbook community (like a subreddit)."""
    id: str
    name: str
    display_name: str
    description: str
    subscriber_count: int
    created_at: str
    last_activity_at: Optional[str] = None
    featured_at: Optional[str] = None
    created_by: Optional[dict] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Agent:
    """An AI agent on the leaderboard."""
    id: str
    name: str
    post_count: int = 0
    comment_count: int = 0
    score: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Post:
    """A post on Moltbook."""
    id: str
    title: str
    submolt: dict
    author: dict
    upvotes: int
    downvotes: int
    comment_count: int
    created_at: str
    content: Optional[str] = None
    url: Optional[str] = None
    is_pinned: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Comment:
    """A comment on a post."""
    id: str
    content: str
    author: dict
    upvotes: int
    downvotes: int
    created_at: str
    post_id: str
    parent_id: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


class MoltbookAPI:
    """
    API client for moltbook.com public endpoints.

    Example usage:
        with MoltbookAPI() as api:
            submolts = api.get_submolts()
            stats = api.get_stats()
            leaderboard = api.get_leaderboard()
            posts = api.get_all_posts()
    """

    def __init__(self, api_key: Optional[str] = None, max_retries: int = 3, retry_delay: float = 2.0):
        headers = DEFAULT_HEADERS.copy()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self.client = httpx.Client(headers=headers, timeout=30)
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.api_key = api_key

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.client.close()

    def _request(self, method: str, url: str) -> httpx.Response:
        """Make a request with retry logic for transient errors."""
        last_error = None
        for attempt in range(self.max_retries):
            try:
                r = self.client.request(method, url)
                if r.status_code in (429, 500, 502, 503, 504):
                    wait = self.retry_delay * (attempt + 1)
                    time.sleep(wait)
                    continue
                return r
            except httpx.TimeoutException as e:
                last_error = e
                time.sleep(self.retry_delay * (attempt + 1))
        if last_error:
            raise last_error
        return r

    def get_submolts(self) -> list[Submolt]:
        """
        Get all submolts (communities).

        Returns:
            List of Submolt objects
        """
        r = self._request("GET", f"{API_BASE}/submolts")
        r.raise_for_status()
        data = r.json()

        submolts = []
        for s in data.get("submolts", []):
            submolts.append(Submolt(
                id=s["id"],
                name=s["name"],
                display_name=s["display_name"],
                description=s["description"],
                subscriber_count=s["subscriber_count"],
                created_at=s["created_at"],
                last_activity_at=s.get("last_activity_at"),
                featured_at=s.get("featured_at"),
                created_by=s.get("created_by"),
            ))
        return submolts

    def get_leaderboard(self) -> list[Agent]:
        """
        Get agent leaderboard.

        Returns:
            List of Agent objects
        """
        r = self._request("GET", f"{API_BASE}/agents/leaderboard")
        r.raise_for_status()
        data = r.json()

        agents = []
        for a in data.get("leaderboard", []):
            agents.append(Agent(
                id=a.get("id", ""),
                name=a.get("name", "unknown"),
                post_count=a.get("post_count", 0),
                comment_count=a.get("comment_count", 0),
                score=a.get("score", 0),
            ))
        return agents

    def get_stats(self) -> dict:
        """
        Get site-wide statistics.

        Returns:
            Dict with total_submolts, total_posts, total_comments
        """
        r = self._request("GET", f"{API_BASE}/submolts")
        r.raise_for_status()
        data = r.json()
        return {
            "total_submolts": data.get("count", 0),
            "total_posts": data.get("total_posts", 0),
            "total_comments": data.get("total_comments", 0),
        }

    def get_posts(self, sort: str = "new", limit: int = 100, before: Optional[str] = None) -> dict:
        """
        Get posts from the main feed.

        Args:
            sort: Sort order - 'hot', 'new', 'top', 'rising'
            limit: Number of posts to fetch (max 100)
            before: Cursor for pagination (post ID)

        Returns:
            Dict with 'posts' list and 'next_cursor' for pagination
        """
        params = {"sort": sort, "limit": min(limit, 100)}
        if before:
            params["before"] = before

        r = self._request("GET", f"{API_BASE}/posts?" + "&".join(f"{k}={v}" for k, v in params.items()))

        if r.status_code == 401 and not self.api_key:
            print("  Note: Posts endpoint requires authentication. Provide an API key to access posts.")
            return {"posts": [], "next_cursor": None}

        r.raise_for_status()
        data = r.json()

        posts = []
        for p in data.get("posts", []):
            posts.append(Post(
                id=p["id"],
                title=p["title"],
                submolt=p["submolt"],
                author=p["author"],
                upvotes=p["upvotes"],
                downvotes=p["downvotes"],
                comment_count=p["comment_count"],
                created_at=p["created_at"],
                content=p.get("content"),
                url=p.get("url"),
                is_pinned=p.get("is_pinned", False),
            ))

        return {
            "posts": posts,
            "next_cursor": data.get("next_cursor"),
        }

    def get_submolt_posts(self, submolt_name: str, sort: str = "new", limit: int = 100, before: Optional[str] = None) -> dict:
        """
        Get posts from a specific submolt.

        Args:
            submolt_name: Name of the submolt (e.g., 'general')
            sort: Sort order - 'hot', 'new', 'top', 'rising'
            limit: Number of posts to fetch (max 100)
            before: Cursor for pagination

        Returns:
            Dict with 'posts' list and 'next_cursor' for pagination
        """
        params = {"sort": sort, "limit": min(limit, 100)}
        if before:
            params["before"] = before

        r = self._request("GET", f"{API_BASE}/submolts/{submolt_name}/feed?" + "&".join(f"{k}={v}" for k, v in params.items()))

        if r.status_code == 401 and not self.api_key:
            print(f"  Note: Submolt '{submolt_name}' requires authentication. Skipping.")
            return {"posts": [], "next_cursor": None}

        r.raise_for_status()
        data = r.json()

        posts = []
        for p in data.get("posts", []):
            posts.append(Post(
                id=p["id"],
                title=p["title"],
                submolt=p["submolt"],
                author=p["author"],
                upvotes=p["upvotes"],
                downvotes=p["downvotes"],
                comment_count=p["comment_count"],
                created_at=p["created_at"],
                content=p.get("content"),
                url=p.get("url"),
                is_pinned=p.get("is_pinned", False),
            ))

        return {
            "posts": posts,
            "next_cursor": data.get("next_cursor"),
        }

    def get_post_comments(self, post_id: str, sort: str = "top") -> list[Comment]:
        """
        Get all comments for a post.

        Args:
            post_id: ID of the post
            sort: Sort order - 'top', 'new', 'controversial'

        Returns:
            List of Comment objects
        """
        r = self._request("GET", f"{API_BASE}/posts/{post_id}/comments?sort={sort}")

        if r.status_code == 401 and not self.api_key:
            return []

        r.raise_for_status()
        data = r.json()

        comments = []
        for c in data.get("comments", []):
            comments.append(Comment(
                id=c["id"],
                content=c["content"],
                author=c["author"],
                upvotes=c["upvotes"],
                downvotes=c["downvotes"],
                created_at=c["created_at"],
                post_id=post_id,
                parent_id=c.get("parent_id"),
            ))

        return comments

    def get_all_posts(self, sort: str = "new", max_posts: Optional[int] = None) -> list[Post]:
        """
        Fetch all posts from the main feed with pagination.

        Args:
            sort: Sort order - 'hot', 'new', 'top', 'rising'
            max_posts: Maximum number of posts to fetch (None = all)

        Returns:
            List of all Post objects
        """
        all_posts = []
        cursor = None
        page = 0

        while True:
            page += 1
            print(f"  Fetching page {page}...")

            result = self.get_posts(sort=sort, limit=100, before=cursor)
            posts = result["posts"]

            if not posts:
                break

            all_posts.extend(posts)
            print(f"    Got {len(posts)} posts (total: {len(all_posts)})")

            if max_posts and len(all_posts) >= max_posts:
                all_posts = all_posts[:max_posts]
                break

            cursor = result.get("next_cursor")
            if not cursor:
                break

            time.sleep(0.5)  # Rate limiting

        return all_posts

    def get_all_submolt_posts(self, submolt_name: str, sort: str = "new", max_posts: Optional[int] = None) -> list[Post]:
        """
        Fetch all posts from a specific submolt with pagination.

        Args:
            submolt_name: Name of the submolt
            sort: Sort order
            max_posts: Maximum number of posts to fetch (None = all)

        Returns:
            List of all Post objects from the submolt
        """
        all_posts = []
        cursor = None
        page = 0

        while True:
            page += 1

            result = self.get_submolt_posts(submolt_name, sort=sort, limit=100, before=cursor)
            posts = result["posts"]

            if not posts:
                break

            all_posts.extend(posts)

            if max_posts and len(all_posts) >= max_posts:
                all_posts = all_posts[:max_posts]
                break

            cursor = result.get("next_cursor")
            if not cursor:
                break

            time.sleep(0.5)  # Rate limiting

        return all_posts


class MoltbookBrowser:
    """
    Browser-based scraper for content requiring JavaScript rendering.

    Note: Individual submolt pages may require authentication.
    The /m page (communities listing) is publicly accessible.
    """

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.browser = None
        self.page = None

    async def __aenter__(self):
        try:
            import zendriver as zd
            self.zd = zd
            from zendriver import cdp
            self.cdp = cdp
        except ImportError:
            raise ImportError(
                "zendriver is required for browser-based scraping. "
                "Install it with: pip install zendriver"
            )
        self.browser = await self.zd.start(headless=self.headless)
        self.page = await self.browser.get("about:blank")
        return self

    async def __aexit__(self, *args):
        if self.browser:
            await self.browser.stop()

    async def navigate(self, url: str, wait_time: float = 5.0):
        """Navigate to a URL and wait for content."""
        await self.page.send(self.cdp.page.navigate(url))
        await self.page.wait_for_ready_state(until="complete", timeout=30)
        await asyncio.sleep(wait_time)

    async def wait_for_content(self, timeout: float = 30.0) -> bool:
        """Wait for the page to finish loading."""
        start = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start < timeout:
            content = await self.page.evaluate("document.body.innerText")
            if "Loading..." not in content and len(content) > 500:
                return True
            await asyncio.sleep(1)
        return False

    async def get_page_content(self) -> str:
        """Get the visible text content of the current page."""
        return await self.page.evaluate("document.body.innerText")

    async def get_communities_page(self) -> dict:
        """
        Scrape the communities listing page (/m).

        Returns:
            Dict with communities info extracted from the page
        """
        await self.navigate(f"{BASE_URL}/m", wait_time=3)
        await self.wait_for_content(timeout=15)

        content = await self.get_page_content()

        # Parse basic info from page
        return {
            "content": content,
            "loaded": "Loading..." not in content,
        }


def scrape_all_data(api_key: Optional[str] = None, include_comments: bool = False, sort: str = "new") -> dict:
    """
    Scrape all data from Moltbook.

    Args:
        api_key: Moltbook API key (required for posts)
        include_comments: Whether to fetch comments for each post
        sort: Sort method for posts - 'new', 'hot', 'top', or 'rising'

    Returns:
        dict with keys: stats, submolts, agents, all_posts, submolt_posts, comments
    """
    print("Moltbook API Scraper")
    print("=" * 70)
    print(f"Sort method: {sort}")

    if not api_key:
        print("\nWarning: No API key provided. Post scraping will be limited.")
        print("To get full access:")
        print("  1. Set MOLTBOOK_API_KEY environment variable")
        print("  2. Or create ~/.config/moltbook/credentials.json with your api_key")
        print()

    result = {
        "stats": {},
        "submolts": [],
        "agents": [],
        "all_posts": [],
        "submolt_posts": {},
        "comments": {},
    }

    with MoltbookAPI(api_key=api_key) as api:
        # Get basic stats
        print("\n[1/5] Getting site statistics...")
        try:
            result["stats"] = api.get_stats()
            print(f"  Communities: {result['stats']['total_submolts']}")
            print(f"  Total Posts: {result['stats']['total_posts']}")
            print(f"  Total Comments: {result['stats']['total_comments']}")
        except Exception as e:
            print(f"  Error: {e}")

        # Get all submolts
        print("\n[2/5] Getting all submolts...")
        try:
            submolts = api.get_submolts()
            result["submolts"] = [s.to_dict() for s in submolts]
            print(f"  Found {len(submolts)} submolts")

            sorted_submolts = sorted(submolts, key=lambda x: x.subscriber_count, reverse=True)
            print("\n  Top 10 communities:")
            for s in sorted_submolts[:10]:
                print(f"    m/{s.name}: {s.display_name} ({s.subscriber_count} subs)")
        except Exception as e:
            print(f"  Error: {e}")
            submolts = []

        # Get leaderboard
        print("\n[3/5] Getting agent leaderboard...")
        try:
            agents = api.get_leaderboard()
            result["agents"] = [a.to_dict() for a in agents]
            print(f"  Found {len(agents)} agents")
            print("\n  Top 10 agents:")
            for a in agents[:10]:
                print(f"    {a.name}: {a.post_count} posts, {a.comment_count} comments, score {a.score}")
        except Exception as e:
            print(f"  Error: {e}")

        # Get all posts from main feed
        print(f"\n[4/5] Getting all posts from main feed (sort={sort})...")
        try:
            all_posts = api.get_all_posts(sort=sort)
            result["all_posts"] = [p.to_dict() for p in all_posts]
            print(f"  Total posts collected: {len(all_posts)}")
        except Exception as e:
            print(f"  Error: {e}")
            all_posts = []

        # Get posts from each submolt
        print(f"\n[5/5] Getting posts from each submolt (sort={sort})...")
        for submolt in submolts:
            try:
                print(f"  Scraping m/{submolt.name}...")
                posts = api.get_all_submolt_posts(submolt.name, sort=sort)
                if posts:
                    result["submolt_posts"][submolt.name] = [p.to_dict() for p in posts]
                    print(f"    Found {len(posts)} posts")
            except Exception as e:
                print(f"    Error: {e}")

        # Optionally get comments
        if include_comments and all_posts:
            print("\n[Bonus] Fetching comments for all posts...")
            for i, post in enumerate(all_posts, 1):
                try:
                    if post.comment_count > 0:
                        print(f"  [{i}/{len(all_posts)}] Post {post.id} ({post.comment_count} comments)")
                        comments = api.get_post_comments(post.id)
                        result["comments"][post.id] = [c.to_dict() for c in comments]
                        time.sleep(0.3)  # Rate limiting
                except Exception as e:
                    print(f"    Error: {e}")

    print("\n" + "=" * 70)
    print("✓ Scraping complete!")

    total_posts = len(result["all_posts"]) + sum(len(posts) for posts in result["submolt_posts"].values())
    total_comments = sum(len(comments) for comments in result["comments"].values())

    print(f"\nCollected:")
    print(f"  - {len(result['submolts'])} submolts")
    print(f"  - {len(result['agents'])} agents")
    print(f"  - {total_posts} posts")
    print(f"  - {total_comments} comments")

    return result


async def main():
    """Entry point."""
    import sys

    # Check for API key
    api_key = API_KEY

    # Parse arguments
    include_comments = "--with-comments" in sys.argv

    if not api_key:
        print("\n⚠️  No API key found!")
        print("\nTo scrape posts, you need a Moltbook API key.")
        print("Get one at: https://www.moltbook.com")
        print("\nThen either:")
        print("  export MOLTBOOK_API_KEY='your_key_here'")
        print("  or create ~/.config/moltbook/credentials.json")
        print()

        response = input("Continue without API key? (limited data) [y/N]: ")
        if response.lower() != 'y':
            return

    scrape_all_data(api_key=api_key, include_comments=include_comments)


if __name__ == "__main__":
    asyncio.run(main())
