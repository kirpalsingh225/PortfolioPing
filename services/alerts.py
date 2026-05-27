from typing import Any

from services.broker import ZerodhaClient
from services.crypto import decrypt_secret
from services.supabase_db import create_audit_event, get_supabase
from services.whatsapp import send_whatsapp_text


async def create_price_alert(
    user_id: str,
    symbol: str,
    exchange: str,
    condition: str,
    target_price: float,
) -> dict[str, Any]:
    db = get_supabase()
    account = (
        db.table("broker_accounts")
        .select("id")
        .eq("user_id", user_id)
        .eq("broker", "zerodha")
        .eq("is_active", True)
        .maybe_single()
        .execute()
    )
    result = db.table("alerts").insert(
        {
            "user_id": user_id,
            "broker_account_id": (account.data or {}).get("id"),
            "symbol": symbol.upper(),
            "exchange": exchange.upper(),
            "condition": condition,
            "target_price": target_price,
            "enabled": True,
        }
    ).execute()
    alert = result.data[0]
    await create_audit_event(user_id, "alert_created", {"alert_id": alert["id"]})
    return alert


async def cancel_price_alerts(user_id: str, symbol: str | None) -> int:
    db = get_supabase()
    query = db.table("alerts").update({"enabled": False}).eq("user_id", user_id).eq("enabled", True)
    if symbol:
        query = query.eq("symbol", symbol.upper())
    result = query.execute()
    count = len(result.data or [])
    await create_audit_event(user_id, "alerts_cancelled", {"symbol": symbol, "count": count})
    return count


async def check_due_alerts() -> None:
    db = get_supabase()
    alerts = db.table("alerts").select("*, users(phone), broker_accounts(access_token_ciphertext)").eq("enabled", True).execute()

    for alert in alerts.data or []:
        ciphertext = (alert.get("broker_accounts") or {}).get("access_token_ciphertext")
        phone = (alert.get("users") or {}).get("phone")
        if not ciphertext or not phone:
            continue

        token = decrypt_secret(ciphertext)
        client = ZerodhaClient(token)
        instrument = f"{alert.get('exchange', 'NSE')}:{alert['symbol']}"
        prices = await client.ltp([instrument])
        price = _extract_ltp(prices.get(instrument))
        if price is None or not _is_triggered(alert, price):
            continue

        await send_whatsapp_text(
            phone,
            f"Price alert: {instrument} is now {price}. Your alert condition was {alert['condition']} {alert['target_price']}.",
        )
        db.table("alerts").update({"enabled": False, "last_triggered_price": price}).eq("id", alert["id"]).execute()
        await create_audit_event(alert["user_id"], "alert_triggered", {"alert_id": alert["id"], "price": price})


def _extract_ltp(payload: dict[str, Any] | None) -> float | None:
    if not payload:
        return None
    value = payload.get("last_price")
    return float(value) if value is not None else None


def _is_triggered(alert: dict[str, Any], price: float) -> bool:
    target = float(alert["target_price"])
    condition = alert["condition"]
    if condition == "above":
        return price >= target
    if condition == "below":
        return price <= target
    return False
