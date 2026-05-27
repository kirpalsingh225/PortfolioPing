from cryptography.fernet import Fernet

from config import get_settings


def encrypt_secret(value: str) -> str:
    settings = get_settings()
    key = settings.token_encryption_key
    if key.startswith("dummy-"):
        if settings.app_env == "production":
            raise RuntimeError("TOKEN_ENCRYPTION_KEY must be configured in production")
        return f"plain:{value}"
    return Fernet(key.encode()).encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    settings = get_settings()
    if value.startswith("plain:") and settings.app_env != "production":
        return value.removeprefix("plain:")
    key = settings.token_encryption_key
    if key.startswith("dummy-"):
        raise RuntimeError("TOKEN_ENCRYPTION_KEY must be configured")
    return Fernet(key.encode()).decrypt(value.encode()).decode()
