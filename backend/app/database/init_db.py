"""
app/database/init_db.py
-----------------------
Database initialization script.

Run this once to:
  1. Create all tables in PostgreSQL
  2. Seed a default admin user for development

Usage:
    cd backend
    source venv/bin/activate
    python -m app.database.init_db
"""

import asyncio
from loguru import logger

from app.database.session import async_engine, AsyncSessionLocal, Base
from app.config.settings import get_settings

# Import all models so Base.metadata knows about every table
import app.models  # noqa: F401 — triggers all model registrations

settings = get_settings()


async def create_tables() -> None:
    """Drop + recreate all tables (dev only). In production use Alembic."""
    async with async_engine.begin() as conn:
        logger.info("Creating all database tables...")
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Tables created successfully.")


async def seed_admin_user() -> None:
    """
    Insert a default admin user if none exists.
    Password is bcrypt-hashed.
    """
    from passlib.context import CryptContext
    from app.models.user import User, UserRole

    pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        result = await session.execute(select(User).where(User.email == "admin@aicouncil.dev"))
        existing = result.scalar_one_or_none()

        if existing:
            logger.info("Admin user already exists — skipping seed.")
            return

        admin = User(
            email="admin@aicouncil.dev",
            username="admin",
            full_name="AI Council Admin",
            hashed_password=pwd_ctx.hash("admin1234"),
            is_active=True,
            is_verified=True,
            role=UserRole.ADMIN,
            brand_name="AI Council Demo Brand",
            brand_voice="Innovative, bold, data-driven",
            target_audience="Tech-savvy marketers aged 25–40",
        )
        session.add(admin)
        await session.commit()
        logger.info("Default admin user seeded: admin@aicouncil.dev / admin1234")


async def init_db() -> None:
    """Full initialization: tables + seed data."""
    await create_tables()
    await seed_admin_user()
    await async_engine.dispose()
    logger.info("Database initialization complete.")


if __name__ == "__main__":
    asyncio.run(init_db())
