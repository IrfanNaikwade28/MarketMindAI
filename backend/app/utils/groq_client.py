"""
app/utils/groq_client.py
------------------------
Singleton Groq API client with retry logic and structured response parsing.
All agents import this module to talk to the LLM.
"""

import json
from typing import Any

from groq import AsyncGroq
from tenacity import retry, stop_after_attempt, wait_exponential
from loguru import logger

from app.config.settings import get_settings

settings = get_settings()

# ── Singleton client ───────────────────────────────────────────
_groq_client: AsyncGroq | None = None


def get_groq_client() -> AsyncGroq:
    """Return a cached AsyncGroq client instance."""
    global _groq_client
    if _groq_client is None:
        _groq_client = AsyncGroq(api_key=settings.groq_api_key)
        logger.info("Groq client initialized (model={})", settings.groq_model)
    return _groq_client


# ── Core completion helper ─────────────────────────────────────
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
async def groq_chat(
    messages: list[dict[str, str]],
    temperature: float | None = None,
    max_tokens: int | None = None,
    response_format: str = "text",   # "text" | "json"
) -> str:
    """
    Send a chat completion request to Groq.

    Args:
        messages:        OpenAI-style message list [{"role": ..., "content": ...}]
        temperature:     Override default temperature from settings.
        max_tokens:      Override default max_tokens from settings.
        response_format: "json" forces JSON output mode.

    Returns:
        Raw string content of the LLM response.
    """
    client = get_groq_client()

    kwargs: dict[str, Any] = {
        "model": settings.groq_model,
        "messages": messages,
        "temperature": temperature if temperature is not None else settings.groq_temperature,
        "max_tokens": max_tokens if max_tokens is not None else settings.groq_max_tokens,
    }

    if response_format == "json":
        kwargs["response_format"] = {"type": "json_object"}

    logger.debug("Groq request | model={} | messages={}", settings.groq_model, len(messages))

    response = await client.chat.completions.create(**kwargs)
    content = response.choices[0].message.content

    logger.debug("Groq response received | tokens_used={}", response.usage.total_tokens)
    return content


async def groq_json(
    messages: list[dict[str, str]],
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    """
    Convenience wrapper: calls Groq in JSON mode and parses the result.

    Returns:
        Parsed Python dict from the LLM's JSON response.

    Raises:
        ValueError: if the response cannot be parsed as JSON.
    """
    raw = await groq_chat(
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        response_format="json",
    )
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("Failed to parse Groq JSON response: {}", raw)
        raise ValueError(f"Groq returned invalid JSON: {e}") from e


# ── Health check ───────────────────────────────────────────────
async def check_groq_connection() -> bool:
    """
    Ping Groq with a minimal request.
    Used at startup to verify the API key is valid.
    """
    try:
        await groq_chat(
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=5,
        )
        logger.info("Groq connection OK")
        return True
    except Exception as e:
        logger.warning("Groq connection failed: {}", e)
        return False
