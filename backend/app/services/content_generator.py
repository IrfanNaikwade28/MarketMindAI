"""
app/services/content_generator.py
-----------------------------------
ContentGenerator — produces platform-specific social media posts
after the debate council has approved (or conditionally approved)
a campaign strategy.

Responsibilities:
  1. Read the finalized DebateState for campaign context + agent verdicts.
  2. Call Groq once per platform to generate tailored content.
  3. Return a list of GeneratedContent dataclasses (one per platform).
  4. Optionally persist each post as a ContentPost row via save_to_db().

Platforms supported:
  - Instagram  → long-form caption + hashtags + image prompt
  - Twitter/X  → ≤280 char tweet + hashtags
  - YouTube    → title (≤100 chars) + description + tags
  - LinkedIn   → professional post + hashtags
  - Facebook   → casual post + hashtags + image prompt
  - TikTok     → hook line + script outline + trending sounds suggestion

Design notes:
  - Each platform gets its own focused Groq call (better quality than
    asking for all platforms in one shot).
  - All calls are run concurrently via asyncio.gather() for speed.
  - The generator never crashes the caller — if one platform fails, the
    others still succeed and the error is captured in the dataclass.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from app.utils.groq_client import groq_json
from app.orchestrator.debate_state import DebateState


# ── Platform constants ──────────────────────────────────────────────────────

SUPPORTED_PLATFORMS = {
    "instagram", "twitter", "youtube",
    "linkedin", "facebook", "tiktok",
}


# ── Output dataclass ────────────────────────────────────────────────────────

@dataclass
class GeneratedContent:
    """
    Platform-specific generated content for one social media channel.

    Fields that are irrelevant to a platform are left as empty strings.
    e.g. tweet_text is empty for Instagram, youtube_title is empty for Twitter.
    """
    platform: str

    # Instagram / Facebook
    caption: str = ""

    # Twitter / X
    tweet_text: str = ""

    # YouTube
    youtube_title: str = ""
    youtube_description: str = ""

    # TikTok
    tiktok_hook: str = ""
    tiktok_script_outline: str = ""
    tiktok_trending_sounds: list[str] = field(default_factory=list)

    # Shared
    hashtags: list[str] = field(default_factory=list)
    image_prompt: str = ""
    call_to_action: str = ""

    # Scores carried over from debate agents
    predicted_engagement_score: float = 0.0
    brand_alignment_score: float = 0.0
    risk_score: float = 0.0

    # Generation metadata
    tokens_used: int = 0
    success: bool = True
    error: str | None = None


# ── System prompt ───────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are a world-class social media copywriter and content strategist.
You write platform-native content that is engaging, on-brand, and optimised for maximum
organic reach. You always respond with valid JSON only — no markdown, no explanation."""


# ── Per-platform prompt builders ────────────────────────────────────────────

def _build_instagram_prompt(ctx: dict[str, Any]) -> str:
    return f"""Generate an Instagram post for the following campaign.

Campaign: {ctx['campaign_title']}
Goal: {ctx['campaign_goal']}
Brand: {ctx['brand_name']}
Brand Voice: {ctx['brand_voice']}
Target Audience: {ctx['target_audience']}
Keywords: {', '.join(ctx['keywords'])}
Trend Angle: {ctx.get('trend_angle', 'Not specified')}
CMO Notes: {ctx.get('cmo_notes', 'None')}

Return a JSON object with these exact keys:
{{
  "caption": "<engaging Instagram caption, 150-300 words, line breaks for readability>",
  "hashtags": ["<tag1>", "<tag2>", ..., "<tag15 max>"],
  "image_prompt": "<detailed DALL-E / Stable Diffusion prompt for the hero image>",
  "call_to_action": "<short CTA line, e.g. 'Link in bio!'>",
  "rationale": "<1 sentence explaining the creative choice>"
}}"""


def _build_twitter_prompt(ctx: dict[str, Any]) -> str:
    return f"""Generate a Twitter/X post for the following campaign.

Campaign: {ctx['campaign_title']}
Goal: {ctx['campaign_goal']}
Brand: {ctx['brand_name']}
Brand Voice: {ctx['brand_voice']}
Target Audience: {ctx['target_audience']}
Keywords: {', '.join(ctx['keywords'])}
Trend Angle: {ctx.get('trend_angle', 'Not specified')}
CMO Notes: {ctx.get('cmo_notes', 'None')}

IMPORTANT: tweet_text must be 280 characters or fewer (including spaces).

Return a JSON object with these exact keys:
{{
  "tweet_text": "<tweet content, MAX 280 chars, punchy and engaging>",
  "hashtags": ["<tag1>", "<tag2>", "<tag3 max>"],
  "call_to_action": "<short CTA if needed, e.g. 'Thread below 🧵'>",
  "rationale": "<1 sentence explaining the creative choice>"
}}"""


