"""
main.py
-------
FastAPI application entrypoint.
- Registers all routers
- Connects to PostgreSQL and Redis on startup
- Runs Groq health check on startup
- Configures CORS and logging
"""

import sys
import asyncio

# ── Windows event loop fix ─────────────────────────────────────
# On Windows, Python 3.8+ defaults to ProactorEventLoop which does NOT
# support some socket operations needed by uvicorn's WebSocket handling.
# Forcing SelectorEventLoop (the default on Linux/macOS) fixes:
#   - WebSocket connection failures / silent hangs
#   - "RuntimeError: no running event loop" in background tasks
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import redis.asyncio as aioredis
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.config.settings import get_settings
from app.database.session import async_engine, Base
from app.utils.groq_client import check_groq_connection

settings = get_settings()

# ── Redis singleton ────────────────────────────────────────────
redis_client: aioredis.Redis | None = None


# ── Lifespan: startup & shutdown ───────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Code before `yield` runs on startup.
    Code after  `yield` runs on shutdown.
    """
    global redis_client

    logger.info("Starting {} [{}]", settings.app_name, settings.app_env)

    # 1. Create all DB tables (non-fatal if DB is not yet running)
    try:
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database connected & tables ready")
    except Exception as e:
        logger.warning("Database not available yet: {} — check DATABASE_URL and restart", e)

    # 1b. Seed system user required by Campaign FK (owner_id)
    try:
        from app.database.session import AsyncSessionLocal
        from app.models.user import User, UserRole
        from sqlalchemy import select
        SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000001"
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(User).where(User.id == SYSTEM_USER_ID))
            if result.scalar_one_or_none() is None:
                system_user = User(
                    id=SYSTEM_USER_ID,
                    email="system@ai-council.local",
                    username="system",
                    hashed_password="!",
                    role=UserRole.ADMIN,
                    is_active=True,
                    is_verified=True,
                )
                session.add(system_user)
                await session.commit()
                logger.info("System user seeded (id={})", SYSTEM_USER_ID)
            else:
                logger.info("System user already exists — skipping seed")
    except Exception as e:
        logger.warning("Could not seed system user: {}", e)

    # 2. Connect to Redis (non-fatal if Redis is not yet running)
    try:
        redis_client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
        await redis_client.ping()
        logger.info("Redis connected at {}", settings.redis_url)
    except Exception as e:
        logger.warning("Redis not available yet: {} — start Redis and restart the server", e)
        redis_client = None

    # 3. Groq health check (non-fatal — just warns if key is missing)
    groq_ok = await check_groq_connection()
    if not groq_ok:
        logger.warning("Groq API unreachable — add your GROQ_API_KEY to .env")

    # Store redis on app state so routes can access it
    app.state.redis = redis_client

    yield  # ← application runs here

    # Shutdown
    logger.info("Shutting down {}...", settings.app_name)
    if redis_client is not None:
        await redis_client.aclose()
    await async_engine.dispose()
    logger.info("Connections closed.")


# ── Application factory ────────────────────────────────────────
def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        description="Autonomous Multi-Agent AI Council for Social Media Strategy",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routers ────────────────────────────────────────────────
    from app.api.routes import campaigns, debates, content, analytics
    app.include_router(campaigns.router, prefix=settings.api_v1_prefix)
    app.include_router(debates.router,   prefix=settings.api_v1_prefix)
    app.include_router(content.router,   prefix=settings.api_v1_prefix)
    app.include_router(analytics.router, prefix=settings.api_v1_prefix)

    # ── Health endpoints ───────────────────────────────────────
    @app.get("/health", tags=["health"])
    async def health_check():
        return {
            "status": "ok",
            "app": settings.app_name,
            "env": settings.app_env,
        }

    @app.get("/health/groq", tags=["health"])
    async def groq_health():
        ok = await check_groq_connection()
        return {"groq_connected": ok, "model": settings.groq_model}

    @app.get("/health/redis", tags=["health"])
    async def redis_health():
        if app.state.redis is None:
            return {"redis_connected": False, "error": "Redis client not initialized"}
        try:
            pong = await app.state.redis.ping()
            return {"redis_connected": pong}
        except Exception as e:
            return {"redis_connected": False, "error": str(e)}

    return app


app = create_app()
