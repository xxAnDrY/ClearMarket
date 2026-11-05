"""Genera il JWT usato dall'app quando non c'e' Supabase.

Uso: `python scripts/mint_dev_token.py [--days 30]` (legge JWT_SECRET dall'ambiente o da .env).
Tutte le copie dell'app con questo token condividono la stessa watchlist: va bene per uso
personale, non per un'app pubblica. Rifiuta di partire se e' configurato JWT_JWKS_URL.
"""
import argparse
import time
import uuid

import jwt

from app.config import get_settings

DAY_S = 86_400


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()

    settings = get_settings()
    if settings.jwt_jwks_url or not settings.jwt_secret:
        raise SystemExit("Serve JWT_SECRET senza JWT_JWKS_URL")
    claims = {"sub": str(uuid.uuid4()), "aud": settings.jwt_audience,
              "exp": int(time.time()) + args.days * DAY_S}
    print(jwt.encode(claims, settings.jwt_secret, algorithm="HS256"))


if __name__ == "__main__":
    main()