def _build_youtube_prompt(ctx: dict[str, Any]) -> str:
    return f"""Generate a YouTube video title and description for the following campaign.

Campaign: {ctx['campaign_title']}
Goal: {ctx['campaign_goal']}
Brand: {ctx['brand_name']}
Brand Voice: {ctx['brand_voice']}
Target Audience: {ctx['target_audience']}
Keywords: {', '.join(ctx['keywords'])}
Trend Angle: {ctx.get('trend_angle', 'Not specified')}
CMO Notes: {ctx.get('cmo_notes', 'None')}

Return a JSON object with these exact keys:
{{
  "youtube_title": "<SEO-optimised title, MAX 100 chars, curiosity-driven>",
  "youtube_description": "<full description, 200-400 words, with timestamps placeholder, keywords naturally woven in>",
  "hashtags": ["<tag1>", "<tag2>", ..., "<tag8 max>"],
  "call_to_action": "<subscribe/like CTA line>",
  "rationale": "<1 sentence explaining the creative choice>"
}}"""


def _build_linkedin_prompt(ctx: dict[str, Any]) -> str:
    return f"""Generate a LinkedIn post for the following campaign.

Campaign: {ctx['campaign_title']}
Goal: {ctx['campaign_goal']}
Brand: {ctx['brand_name']}
Brand Voice: {ctx['brand_voice']}
Target Audience: {ctx['target_audience']}
Keywords: {', '.join(ctx['keywords'])}
Trend Angle: {ctx.get('trend_angle', 'Not specified')}
CMO Notes: {ctx.get('cmo_notes', 'None')}

LinkedIn tone: professional yet conversational, thought-leadership oriented.

Return a JSON object with these exact keys:
{{
  "caption": "<LinkedIn post, 150-250 words, insight-led with a hook opening line>",
  "hashtags": ["<tag1>", "<tag2>", ..., "<tag5 max>"],
  "call_to_action": "<CTA encouraging comments or shares>",
  "rationale": "<1 sentence explaining the creative choice>"
}}"""


def _build_facebook_prompt(ctx: dict[str, Any]) -> str:
    return f"""Generate a Facebook post for the following campaign.

Campaign: {ctx['campaign_title']}
Goal: {ctx['campaign_goal']}
Brand: {ctx['brand_name']}
Brand Voice: {ctx['brand_voice']}
Target Audience: {ctx['target_audience']}
Keywords: {', '.join(ctx['keywords'])}
Trend Angle: {ctx.get('trend_angle', 'Not specified')}
CMO Notes: {ctx.get('cmo_notes', 'None')}

Return a JSON object with these exact keys:
{{
  "caption": "<Facebook post, 100-200 words, conversational and community-focused>",
  "hashtags": ["<tag1>", "<tag2>", "<tag3 max>"],
  "image_prompt": "<detailed DALL-E / Stable Diffusion prompt for the accompanying image>",
  "call_to_action": "<CTA encouraging reactions or shares>",
  "rationale": "<1 sentence explaining the creative choice>"
}}"""


def _build_tiktok_prompt(ctx: dict[str, Any]) -> str:
    return f"""Generate a TikTok video concept for the following campaign.

Campaign: {ctx['campaign_title']}
Goal: {ctx['campaign_goal']}
Brand: {ctx['brand_name']}
Brand Voice: {ctx['brand_voice']}
Target Audience: {ctx['target_audience']}
Keywords: {', '.join(ctx['keywords'])}
Trend Angle: {ctx.get('trend_angle', 'Not specified')}
CMO Notes: {ctx.get('cmo_notes', 'None')}

Return a JSON object with these exact keys:
{{
  "tiktok_hook": "<first 3 seconds hook line that stops the scroll>",
  "tiktok_script_outline": "<brief scene-by-scene outline, 60-90 second video>",
  "tiktok_trending_sounds": ["<sound/song suggestion 1>", "<sound/song suggestion 2>"],
  "hashtags": ["<tag1>", "<tag2>", ..., "<tag5 max>"],
  "call_to_action": "<end-of-video CTA>",
  "rationale": "<1 sentence explaining the creative choice>"
}}"""


_PROMPT_BUILDERS = {
    "instagram": _build_instagram_prompt,
    "twitter":   _build_twitter_prompt,
    "youtube":   _build_youtube_prompt,
    "linkedin":  _build_linkedin_prompt,
    "facebook":  _build_facebook_prompt,
    "tiktok":    _build_tiktok_prompt,
}


# ── Internal: call Groq for one platform ───────────────────────────────────

