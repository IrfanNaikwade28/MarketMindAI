"""
app/database/session.py
-----------------------
Async SQLAlchemy engine + session factory.
Also exports a synchronous engine for Alembic migrations.
"""

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config.settings import get_settings

settings = get_settings()

# ── Async engine (used by FastAPI) ─────────────────────────────
# SQLite does not support pool_size / max_overflow — use NullPool instead.
# PostgreSQL (prod) keeps the connection pool args.
_is_sqlite = settings.database_url.startswith("sqlite")

async_engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,          # logs SQL in development
    **({} if _is_sqlite else {"pool_pre_ping": True, "pool_size": 10, "max_overflow": 20}),
    **({"poolclass": NullPool} if _is_sqlite else {}),
)

# ── Session factory ────────────────────────────────────────────
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,       # keep objects usable after commit
    autocommit=False,
    autoflush=False,
)

# ── Base class for all ORM models ──────────────────────────────
class Base(DeclarativeBase):
    pass


# ── FastAPI dependency ─────────────────────────────────────────
async def get_db() -> AsyncSession:
    """
    Yield an async DB session per request.
    Raises HTTP 503 if the database is not reachable, so the frontend
    receives a clean error instead of a 500 traceback.
    """
    from fastapi import HTTPException
    try:
        async with AsyncSessionLocal() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Database unavailable — check your DATABASE_URL and restart the server. ({type(e).__name__})",
        )
