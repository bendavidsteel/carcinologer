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
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional

import httpx
import zendriver as zd
from zendriver import cdp


BASE_URL = "https://www.moltbook.com"
API_BASE = f"{BASE_URL}/api/v1"

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
}


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


class MoltbookAPI:
    """
    API client for moltbook.com public endpoints.

    Example usage:
        with MoltbookAPI() as api:
            submolts = api.get_submolts()
            stats = api.get_stats()
            leaderboard = api.get_leaderboard()
    """

    def __init__(self, max_retries: int = 3, retry_delay: float = 2.0):
        self.client = httpx.Client(headers=DEFAULT_HEADERS, timeout=30)
        self.max_retries = max_retries
        self.retry_delay = retry_delay

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
        self.browser = await zd.start(headless=self.headless)
        self.page = await self.browser.get("about:blank")
        return self

    async def __aexit__(self, *args):
        if self.browser:
            await self.browser.stop()

    async def navigate(self, url: str, wait_time: float = 5.0):
        """Navigate to a URL and wait for content."""
        await self.page.send(cdp.page.navigate(url))
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


def save_to_json(data: list | dict, filename: str):
    """Helper to save data to JSON file."""
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2, default=str)
    print(f"Saved to {filename}")


async def main():
    """Demo and example usage."""
    print("Moltbook Scraper")
    print("=" * 50)

    # API usage
    with MoltbookAPI() as api:
        print("\n[API] Getting stats...")
        try:
            stats = api.get_stats()
            print(f"  Communities: {stats['total_submolts']}")
            print(f"  Posts: {stats['total_posts']}")
            print(f"  Comments: {stats['total_comments']}")
        except Exception as e:
            print(f"  Error: {e}")

        print("\n[API] Getting submolts...")
        try:
            submolts = api.get_submolts()
            print(f"  Found {len(submolts)} submolts")

            # Show top 5 by subscribers
            sorted_submolts = sorted(submolts, key=lambda x: x.subscriber_count, reverse=True)
            print("\n  Top communities by subscribers:")
            for s in sorted_submolts[:5]:
                print(f"    - m/{s.name}: {s.display_name} ({s.subscriber_count} subscribers)")

            # Save to file
            save_to_json([s.to_dict() for s in submolts], "submolts.json")

        except Exception as e:
            print(f"  Error: {e}")

        print("\n[API] Getting leaderboard...")
        try:
            agents = api.get_leaderboard()
            print(f"  Found {len(agents)} agents")
            for a in agents[:5]:
                print(f"    - {a.name}: {a.post_count} posts, score {a.score}")

            save_to_json([a.to_dict() for a in agents], "leaderboard.json")

        except Exception as e:
            print(f"  Error: {e}")

    # Browser usage (for pages requiring JS)
    print("\n[Browser] Testing page rendering...")
    async with MoltbookBrowser(headless=False) as browser:
        result = await browser.get_communities_page()
        if result["loaded"]:
            print("  Communities page loaded successfully")
            # Save content sample
            with open("communities_page.txt", "w") as f:
                f.write(result["content"])
            print("  Saved page content to communities_page.txt")
        else:
            print("  Page did not fully load")

    print("\n" + "=" * 50)
    print("Done! Check generated JSON files for data.")


if __name__ == "__main__":
    asyncio.run(main())
