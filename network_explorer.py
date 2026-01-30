"""
Moltbook Network Explorer

Uses zendriver to visit moltbook.com and capture network calls.
This helps us understand the API structure for building a scraper.
"""

import asyncio
import json
from datetime import datetime

import zendriver as zd
from zendriver import cdp


class NetworkExplorer:
    def __init__(self, headless: bool = False):
        self.headless = headless
        self.browser = None
        self.page = None
        self.collected_responses = []
        self.pending_requests = {}
        self.request_headers = {}  # Track request headers
        self.ready_to_fetch = []

    async def __aenter__(self):
        self.browser = await zd.start(headless=self.headless)
        self.page = await self.browser.get('about:blank')

        # Enable network tracking via CDP
        await self.page.send(cdp.network.enable())

        # Set up handlers
        self.page.add_handler(cdp.network.RequestWillBeSent, self._on_request)
        self.page.add_handler(cdp.network.ResponseReceived, self._on_response)
        self.page.add_handler(cdp.network.LoadingFinished, self._on_loading_finished)

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.browser:
            await self.browser.stop()

    def _on_request(self, event):
        """Capture outgoing request headers."""
        if not isinstance(event, cdp.network.RequestWillBeSent):
            return

        url = event.request.url
        if '/api/' in url or 'moltbook' in url:
            self.request_headers[event.request_id] = {
                'url': url,
                'method': event.request.method,
                'headers': dict(event.request.headers) if event.request.headers else {},
            }

    def _on_response(self, event):
        """Capture response metadata."""
        if not isinstance(event, cdp.network.ResponseReceived):
            return

        url = event.response.url
        if not self._should_track(url):
            return

        req_headers = self.request_headers.get(event.request_id, {})

        self.pending_requests[event.request_id] = {
            'url': url,
            'status': event.response.status,
            'mime_type': event.response.mime_type,
            'response_headers': dict(event.response.headers) if event.response.headers else {},
            'request_headers': req_headers.get('headers', {}),
            'method': req_headers.get('method', 'GET'),
            'timestamp': datetime.now().isoformat(),
        }

    def _on_loading_finished(self, event):
        """Mark request as ready to have body fetched."""
        if not isinstance(event, cdp.network.LoadingFinished):
            return

        request_id = event.request_id
        if request_id in self.pending_requests:
            self.ready_to_fetch.append(request_id)

    async def fetch_pending_bodies(self):
        """Fetch all pending response bodies."""
        while self.ready_to_fetch:
            request_id = self.ready_to_fetch.pop(0)
            if request_id not in self.pending_requests:
                continue

            info = self.pending_requests.pop(request_id)
            try:
                result = await self.page.send(cdp.network.get_response_body(request_id))
                body = result[0] if isinstance(result, tuple) else result.body
                base64_encoded = result[1] if isinstance(result, tuple) else result.base64_encoded
                info['body'] = body
                info['body_was_base64'] = base64_encoded
            except Exception as e:
                info['body'] = None
                info['body_error'] = str(e)

            self.collected_responses.append(info)

    def _should_track(self, url: str) -> bool:
        """Filter URLs to track."""
        patterns = ['/api/', '?_rsc=']
        return any(p in url for p in patterns)

    async def get_cookies(self) -> dict:
        """Get cookies as a dictionary."""
        result = await self.page.send(cdp.network.get_cookies())
        return {cookie.name: cookie.value for cookie in result}

    async def navigate(self, url: str, wait_time: float = 5.0):
        """Navigate to a URL and wait for network activity."""
        print(f"Navigating to: {url}")
        await self.page.send(cdp.page.navigate(url))
        await self.page.wait_for_ready_state(until='complete', timeout=30)

        print(f"Waiting {wait_time}s for network activity...")
        await asyncio.sleep(wait_time)
        await self.fetch_pending_bodies()

    async def scroll_page(self, scrolls: int = 3, delay: float = 2.0):
        """Scroll the page to trigger lazy loading."""
        for i in range(scrolls):
            print(f"Scroll {i+1}/{scrolls}")
            await self.page.evaluate('window.scrollBy(0, window.innerHeight)')
            await asyncio.sleep(delay)
            await self.fetch_pending_bodies()

    def save_responses(self, filepath: str = "network_capture.json"):
        """Save captured responses to a JSON file."""
        data = []
        for r in self.collected_responses:
            entry = {k: v for k, v in r.items()}
            data.append(entry)

        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        print(f"\nSaved {len(data)} responses to {filepath}")


async def main():
    print("Starting Moltbook Network Explorer...")
    print("Capturing all network activity including RSC responses...")

    async with NetworkExplorer(headless=False) as explorer:
        # Visit main page first
        await explorer.navigate('https://www.moltbook.com/', wait_time=5)

        # Then visit submolts listing
        await explorer.navigate('https://www.moltbook.com/m', wait_time=5)

        # Then visit a specific submolt
        print("\n--- Visiting m/general ---")
        await explorer.navigate('https://www.moltbook.com/m/general', wait_time=10)

        # Scroll to trigger more loads
        await explorer.scroll_page(scrolls=2, delay=3)

        # Get cookies
        cookies = await explorer.get_cookies()
        print(f"\nCookies found: {list(cookies.keys())}")

        # Save all responses
        explorer.save_responses()

        # Analyze captured responses
        print("\n" + "="*60)
        print("CAPTURED RESPONSES")
        print("="*60)

        for resp in explorer.collected_responses:
            url = resp.get('url', '')
            status = resp.get('status', '?')
            mime = resp.get('mime_type', '')

            # Print summary
            short_url = url.split('?')[0] if '?' in url else url
            print(f"\n[{status}] {mime[:30]:30} {short_url}")

            # Show request headers for API calls
            if '/api/' in url:
                print("  Request headers:")
                for k, v in resp.get('request_headers', {}).items():
                    if k.lower() in ['authorization', 'x-api-key', 'cookie', 'x-auth']:
                        print(f"    {k}: {v[:50]}...")

            # Parse body if JSON or RSC
            if resp.get('body'):
                body = resp['body']
                if mime == 'application/json':
                    try:
                        data = json.loads(body)
                        keys = list(data.keys()) if isinstance(data, dict) else 'list'
                        print(f"  JSON keys: {keys}")
                    except:
                        pass
                elif 'x-component' in mime:
                    # RSC payload - show first few lines
                    lines = body.split('\n')[:3]
                    for line in lines:
                        print(f"  RSC: {line[:100]}...")

        # Save individual RSC responses for analysis
        print("\n\nSaving RSC responses...")
        rsc_count = 0
        for resp in explorer.collected_responses:
            if 'x-component' in resp.get('mime_type', '') and resp.get('body'):
                rsc_count += 1
                with open(f'rsc_response_{rsc_count}.txt', 'w') as f:
                    f.write(f"URL: {resp['url']}\n\n")
                    f.write(resp['body'])
        print(f"Saved {rsc_count} RSC responses")

        print("\nBrowser staying open for 5 seconds...")
        await asyncio.sleep(5)


if __name__ == '__main__':
    asyncio.run(main())
