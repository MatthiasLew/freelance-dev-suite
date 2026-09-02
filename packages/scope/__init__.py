"""Scope package — scope change detection and proposal generator."""

from .detector import ScopeChangeDetector
from .models import ScopeChangeItem, ScopeClassification

__all__ = [
    "ScopeChangeDetector",
    "ScopeChangeItem",
    "ScopeClassification",
]
