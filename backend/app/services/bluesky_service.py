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

    # Increase timeout to handle large image blob uploads (default httpx timeout is 5s)
    client = Client()
    client._request._client.timeout = 60  # seconds
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

def _publish_sync(text: str, image_bytes: bytes | None = None) -> BlueskyPostResult:
    """
    Synchronous publish — called via asyncio.to_thread().

    If image_bytes is provided, uploads the image blob first then
    attaches it to the post via an image embed.
    """
    settings = get_settings()
    try:
        client    = _make_client()
        safe_text = _truncate(text)

        if image_bytes:
            # Upload the image blob; atproto auto-detects mime type from bytes
            logger.info("Bluesky | uploading image blob | size={} bytes", len(image_bytes))
            upload_resp = client.upload_blob(image_bytes)
            blob_ref    = upload_resp.blob
            logger.info("Bluesky | blob uploaded | mime={} | ref={}", blob_ref.mime_type, blob_ref.ref)

            # Build the image embed
            from atproto import models as bsky_models
            embed = bsky_models.AppBskyEmbedImages.Main(
                images=[
                    bsky_models.AppBskyEmbedImages.Image(
                        alt="AI-generated campaign image",
                        image=blob_ref,
                    )
                ]
            )
            response = client.send_post(text=safe_text, embed=embed)
            logger.info("Bluesky | published with image | uri={}", response.uri)
        else:
            response = client.send_post(text=safe_text)
            logger.info("Bluesky | published (text only) | uri={}", response.uri)

        uri     = response.uri
        cid     = response.cid
        web_url = _uri_to_web_url(uri, settings.bluesky_handle)

        return BlueskyPostResult(
            success=True,
            uri=uri,
            cid=cid,
            web_url=web_url,
            text=safe_text,
            published_at=datetime.now(timezone.utc).isoformat(),
        )

    except Exception as e:
        logger.exception("Bluesky | publish failed: {}", e)
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

async def publish_to_bluesky(text: str, image_bytes: bytes | None = None) -> BlueskyPostResult:
    """
    Publish a text post (with optional image) to Bluesky.

    Args:
        text:        Post text. Will be truncated to 300 graphemes if needed.
        image_bytes: Optional raw image bytes to attach to the post.
                     If provided, the image is uploaded as a blob and embedded.

    Returns:
        BlueskyPostResult with uri, cid, web_url and published_at on success.
    """
    if not text or not text.strip():
        return BlueskyPostResult(success=False, error="Post text cannot be empty.")

    return await asyncio.to_thread(_publish_sync, text, image_bytes)


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

