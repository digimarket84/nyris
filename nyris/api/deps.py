"""Dépendances FastAPI partagées."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy.orm import Session

from nyris.core.database import SessionLocal


def get_db() -> Iterator[Session]:
    """Fournit une session DB par requête, fermée automatiquement."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
