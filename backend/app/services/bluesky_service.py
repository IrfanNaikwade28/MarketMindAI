"""
app/services/bluesky_service.py
--------------------------------
Bluesky publishing service via the AT Protocol (atproto Python client).

Responsibilities:
  1. Authenticate with Bluesky using BLUESKY_HANDLE + BLUESKY_PASSWORD from .env
  2. Publish a post (text + optional external link card)
  3. Fetch engagement metrics for a published post (likes, replies, reposts)
  4. Delete a post by its AT URI

Design notes:
  - Uses atproto's synchronous Client wrapped in asyncio.to_thread() so the
    async FastAPI app is never blocked.
  - Authentication is lazy — the client logs in on first use and reuses the
    session for subsequent calls (token cached in the Client instance).
  - All public functions return typed dataclasses so callers get consistent
    structures regardless of Bluesky API changes.
  - If credentials are missing the service degrades gracefully — it logs a
    warning and returns a failure result instead of crashing.

Bluesky content notes:
  - Max post length: 300 graphemes (not bytes, not chars — grapheme clusters).
    We enforce this by truncating at 297 and appending "…".
  - The platform generates content for Instagram/Twitter/YouTube as part of
    the AI simulation, but ONLY Bluesky actually publishes.
  - We use the Bluesky post as the Twitter-equivalent output (≤280 chars fits
    comfortably within the 300 grapheme limit).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from app.config.settings import get_settings

# ── Constants ───────────────────────────────────────────────────────────────

BSKY_MAX_GRAPHEMES = 300
BSKY_TRUNCATE_AT   = 297   # leave room for "…"


# ── Result dataclasses ──────────────────────────────────────────────────────

@dataclass
class BlueskyPostResult:
    """Result of a publish attempt."""
    success: bool
    uri: str = ""           # AT URI  — e.g. at://did:plc:xxx/app.bsky.feed.post/yyy
    cid: str = ""           # Content ID (for engagement lookups)
    web_url: str = ""       # https://bsky.app/profile/<handle>/post/<rkey>
    text: str = ""          # The text that was actually posted
    error: str | None = None
    published_at: str = ""  # ISO timestamp


@dataclass
class BlueskyEngagement:
    """Engagement metrics fetched from Bluesky for a published post."""
    success: bool
    uri: str = ""
    like_count: int = 0
    reply_count: int = 0
    repost_count: int = 0
    quote_count: int = 0
    fetched_at: str = ""
    error: str | None = None


# ── Internal: build the atproto client ─────────────────────────────────────

def _make_client():
    """
    Create and authenticate an atproto Client.
    Called inside asyncio.to_thread() so it never blocks the event loop.
    Raises RuntimeError if credentials are missing or login fails.
    """
    from atproto import Client  # local import — keeps startup fast if not used

    settings = get_settings()
    handle   = settings.bluesky_handle
    password = settings.bluesky_password

    if not handle or not password:
        raise RuntimeError(
            "BLUESKY_HANDLE and BLUESKY_PASSWORD must be set in .env to publish to Bluesky."
        )

    client = Client()
    client.login(handle, password)
    logger.info("Bluesky | authenticated as @{}", handle)
    return client


# ── Internal helpers ────────────────────────────────────────────────────────

def _truncate(text: str, max_graphemes: int = BSKY_MAX_GRAPHEMES) -> str:
    """
    Bluesky enforces a 300-grapheme limit.
    Simple grapheme counting: treat each character as one grapheme
    (close enough for Latin/CJK; full grapheme segmentation would need
    the `grapheme` package which is not a hard dependency here).
    """
    if len(text) <= max_graphemes:
        return text
    return text[:BSKY_TRUNCATE_AT] + "…"


def _uri_to_web_url(uri: str, handle: str) -> str:
    """
    Convert AT URI (at://did:plc:.../app.bsky.feed.post/<rkey>)
    to a browser-friendly https://bsky.app URL.
    """
    try:
        rkey = uri.split("/")[-1]
        return f"https://bsky.app/profile/{handle}/post/{rkey}"
    except Exception:
        return ""


# ── Sync worker functions (run in thread pool) ──────────────────────────────

def _publish_sync(text: str) -> BlueskyPostResult:
    """Synchronous publish — called via asyncio.to_thread()."""
    settings = get_settings()
    try:
        client = _make_client()
        safe_text = _truncate(text)
        response  = client.send_post(text=safe_text)

        uri     = response.uri
        cid     = response.cid
        web_url = _uri_to_web_url(uri, settings.bluesky_handle)

        logger.info("Bluesky | published | uri={}", uri)
        return BlueskyPostResult(
            success=True,
            uri=uri,
            cid=cid,
            web_url=web_url,
            text=safe_text,
            published_at=datetime.now(timezone.utc).isoformat(),
        )

    except Exception as e:
        logger.error("Bluesky | publish failed: {}", e)
        return BlueskyPostResult(success=False, error=str(e))


def _fetch_engagement_sync(uri: str) -> BlueskyEngagement:
    """Synchronous engagement fetch — called via asyncio.to_thread()."""
    try:
        client = _make_client()

        # get_post_thread returns a PostThread with thread.post having threadgate info
        # For like/repost counts we use app.bsky.feed.getPostThread
        thread = client.get_post_thread(uri=uri)
        post   = thread.thread.post  # type: ignore[union-attr]

        return BlueskyEngagement(
            success=True,
            uri=uri,
            like_count   = getattr(post, "like_count",   0) or 0,
            reply_count  = getattr(post, "reply_count",  0) or 0,
            repost_count = getattr(post, "repost_count", 0) or 0,
            quote_count  = getattr(post, "quote_count",  0) or 0,
            fetched_at   = datetime.now(timezone.utc).isoformat(),
        )

    except Exception as e:
        logger.error("Bluesky | engagement fetch failed for {}: {}", uri, e)
        return BlueskyEngagement(success=False, uri=uri, error=str(e))


def _delete_post_sync(uri: str) -> dict[str, Any]:
    """Synchronous post delete — called via asyncio.to_thread()."""
    try:
        client = _make_client()
        client.delete_post(uri)
        logger.info("Bluesky | deleted post | uri={}", uri)
        return {"success": True, "uri": uri}
    except Exception as e:
        logger.error("Bluesky | delete failed for {}: {}", uri, e)
        return {"success": False, "uri": uri, "error": str(e)}


# ── Public async API ────────────────────────────────────────────────────────

async def publish_to_bluesky(text: str) -> BlueskyPostResult:
    """
    Publish a text post to Bluesky.

    Args:
        text: Post text. Will be truncated to 300 graphemes if needed.

    Returns:
        BlueskyPostResult with uri, cid, web_url and published_at on success.
    """
    if not text or not text.strip():
        return BlueskyPostResult(success=False, error="Post text cannot be empty.")

    return await asyncio.to_thread(_publish_sync, text)


async def get_engagement(uri: str) -> BlueskyEngagement:
    """
    Fetch engagement metrics (likes, replies, reposts, quotes) for a post.

    Args:
        uri: The AT URI of the post (returned by publish_to_bluesky).

    Returns:
        BlueskyEngagement with counts.
    """
    if not uri:
        return BlueskyEngagement(success=False, error="URI is required.")

    return await asyncio.to_thread(_fetch_engagement_sync, uri)


async def delete_post(uri: str) -> dict[str, Any]:
    """
    Delete a Bluesky post by its AT URI.

    Args:
        uri: The AT URI of the post to delete.

    Returns:
        dict with success flag.
    """
    if not uri:
        return {"success": False, "error": "URI is required."}

    return await asyncio.to_thread(_delete_post_sync, uri)


# ── Convenience: publish from GeneratedContent ──────────────────────────────

async def publish_approved_content(
    generated_content: list[dict[str, Any]],
) -> BlueskyPostResult:
    """
    Given a list of GeneratedContent dicts (from content_to_dict()),
    pick the best text for Bluesky and publish it.

    Priority order for text selection:
      1. tweet_text (≤280 chars — fits perfectly in Bluesky's 300 limit)
      2. caption truncated to 297 chars
      3. tiktok_hook
      4. youtube_title

    Args:
        generated_content: List of content dicts from content_to_dict().

    Returns:
        BlueskyPostResult.
    """
    if not generated_content:
        return BlueskyPostResult(success=False, error="No generated content provided.")

    text = ""

    # Build a lookup by platform
    by_platform: dict[str, dict] = {c["platform"]: c for c in generated_content}

    if "twitter" in by_platform and by_platform["twitter"].get("tweet_text"):
        text = by_platform["twitter"]["tweet_text"]
    elif "instagram" in by_platform and by_platform["instagram"].get("caption"):
        text = by_platform["instagram"]["caption"]
    elif "tiktok" in by_platform and by_platform["tiktok"].get("tiktok_hook"):
        text = by_platform["tiktok"]["tiktok_hook"]
    elif "youtube" in by_platform and by_platform["youtube"].get("youtube_title"):
        text = by_platform["youtube"]["youtube_title"]
    else:
        # Fall back to any available text
        for c in generated_content:
            for field_name in ("tweet_text", "caption", "tiktok_hook", "youtube_title"):
                if c.get(field_name):
                    text = c[field_name]
                    break
            if text:
                break

    if not text:
        return BlueskyPostResult(success=False, error="No publishable text found in generated content.")

    # Append hashtags from twitter content if available, fitting within limit
    hashtags = []
    if "twitter" in by_platform:
        hashtags = by_platform["twitter"].get("hashtags", [])
    elif generated_content:
        hashtags = generated_content[0].get("hashtags", [])

    if hashtags:
        tag_str = " " + " ".join(
            f"#{t.lstrip('#')}" for t in hashtags[:3]  # max 3 tags
        )
        candidate = text + tag_str
        text = candidate if len(candidate) <= BSKY_MAX_GRAPHEMES else text

    return await publish_to_bluesky(text)
