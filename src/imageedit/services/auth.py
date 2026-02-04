"""Token helpers for imageedit API authentication."""

from __future__ import annotations

import secrets
from typing import Any

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

_TOKEN_SALT = "imageedit-api-token"  # noqa: S105


def issue_api_token(secret: str, *, subject: str) -> str:
    serializer = URLSafeTimedSerializer(secret, salt=_TOKEN_SALT)
    return serializer.dumps({"sub": subject, "scope": "api"})


def verify_api_token(
    token: str, secret: str, *, max_age: int
) -> tuple[dict[str, Any] | None, str | None]:
    serializer = URLSafeTimedSerializer(secret, salt=_TOKEN_SALT)
    try:
        data = serializer.loads(token, max_age=max_age)
    except SignatureExpired:
        return None, "expired"
    except BadSignature:
        return None, "invalid"

    if not isinstance(data, dict) or data.get("scope") != "api":
        return None, "invalid"

    return data, None


def issuer_key_matches(candidate: str | None, expected: str) -> bool:
    if not candidate:
        return False
    return secrets.compare_digest(candidate, expected)
