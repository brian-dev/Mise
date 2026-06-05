"""Auth: verify Supabase JWTs and authorize household membership (ARCHITECTURE §4).

The service trusts the bearer JWT minted by Supabase Auth (HS256, signed with the
project JWT secret), derives the user from its `sub`, and checks household
membership in code — it never relies on the request body alone for the caller's
identity, and never relies on RLS as its only guard.

Enforcement is gated by `settings.require_auth`. While off (pre-login-UI), a
request without a token is treated as anonymous (user_id=None) and membership
checks are skipped, preserving the dev harness. With a token present, it is
always verified.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import jwt
import psycopg
from fastapi import Header, HTTPException

from .config import settings

# Lazily-built JWKS client for verifying Supabase's asymmetric (ES256) user
# tokens. PyJWKClient fetches + caches the signing keys from the JWKS endpoint.
_jwk_client: jwt.PyJWKClient | None = None


def _jwks() -> jwt.PyJWKClient:
    global _jwk_client
    if _jwk_client is None:
        _jwk_client = jwt.PyJWKClient(settings.supabase_jwks_url)
    return _jwk_client


def _decode(token: str) -> UUID:
    try:
        alg = jwt.get_unverified_header(token).get("alg")
        if alg == "HS256":
            # Legacy symmetric secret (also used by tests).
            key: Any = settings.supabase_jwt_secret
            algorithms = ["HS256"]
        else:
            # Supabase user tokens: ES256 (or RS256) verified via JWKS public key.
            key = _jwks().get_signing_key_from_jwt(token).key
            algorithms = ["ES256", "RS256"]
        payload = jwt.decode(
            token,
            key,
            algorithms=algorithms,
            audience=settings.supabase_jwt_aud,
        )
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail="invalid token") from e
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="token missing subject")
    try:
        return UUID(str(sub))
    except ValueError as e:
        raise HTTPException(status_code=401, detail="token subject is not a uuid") from e


def current_user(authorization: str | None = Header(default=None)) -> UUID | None:
    """FastAPI dependency → the authenticated user id, or None in anon dev mode.

    - A present `Authorization: Bearer <jwt>` is always verified (401 if invalid).
    - No token: 401 when `require_auth` is on, else None (anonymous).
    """
    if authorization and authorization.lower().startswith("bearer "):
        return _decode(authorization.split(" ", 1)[1].strip())
    if settings.require_auth:
        raise HTTPException(status_code=401, detail="authentication required")
    return None


def is_member(conn: psycopg.Connection, user_id: UUID, household_id: UUID) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "select 1 from household_members where household_id = %s and user_id = %s",
            (household_id, user_id),
        )
        return cur.fetchone() is not None


def require_membership(
    conn: psycopg.Connection, user_id: UUID | None, household_id: UUID
) -> None:
    """Authorize a household-scoped action. No-op for anonymous (auth disabled)."""
    if user_id is None:
        return
    if not is_member(conn, user_id, household_id):
        raise HTTPException(status_code=403, detail="not a member of this household")
