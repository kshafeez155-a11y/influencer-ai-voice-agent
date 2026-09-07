"""Short-lived, IP-bound admission tokens for billable web voice sessions."""

import base64
import hashlib
import hmac
import json
import secrets
import time


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def issue_call_token(
    *, influencer_id: int, client_ip: str, secret: str, lifetime_seconds: int = 120
) -> str:
    payload = {
        "creator": int(influencer_id),
        "ip": client_ip,
        "exp": int(time.time()) + lifetime_seconds,
        "nonce": secrets.token_urlsafe(10),
    }
    encoded = _encode(json.dumps(payload, separators=(",", ":")).encode())
    signature = _encode(
        hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).digest()
    )
    return encoded + "." + signature


def validate_call_token(
    token: str, *, influencer_id: int, client_ip: str, secret: str
) -> bool:
    try:
        encoded, supplied = token.split(".", 1)
        expected = _encode(
            hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(supplied, expected):
            return False
        payload = json.loads(_decode(encoded))
        return (
            int(payload["creator"]) == int(influencer_id)
            and payload["ip"] == client_ip
            and int(payload["exp"]) >= int(time.time())
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return False