async def _generate_for_platform(
    platform: str,
    ctx: dict[str, Any],
) -> GeneratedContent:
    """Call Groq for a single platform and parse the response."""
    try:
        prompt_builder = _PROMPT_BUILDERS.get(platform)
        if not prompt_builder:
            raise ValueError(f"Unsupported platform: {platform}")

        user_prompt = prompt_builder(ctx)
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt},
        ]

        data = await groq_json(messages=messages, temperature=0.75)
        tokens = data.pop("_tokens_used", 0)

        result = GeneratedContent(
            platform=platform,
            tokens_used=tokens,
            predicted_engagement_score=ctx.get("engagement_score", 0.0),
            brand_alignment_score=ctx.get("brand_alignment_score", 0.0),
            risk_score=ctx.get("risk_score", 0.0),
        )

        # Map parsed JSON fields onto the dataclass
        result.hashtags      = data.get("hashtags", [])
        result.call_to_action = data.get("call_to_action", "")

        if platform in ("instagram", "facebook", "linkedin"):
            result.caption = data.get("caption", "")
        if platform == "facebook":
            result.image_prompt = data.get("image_prompt", "")
        if platform == "instagram":
            result.image_prompt = data.get("image_prompt", "")
        if platform == "twitter":
            result.tweet_text = data.get("tweet_text", "")
        if platform == "youtube":
            result.youtube_title       = data.get("youtube_title", "")
            result.youtube_description = data.get("youtube_description", "")
        if platform == "tiktok":
            result.tiktok_hook            = data.get("tiktok_hook", "")
            result.tiktok_script_outline  = data.get("tiktok_script_outline", "")
            result.tiktok_trending_sounds = data.get("tiktok_trending_sounds", [])

        logger.info("ContentGenerator | {} | tokens={}", platform, tokens)
        return result

    except Exception as e:
        logger.error("ContentGenerator | {} FAILED: {}", platform, e)
        return GeneratedContent(
            platform=platform,
            success=False,
            error=str(e),
        )


# ── Public API ──────────────────────────────────────────────────────────────

async def generate_content(
    state: DebateState,
    platforms: list[str] | None = None,
) -> list[GeneratedContent]:
    """
    Generate platform-specific posts for all (or selected) platforms.

    Args:
        state     : Finalized DebateState from the orchestrator.
        platforms : Subset of platforms to generate for.
                    Defaults to state['platforms'].

    Returns:
        List of GeneratedContent (one per platform, concurrent generation).
    """
    target_platforms = platforms or state.get("platforms", [])
    # Normalise to lowercase and filter unsupported
    target_platforms = [
        p.lower() for p in target_platforms
        if p.lower() in SUPPORTED_PLATFORMS
    ]

    if not target_platforms:
        logger.warning("ContentGenerator: no supported platforms specified, skipping.")
        return []

    # Build shared context from debate state + agent verdicts
    trend_out      = state.get("trend_agent_output", {})
    engagement_out = state.get("engagement_agent_output", {})
    brand_out      = state.get("brand_agent_output", {})
    risk_out       = state.get("risk_agent_output", {})
    cmo_out        = state.get("cmo_agent_output", {})

    # Extract the most useful signals from each agent
    trend_structured   = trend_out.get("structured_output", {})
    cmo_structured     = cmo_out.get("structured_output", {})
    engagement_structured = engagement_out.get("structured_output", {})

    ctx = {
        # Campaign basics
        "campaign_title":  state.get("campaign_title", ""),
        "campaign_goal":   state.get("campaign_goal", ""),
        "brand_name":      state.get("brand_name", ""),
        "brand_voice":     state.get("brand_voice", ""),
        "target_audience": state.get("target_audience", ""),
        "keywords":        state.get("keywords", []),

        # Agent intelligence
        "trend_angle":     trend_structured.get("content_angle", ""),
        "viral_hook":      trend_structured.get("viral_hook", ""),
        "cmo_notes":       cmo_structured.get("modifications_required", ""),
        "best_post_time":  engagement_structured.get("optimal_posting_times", {}),

        # Scores for metadata
        "engagement_score":      engagement_out.get("engagement_score", 0.0),
        "brand_alignment_score": 1.0 - risk_out.get("risk_score", 0.0),
        "risk_score":            risk_out.get("risk_score", 0.0),
    }

    logger.info(
        "ContentGenerator: generating for {} platforms: {}",
        len(target_platforms), target_platforms
    )

    # Run all platform generations concurrently
    tasks = [_generate_for_platform(p, ctx) for p in target_platforms]
    results: list[GeneratedContent] = await asyncio.gather(*tasks)

    success_count = sum(1 for r in results if r.success)
    logger.info(
        "ContentGenerator: done | {}/{} platforms succeeded",
        success_count, len(results)
    )

    return list(results)


def content_to_dict(content: GeneratedContent) -> dict[str, Any]:
    """Serialize a GeneratedContent dataclass to a plain dict (for API responses)."""
    return {
        "platform":                  content.platform,
        "caption":                   content.caption,
        "tweet_text":                content.tweet_text,
        "youtube_title":             content.youtube_title,
        "youtube_description":       content.youtube_description,
        "tiktok_hook":               content.tiktok_hook,
        "tiktok_script_outline":     content.tiktok_script_outline,
        "tiktok_trending_sounds":    content.tiktok_trending_sounds,
        "hashtags":                  content.hashtags,
        "image_prompt":              content.image_prompt,
        "call_to_action":            content.call_to_action,
        "predicted_engagement_score": content.predicted_engagement_score,
        "brand_alignment_score":     content.brand_alignment_score,
        "risk_score":                content.risk_score,
        "tokens_used":               content.tokens_used,
        "success":                   content.success,
        "error":                     content.error,
    }