async def build_bluesky_post(
    generated_content: list[dict[str, Any]],
    state: dict[str, Any] | None = None,
) -> str:
    """
    Build a rich, properly formatted Bluesky post (≤ 300 graphemes) from
    generated content, structured as:

        [Hook — first sentence of caption]

        [Body — as many complete sentences as fit the budget]

        [CTA — if it fits]

        [Hashtags — max 5, only if they fit]

    The key design rule: we NEVER hard-truncate mid-sentence.
    Instead we budget space top-down and only include a sentence
    if it fits completely within the remaining grapheme budget.

    Priority: Instagram caption → LinkedIn caption → Twitter tweet → any text.
    """
    import re

    if not generated_content:
        return ""

    by_platform: dict[str, dict] = {c["platform"]: c for c in generated_content}

    def _graphemes(text: str) -> int:
        """Approximate grapheme count (each char ≈ 1 grapheme for Latin/CJK)."""
        return len(text)

    def _hashtag_line(tags: list[str], max_tags: int = 5) -> str:
        cleaned = [f"#{t.lstrip('#')}" for t in tags[:max_tags]]
        return " ".join(cleaned)

    def _split_sentences(text: str) -> list[str]:
        """Split on sentence-ending punctuation followed by whitespace."""
        return [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]

    def _compose(hook: str, body_sentences: list[str], cta: str, tag_line: str) -> str:
        """
        Build the post by reserving space for hashtags FIRST, then greedily
        filling hook → body sentences → CTA into the remaining budget.
        This guarantees hashtags always appear in the final post.

        Budget:
          BUDGET (300) - hashtag_cost - separator_cost = body_budget
        """
        BUDGET = BSKY_MAX_GRAPHEMES

        # Reserve space for hashtags upfront (tag_line + "\n\n" separator)
        tag_cost    = (_graphemes("\n\n" + tag_line)) if tag_line else 0
        body_budget = BUDGET - tag_cost

        parts: list[str] = []
        used = 0

        def _add(segment: str, prefix: str = "\n\n") -> bool:
            nonlocal used
            addition = (prefix if parts else "") + segment
            cost = _graphemes(addition)
            if used + cost <= body_budget:
                parts.append(addition)
                used += cost
                return True
            return False

        # Hook is mandatory — word-boundary truncate if it alone exceeds budget
        if _graphemes(hook) > body_budget:
            truncated   = hook[:body_budget - 1]
            last_space  = truncated.rfind(" ")
            hook = (truncated[:last_space] if last_space > 0 else truncated) + "…"

        _add(hook, prefix="")

        # Body sentences — stop as soon as one doesn't fit
        for sentence in body_sentences:
            if not _add(sentence):
                break

        # CTA — only if it fits within body budget
        if cta:
            _add(cta)

        # Append hashtags (always, since space was pre-reserved)
        if tag_line:
            parts.append("\n\n" + tag_line)

        return "".join(parts).strip()

    # ── Attempt 1: Instagram caption ──────────────────────────────
    if "instagram" in by_platform:
        ig      = by_platform["instagram"]
        caption = ig.get("caption", "").strip()
        cta     = ig.get("call_to_action", "").strip()
        tags    = ig.get("hashtags", [])

        if caption:
            sentences = _split_sentences(caption)
            hook           = sentences[0] if sentences else caption
            body_sentences = sentences[1:] if len(sentences) > 1 else []
            tag_line       = _hashtag_line(tags, 5)
            return _compose(hook, body_sentences, cta, tag_line)

    # ── Attempt 2: LinkedIn caption ───────────────────────────────
    if "linkedin" in by_platform:
        li      = by_platform["linkedin"]
        caption = li.get("caption", "").strip()
        tags    = li.get("hashtags", [])

        if caption:
            sentences = _split_sentences(caption)
            hook           = sentences[0] if sentences else caption
            body_sentences = sentences[1:] if len(sentences) > 1 else []
            tag_line       = _hashtag_line(tags, 4)
            return _compose(hook, body_sentences, "", tag_line)

    # ── Attempt 3: Twitter tweet ──────────────────────────────────
    if "twitter" in by_platform:
        tw    = by_platform["twitter"]
        tweet = tw.get("tweet_text", "").strip()
        tags  = tw.get("hashtags", [])

        if tweet:
            tag_line = _hashtag_line(tags, 3)
            return _compose(tweet, [], "", tag_line)

    # ── Fallback: any available text field ────────────────────────
    for c in generated_content:
        for field_name in ("tweet_text", "caption", "tiktok_hook", "youtube_title"):
            val = c.get(field_name, "").strip()
            if val:
                sentences = _split_sentences(val)
                hook           = sentences[0] if sentences else val
                body_sentences = sentences[1:] if len(sentences) > 1 else []
                return _compose(hook, body_sentences, "", "")

    return ""


async def publish_approved_content(
    generated_content: list[dict[str, Any]],
    state: dict[str, Any] | None = None,
) -> BlueskyPostResult:
    """
    Build a rich formatted Bluesky post from generated content and publish it.

    Uses build_bluesky_post() to compose a properly structured post
    (hook + body + CTA + hashtags) before publishing.

    Args:
        generated_content: List of content dicts from content_to_dict().
        state: Optional debate state dict (passed through to build_bluesky_post).

    Returns:
        BlueskyPostResult.
    """
    if not generated_content:
        return BlueskyPostResult(success=False, error="No generated content provided.")

    text = await build_bluesky_post(generated_content, state=state)

    if not text:
        return BlueskyPostResult(success=False, error="No publishable text found in generated content.")

    return await publish_to_bluesky(text)
