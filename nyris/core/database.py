"""Connexion PostgreSQL : un seul Engine + fabrique de sessions."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from nyris.core.config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,  # évite les connexions mortes
    future=True,
    echo=settings.debug,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)
