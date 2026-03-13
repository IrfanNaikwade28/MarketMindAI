"""
app/services/image_service.py
------------------------------
AI image generation via Cloudflare Workers AI (FLUX.1-schnell).

Free tier: 10,000 neurons/day (~500-1000 images) — no credit card needed.

API endpoint:
  POST https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/@cf/black-forest-labs/flux-1-schnell

Request body (JSON):
  { "prompt": "...", "num_steps": 4 }

Response:
  Raw image bytes (image/png) — no JSON envelope.

Responsibilities:
  1. Accept an image_prompt string (from content_generator.py)
  2. Call Cloudflare Workers AI and return raw PNG bytes
  3. Degrade gracefully — return None on failure so the caller
     can publish to Bluesky as text-only

Design notes:
  - Uses httpx for async HTTP.
  - num_steps=4 is optimal for flux-1-schnell (fast + good quality).
  - Timeout is 60s — generation typically takes 5–15s.
  - One retry on transient errors.
"""

from __future__ import annotations

import asyncio
import base64
from typing import Optional

import httpx
from loguru import logger

from app.config.settings import get_settings

# Cloudflare Workers AI model
_CF_MODEL  = "@cf/black-forest-labs/flux-1-schnell"
_CF_BASE   = "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"

# Timeout per attempt
_TIMEOUT_SECONDS = 60


def _build_url() -> str:
    settings = get_settings()
    return _CF_BASE.format(
        account_id=settings.cf_account_id,
        model=_CF_MODEL,
    )


async def generate_image(prompt: str) -> Optional[bytes]:
    """
    Generate an image from a text prompt using Cloudflare Workers AI FLUX.1-schnell.

    Args:
        prompt: Descriptive image prompt (from content_generator image_prompt field).

    Returns:
        Raw image bytes (PNG) on success, or None on failure.
    """
    settings = get_settings()

    if not settings.cf_account_id or not settings.cf_api_token:
        logger.warning("ImageService | CF_ACCOUNT_ID or CF_API_TOKEN not set — skipping image generation")
        return None

    if not prompt or not prompt.strip():
        logger.warning("ImageService | empty prompt — skipping image generation")
        return None

    url = _build_url()
    headers = {
        "Authorization": f"Bearer {settings.cf_api_token}",
        "Content-Type":  "application/json",
    }
    payload = {
        "prompt":    prompt.strip(),
        "num_steps": 4,   # flux-1-schnell is optimised for 4 steps
    }

    logger.info(
        "ImageService | generating image via Cloudflare Workers AI | prompt_len={}",
        len(prompt)
    )

    for attempt in range(1, 3):  # max 2 attempts
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
                response = await client.post(url, headers=headers, json=payload)

            if response.status_code == 200:
                # Cloudflare returns JSON: { "result": { "image": "<base64>" }, "success": true }
                try:
                    data = response.json()
                    if not data.get("success"):
                        logger.error("ImageService | CF returned success=false | errors={}", data.get("errors"))
                        return None

                    img_b64 = data.get("result", {}).get("image", "")
                    if not img_b64:
                        logger.error("ImageService | CF response missing result.image field")
                        return None

                    image_bytes = base64.b64decode(img_b64)
                    logger.info(
                        "ImageService | image generated | attempt={} | size={} bytes",
                        attempt, len(image_bytes)
                    )
                    return image_bytes

                except Exception as parse_err:
                    logger.error("ImageService | failed to parse CF response: {}", parse_err)
                    return None

            # Log and retry on server errors
            logger.warning(
                "ImageService | attempt {} | status={} | body={}",
                attempt, response.status_code, response.text[:200]
            )
            if attempt < 2:
                await asyncio.sleep(3)

        except httpx.TimeoutException:
            logger.warning(
                "ImageService | attempt {} | timed out after {}s",
                attempt, _TIMEOUT_SECONDS
            )
            if attempt < 2:
                await asyncio.sleep(2)

        except Exception as e:
            logger.error("ImageService | attempt {} | unexpected error: {}", attempt, e)
            return None

    logger.error("ImageService | all attempts failed — returning None (text-only post)")
    return None


def pick_best_image_prompt(generated_content: list[dict]) -> str:
    """
    Choose the best image_prompt from the list of generated content dicts.

    Priority: instagram → facebook → any platform with an image_prompt.
    Falls back to building a simple prompt from the instagram caption.
    """
    by_platform = {c["platform"]: c for c in generated_content}

    for platform in ("instagram", "facebook"):
        if platform in by_platform:
            prompt = by_platform[platform].get("image_prompt", "").strip()
            if prompt:
                logger.debug("ImageService | using image_prompt from {}", platform)
                return prompt

    # Any platform with an image_prompt
    for content in generated_content:
        prompt = content.get("image_prompt", "").strip()
        if prompt:
            return prompt

    # Last resort: derive from instagram caption
    if "instagram" in by_platform:
        caption = by_platform["instagram"].get("caption", "").strip()
        if caption:
            first_sentence = caption.split(".")[0].strip()
            return (
                f"Professional product photo, social media marketing: "
                f"{first_sentence}. Vibrant, high quality, 4k."
            )

    return ""
