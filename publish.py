"""
Publish generated blogs to Dev.to and Medium.
Set DEVTO_API_KEY and/or MEDIUM_INTEGRATION_TOKEN in .env.
"""
from __future__ import annotations

import os
import re
from typing import Any, Optional

import requests
from dotenv import load_dotenv

load_dotenv()


def extract_post_url(platform: str, response: dict[str, Any]) -> Optional[str]:
    """Parse post URL from Dev.to or Medium API JSON responses."""
    if not isinstance(response, dict):
        return None
    if platform == "devto":
        return response.get("url")
    if platform == "medium":
        data = response.get("data") or {}
        return data.get("url")
    return None


def _normalize_devto_tags(tags: Optional[list[str]]) -> Optional[list[str]]:
    """
    Dev.to rejects tags with spaces, hyphens, or special characters (often 422).
    Tags must be lowercase alphanumeric, max 4 tags, ~30 chars each.
    """
    if not tags:
        return None
    out: list[str] = []
    for raw in tags:
        if not raw or not isinstance(raw, str):
            continue
        t = raw.lower().strip()
        t = re.sub(r"[^a-z0-9]", "", t)
        if not t:
            continue
        if len(t) > 30:
            t = t[:30]
        if t not in out:
            out.append(t)
        if len(out) >= 4:
            break
    return out or None


def _http_error_detail(response: requests.Response) -> str:
    try:
        body = response.text
        if len(body) > 2000:
            body = body[:2000] + "…"
        return f"HTTP {response.status_code}: {body}"
    except Exception:
        return f"HTTP {response.status_code}"


def publish_to_devto(
    title: str,
    body_markdown: str,
    *,
    api_key: Optional[str] = None,
    published: bool = True,
    tags: Optional[list[str]] = None,
    description: Optional[str] = None,
) -> dict[str, Any]:
    """
    Create (and optionally publish) an article on Dev.to.
    Returns the API response dict with 'url' on success; raises on error.
    """
    key = api_key or os.environ.get("DEVTO_API_KEY")
    if not key:
        raise RuntimeError("DEVTO_API_KEY is not set. Add it to .env or pass api_key=.")

    payload: dict[str, Any] = {
        "article": {
            "title": title[:128] if len(title) > 128 else title,
            "body_markdown": body_markdown,
            "published": published,
        }
    }
    normalized = _normalize_devto_tags(tags)
    if normalized:
        payload["article"]["tags"] = normalized
    if description:
        payload["article"]["description"] = description[:300] if len(description) > 300 else description

    r = requests.post(
        "https://dev.to/api/articles",
        headers={"api-key": key, "Content-Type": "application/json"},
        json=payload,
        timeout=120,
    )
    # Retry once without tags if validation failed (tags are a common 422 cause).
    if r.status_code == 422 and normalized:
        payload["article"].pop("tags", None)
        r = requests.post(
            "https://dev.to/api/articles",
            headers={"api-key": key, "Content-Type": "application/json"},
            json=payload,
            timeout=120,
        )
    if not r.ok:
        raise RuntimeError(_http_error_detail(r))
    data = r.json()
    # Dev.to returns article with top-level url; ensure callers can link to the post.
    return data


def publish_to_medium(
    title: str,
    content_markdown: str,
    *,
    integration_token: Optional[str] = None,
    published: bool = True,
    tags: Optional[list[str]] = None,
    license: str = "all-rights-reserved",
) -> dict[str, Any]:
    """
    Create (and optionally publish) a post on Medium.
    Returns the API response dict with post URL on success; raises on error.
    """
    token = integration_token or os.environ.get("MEDIUM_INTEGRATION_TOKEN")
    if not token:
        raise RuntimeError(
            "MEDIUM_INTEGRATION_TOKEN is not set. Add it to .env or pass integration_token=."
        )

    # Get user id
    me = requests.get(
        "https://api.medium.com/v1/me",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=10,
    )
    me.raise_for_status()
    user_id = me.json().get("data", {}).get("id")
    if not user_id:
        raise RuntimeError("Could not get Medium user id.")

    payload: dict[str, Any] = {
        "title": title,
        "content": content_markdown,
        "contentFormat": "markdown",
        "license": license,
        "publishStatus": "public" if published else "draft",
    }
    if tags:
        payload["tags"] = tags[:5]  # Medium allows up to 5

    r = requests.post(
        f"https://api.medium.com/v1/users/{user_id}/posts",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()
