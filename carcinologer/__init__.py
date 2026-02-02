"""
Carcinologer - A Python library for scraping and analyzing Moltbook data.

Moltbook is the social network for AI agents. Carcinologer helps you collect
and analyze data from this unique community.
"""

from .api import (
    MoltbookAPI,
    Submolt,
    Post,
    Comment,
    Agent,
    SearchResult,
    API_KEY,
    BASE_URL,
    API_BASE,
)

__version__ = "0.1.0"

__all__ = [
    "MoltbookAPI",
    "Submolt",
    "Post",
    "Comment",
    "Agent",
    "SearchResult",
    "API_KEY",
    "BASE_URL",
    "API_BASE",
]
