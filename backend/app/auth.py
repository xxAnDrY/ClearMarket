"""Verifica del JWT di Supabase Auth (anche per gli utenti anonimi)."""
import asyncio
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import Settings, get_settings

_bearer = HTTPBearer(auto_error=False)
_ASYMMETRIC_ALGORITHMS = ["ES256", "RS256"]


def verify_token(token: str, settings: Settings, jwks: jwt.PyJWKClient | None) -> UUID:
    # L'algoritmo e' fissato dalla configurazione, mai letto dall'header del token.
    if jwks:
        key = jwks.get_signing_key_from_jwt(token).key
        algorithms = _ASYMMETRIC_ALGORITHMS
    elif settings.jwt_secret:
        key, algorithms = settings.jwt_secret, ["HS256"]
    else:
        raise RuntimeError("configure JWT_JWKS_URL or JWT_SECRET")
    claims = jwt.decode(token, key, algorithms=algorithms, audience=settings.jwt_audience,
                        options={"require": ["exp", "sub"]})
    return UUID(claims["sub"])


async def current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> UUID:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    jwks = getattr(request.app.state, "jwks", None)
    try:
        # PyJWKClient fa I/O bloccante quando deve aggiornare le chiavi.
        return await asyncio.to_thread(verify_token, credentials.credentials, settings, jwks)
    except (jwt.PyJWTError, ValueError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token") from exc


CurrentUser = Annotated[UUID, Depends(current_user)]
