"""Communication package — client interaction messages, email drafts, and stage templates."""

from .generator import MessageGenerator
from .models import ClientMessage, MessageStage

__all__ = [
    "ClientMessage",
    "MessageGenerator",
    "MessageStage",
]
