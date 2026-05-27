import hashlib
import hmac

from config import get_settings


def verify_meta_signature(body: bytes, signature: str | None) -> bool:
    settings = get_settings()
    secret = settings.whatsapp_app_secret

    if settings.app_env != "production" and secret.startswith("dummy-"):
        return True
    if not secret or secret.startswith("dummy-") or not signature:
        return False
    if not signature.startswith("sha256="):
        return False

    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def sign_state(value: str) -> str:
    settings = get_settings()
    digest = hmac.new(settings.api_secret.encode(), value.encode(), hashlib.sha256).hexdigest()
    return f"{value}.{digest}"


def verify_signed_state(state: str) -> str:
    value, _, digest = state.rpartition(".")
    if not value or not digest:
        raise ValueError("Invalid state")
    expected = sign_state(value).rpartition(".")[2]
    if not hmac.compare_digest(expected, digest):
        raise ValueError("Invalid state signature")
    return value
