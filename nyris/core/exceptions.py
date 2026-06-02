"""Exceptions métier, indépendantes de HTTP.

Les services lèvent ces erreurs ; les routes les traduisent en codes HTTP.
"""

from __future__ import annotations


class DomainError(Exception):
    """Erreur métier de base."""


class NotFoundError(DomainError):
    """Ressource introuvable (-> 404)."""


class ConflictError(DomainError):
    """Transition/état invalide (-> 409)."""
