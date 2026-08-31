"""Standalone API client for VRC 700 systems on the myVAILLANT cloud."""

from .auth import AuthenticationError, AuthServerError, VaillantAuth, get_realm
from .client import ApiError, QuotaExceededError, VRC700Client
from .models import VRC700System

__all__ = [
    "ApiError",
    "AuthServerError",
    "AuthenticationError",
    "QuotaExceededError",
    "VRC700Client",
    "VRC700System",
    "VaillantAuth",
    "get_realm",
]
