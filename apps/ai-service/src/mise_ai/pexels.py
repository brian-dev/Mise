"""Pexels image search for representative recipe photos (UX_DESIGN.md §8).

We don't generate or match exact dish photos — we fetch a free, representative
stock image keyed on the recipe title (falling back to cuisine), store its URL on
the recipe, and render it in the plan/recipe UI. Best-effort: no key, no match,
or any HTTP error all degrade to None and the recipe renders without a photo.
"""

from __future__ import annotations

import httpx

from .config import settings

_SEARCH = "https://api.pexels.com/v1/search"


def search_image(*queries: str) -> str | None:
    """Return a landscape photo URL for the first query that yields a hit.

    Tries each query in order (e.g. recipe title, then cuisine) so a too-specific
    title can fall back to something broader. Returns None when unconfigured or on
    any failure.
    """
    key = settings.pexels_api_key
    if not key:
        return None

    for q in queries:
        q = (q or "").strip()
        if not q:
            continue
        url = _search_one(key, q)
        if url:
            return url
    return None


def _search_one(key: str, query: str) -> str | None:
    try:
        resp = httpx.get(
            _SEARCH,
            params={"query": query, "per_page": 1, "orientation": "landscape"},
            headers={"Authorization": key},
            timeout=20,
        )
        if resp.status_code != 200:
            return None
        photos = resp.json().get("photos", [])
    except (httpx.HTTPError, ValueError):
        return None

    if not photos:
        return None
    src = photos[0].get("src", {})
    # `large` is a good balance of quality/size for a hero/card image.
    url = src.get("large") or src.get("medium") or src.get("original")
    return str(url) if url else None
