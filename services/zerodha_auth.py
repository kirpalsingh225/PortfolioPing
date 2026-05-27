import hashlib
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException

from config import get_settings
from services.crypto import encrypt_secret
from services.security import sign_state, verify_signed_state
from services.supabase_db import get_supabase


def build_login_url(user_id: str) -> str:
    settings = get_settings()
    params = {
        "api_key": settings.zerodha_api_key,
        "v": "3",
        "redirect_params": urlencode({"state": sign_state(user_id)}),
    }
    return f"https://kite.zerodha.com/connect/login?{urlencode(params)}"


async def exchange_request_token(request_token: str, state: str) -> str:
    settings = get_settings()
    try:
        user_id = verify_signed_state(state)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Invalid auth state") from exc

    checksum = hashlib.sha256(
        f"{settings.zerodha_api_key}{request_token}{settings.zerodha_api_secret}".encode()
    ).hexdigest()
    payload = {
        "api_key": settings.zerodha_api_key,
        "request_token": request_token,
        "checksum": checksum,
    }

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post("https://api.kite.trade/session/token", data=payload)
        response.raise_for_status()
        data = response.json()["data"]

    db = get_supabase()
    db.table("broker_accounts").upsert(
        {
            "user_id": user_id,
            "broker": "zerodha",
            "broker_user_id": data.get("user_id"),
            "access_token_ciphertext": encrypt_secret(data["access_token"]),
            "public_token": data.get("public_token"),
            "is_active": True,
        },
        on_conflict="user_id,broker",
    ).execute()
    return user_id
