"""
app/config/settings.py
----------------------
Central configuration using Pydantic BaseSettings.
Reads all values from the .env file automatically.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Application ────────────────────────────────────────────
    app_name: str = "AI Council"
    app_env: str = "development"
    debug: bool = True
    secret_key: str = "changeme"
    api_v1_prefix: str = "/api/v1"

    # ── PostgreSQL ─────────────────────────────────────────────
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "ai_council"
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/ai_council"
    )

    # ── Redis ──────────────────────────────────────────────────
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_url: str = "redis://localhost:6379/0"

    # ── Celery ─────────────────────────────────────────────────
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # ── Groq API ───────────────────────────────────────────────
    groq_api_key: str = ""
    groq_model: str = "meta-llama/llama-4-scout-17b-16e-instruct"
    groq_max_tokens: int = 4096
    groq_temperature: float = 0.7

    # ── JWT Auth ───────────────────────────────────────────────
    jwt_secret_key: str = "changeme-jwt"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60

    # ── Bluesky (AT Protocol) ──────────────────────────────────
    bluesky_handle: str = ""        # e.g. yourhandle.bsky.social
    bluesky_password: str = ""      # App password from Bluesky settings

    # ── Hugging Face (Image Generation) ───────────────────────
    hf_token: str = ""
    hf_image_model: str = "black-forest-labs/FLUX.1-schnell"

    # ── Cloudflare Workers AI (Image Generation) ───────────────
    cf_account_id: str = ""
    cf_api_token: str = ""

    # ── CORS ───────────────────────────────────────────────────
    allowed_origins: str = "http://localhost:3000,http://localhost:5173"

    @property
    def allowed_origins_list(self) -> list[str]:
        """Parse comma-separated CORS origins into a list."""
        return [o.strip() for o in self.allowed_origins.split(",")]


@lru_cache()
def get_settings() -> Settings:
    """
    Cached settings instance.
    Call get_settings() anywhere in the app — returns the same object.
    """
    return Settings()
