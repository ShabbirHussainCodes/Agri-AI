"""Verify Supabase-issued user JWTs against the project's JWKS (public
key) endpoint. We never issue tokens ourselves — Supabase Auth does that
on signup/login; this module only checks that a token presented to us is
genuine, unexpired, and extracts who it belongs to.

Tokens are ES256-signed (asymmetric) — verified with a public key, not a
shared secret, matching both local Supabase and the real agriai-db
project (different URLs, same mechanism).
"""
import jwt
from fastapi.concurrency import run_in_threadpool
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

bearer_scheme = HTTPBearer(auto_error=False)

# One client, created once, reused for every request. It fetches
# /.well-known/jwks.json and caches the public keys by `kid` — so most
# requests never touch the network at all, only the first one (or one
# after Supabase rotates its signing key) does.
_jwk_client = jwt.PyJWKClient(settings.jwks_url, cache_keys=True)


class AuthContext:
    """What we trust about the caller once verification succeeds.

    user_id is the same UUID as profiles.id and auth.uid() in Postgres.
    claims is the full decoded token — we forward it to Postgres as-is
    (see db.get_authed_conn) so RLS policies evaluate the real thing,
    not our own re-interpretation of it.
    """

    def __init__(self, user_id: str, claims: dict):
        self.user_id = user_id
        self.claims = claims


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> AuthContext:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")

    token = credentials.credentials
    try:
        # PyJWKClient does a (possibly-blocking) HTTP call on a cache miss,
        # so it runs off the event loop rather than stalling other requests.
        signing_key = await run_in_threadpool(_jwk_client.get_signing_key_from_jwt, token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256"],
            audience=settings.jwt_audience,
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid token: {e}")

    sub = claims.get("sub")
    if not sub:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token missing 'sub' claim")

    return AuthContext(user_id=sub, claims=claims)
