"""
Authentication dependency for FastAPI.

Verifies Supabase-issued JWTs by calling Supabase's auth.getUser()
with the service role client. Returns the authenticated user's ID/email
or raises 401.
"""

from __future__ import annotations

import os
import logging

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)

# Lazily initialised — populated on first call to get_current_user
_supabase_client = None

security = HTTPBearer(auto_error=False)


def _get_supabase():
    """Return a Supabase client initialised with the **service role key**."""
    global _supabase_client
    if _supabase_client is None:
        from supabase import create_client

        url = os.environ.get("SUPABASE_URL", "").strip()
        service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        if not url or not service_key:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in backend/.env"
            )
        _supabase_client = create_client(url, service_key)
    return _supabase_client


class AuthenticatedUser:
    """Simple container returned by get_current_user."""

    __slots__ = ("id", "email")

    def __init__(self, user_id: str, email: str):
        self.id = user_id
        self.email = email

    def __repr__(self) -> str:
        return f"AuthenticatedUser(id={self.id!r}, email={self.email!r})"


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> AuthenticatedUser:
    """FastAPI dependency — verify Supabase JWT and return AuthenticatedUser.

    Reads the ``Authorization: Bearer <token>`` header, calls Supabase's
    ``auth.get_user(token)`` (which validates the JWT server-side using the
    service role key), and returns the user's UUID and email.

    Raises ``HTTPException(401)`` if the token is missing or invalid.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    try:
        sb = _get_supabase()
        user_response = sb.auth.get_user(token)
        user = user_response.user
        if user is None:
            raise ValueError("No user returned from Supabase")
        return AuthenticatedUser(user_id=user.id, email=user.email or "")
    except Exception as exc:
        logger.warning("JWT verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
