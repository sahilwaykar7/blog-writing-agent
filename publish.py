"""
Publish generated blogs to Dev.to and Medium.
Set DEVTO_API_KEY and/or MEDIUM_INTEGRATION_TOKEN in .env.
"""
from __future__ import annotations

import os
import re
from typing import Any, Optional

import requests
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Markdown image: ![alt](path_or_url)
_MD_IMG = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


def cloudinary_configured() -> bool:
    """True if Cloudinary env is set (CLOUDINARY_URL or cloud_name + key + secret)."""
    if os.environ.get("CLOUDINARY_URL", "").strip():
        return True
    return all(
        os.environ.get(k, "").strip()
        for k in ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET")
    )


def _configure_cloudinary() -> None:
    import cloudinary

    url = os.environ.get("CLOUDINARY_URL", "").strip()
    if url:
        cloudinary.config(cloudinary_url=url)
    else:
        cloudinary.config(
            cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
            api_key=os.environ.get("CLOUDINARY_API_KEY"),
            api_secret=os.environ.get("CLOUDINARY_API_SECRET"),
        )


def rewrite_markdown_local_images_to_cloudinary(
    markdown: str,
    base_dir: Path,
) -> tuple[str, list[str]]:
    """
    Upload local image files referenced in markdown to Cloudinary and replace src with https URLs.
    Skips URLs that already start with http:// or https://.
    Returns (new_markdown, warning_messages).
    If Cloudinary is not configured, returns (markdown, ["Cloudinary not configured — add CLOUDINARY_* to .env."]).
    """
    notes: list[str] = []
    if not cloudinary_configured():
        return markdown, [
            "Cloudinary not configured — image links stay local; Dev.to will not show them. "
            "Set CLOUDINARY_URL or CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET."
        ]

    try:
        import cloudinary.uploader
    except ImportError:
        return markdown, ["Install Cloudinary SDK: pip install cloudinary"]

    _configure_cloudinary()
    cache: dict[str, str] = {}

    def replace_one(m: re.Match[str]) -> str:
        alt = m.group(1)
        src = m.group(2).strip().strip('"').strip("'")
        if src.startswith("http://") or src.startswith("https://"):
            return m.group(0)
        rel = src.lstrip("./")
        path = (base_dir / rel).resolve()
        key = str(path)
        if key in cache:
            return f"![{alt}]({cache[key]})"
        if not path.is_file():
            notes.append(f"Image not found (skipped): {src}")
            return m.group(0)
        try:
            out = cloudinary.uploader.upload(
                str(path),
                folder=os.environ.get("CLOUDINARY_FOLDER", "blog-writing-agent"),
            )
            secure = out.get("secure_url")
            if not secure:
                notes.append(f"Cloudinary upload returned no URL: {path.name}")
                return m.group(0)
            cache[key] = secure
            return f"![{alt}]({secure})"
        except Exception as e:
            notes.append(f"Cloudinary upload failed ({path.name}): {e}")
            return m.group(0)

    new_md = _MD_IMG.sub(replace_one, markdown)
    if cache:
        notes.insert(0, f"Uploaded {len(cache)} image(s) to Cloudinary.")
    return new_md, notes


def first_https_image_url(markdown: str) -> Optional[str]:
    """First https:// URL inside a markdown image, for Dev.to cover_image."""
    for m in _MD_IMG.finditer(markdown):
        src = m.group(2).strip()
        if src.startswith("https://"):
            return src
    return None


def markdown_still_has_local_image_paths(markdown: str) -> bool:
    """True if any markdown image still uses a non-http(s) src (e.g. images/foo.png)."""
    for m in _MD_IMG.finditer(markdown):
        src = m.group(2).strip().strip('"').strip("'")
        if src.startswith("http://") or src.startswith("https://"):
            continue
        if src and not src.startswith("data:"):
            return True
    return False


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
    cover_image: Optional[str] = None,
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
    if cover_image and cover_image.startswith("https://"):
        payload["article"]["cover_image"] = cover_image

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
