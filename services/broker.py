from typing import Any

import httpx

from config import get_settings
from services.crypto import decrypt_secret
from services.supabase_db import get_supabase


class ZerodhaClient:
    def __init__(self, access_token: str):
        settings = get_settings()
        self.api_key = settings.zerodha_api_key
        self.access_token = access_token
        self.headers = {
            "X-Kite-Version": "3",
            "Authorization": f"token {self.api_key}:{self.access_token}",
        }

    async def holdings(self) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get("https://api.kite.trade/portfolio/holdings", headers=self.headers)
            response.raise_for_status()
            return response.json().get("data", [])

    async def positions(self) -> dict[str, list[dict[str, Any]]]:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get("https://api.kite.trade/portfolio/positions", headers=self.headers)
            response.raise_for_status()
            return response.json().get("data", {"net": [], "day": []})

    async def ltp(self, instruments: list[str]) -> dict[str, Any]:
        params = [("i", item) for item in instruments]
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                "https://api.kite.trade/quote/ltp",
                headers=self.headers,
                params=params,
            )
            response.raise_for_status()
            return response.json().get("data", {})


async def get_portfolio_summary(user_id: str) -> dict[str, Any]:
    db = get_supabase()
    account = (
        db.table("broker_accounts")
        .select("id, access_token_ciphertext")
        .eq("user_id", user_id)
        .eq("broker", "zerodha")
        .eq("is_active", True)
        .maybe_single()
        .execute()
    )
    ciphertext = (account.data or {}).get("access_token_ciphertext")
    if ciphertext:
        try:
            client = ZerodhaClient(decrypt_secret(ciphertext))
            holdings = await client.holdings()
            positions = await client.positions()
            return _summarize_portfolio(holdings, positions)
        except Exception:
            pass

    result = (
        db.table("holdings_snapshots")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        return {"status": "not_connected", "message": "Zerodha account is not connected yet."}
    return result.data[0].get("summary", {})


async def get_current_price(user_id: str, symbol: str, exchange: str = "NSE") -> dict[str, Any]:
    db = get_supabase()
    account = (
        db.table("broker_accounts")
        .select("access_token_ciphertext")
        .eq("user_id", user_id)
        .eq("broker", "zerodha")
        .eq("is_active", True)
        .maybe_single()
        .execute()
    )
    ciphertext = (account.data or {}).get("access_token_ciphertext")
    if not ciphertext:
        return {"status": "not_connected", "message": "Zerodha account is not connected yet."}

    instrument = f"{exchange}:{symbol.upper()}"
    client = ZerodhaClient(decrypt_secret(ciphertext))
    data = await client.ltp([instrument])
    return {"status": "ok", "instrument": instrument, "price": data.get(instrument, {}).get("last_price")}


async def sync_portfolio_snapshots() -> None:
    db = get_supabase()
    accounts = db.table("broker_accounts").select("*").eq("broker", "zerodha").eq("is_active", True).execute()
    for account in accounts.data or []:
        ciphertext = account.get("access_token_ciphertext")
        if not ciphertext:
            continue
        token = decrypt_secret(ciphertext)
        client = ZerodhaClient(token)
        holdings = await client.holdings()
        positions = await client.positions()
        summary = _summarize_portfolio(holdings, positions)
        db.table("holdings_snapshots").insert(
            {
                "user_id": account["user_id"],
                "broker_account_id": account["id"],
                "raw_holdings": holdings,
                "summary": summary,
            }
        ).execute()


def _summarize_portfolio(holdings: list[dict[str, Any]], positions: dict[str, list[dict[str, Any]]] | None = None) -> dict[str, Any]:
    total_invested = 0.0
    total_current = 0.0
    holding_rows = []

    for item in holdings:
        quantity = float(item.get("quantity") or 0)
        average_price = float(item.get("average_price") or 0)
        last_price = float(item.get("last_price") or 0)
        invested = quantity * average_price
        current = quantity * last_price
        total_invested += invested
        total_current += current
        holding_rows.append(
            {
                "symbol": item.get("tradingsymbol"),
                "exchange": item.get("exchange"),
                "quantity": quantity,
                "average_price": average_price,
                "last_price": last_price,
                "pnl": current - invested,
            }
        )

    net_positions = _summarize_positions((positions or {}).get("net") or [], include_closed=False)
    day_positions = _summarize_positions((positions or {}).get("day") or [], include_closed=True)
    total_position_pnl = sum(float(item.get("pnl") or 0) for item in net_positions)

    return {
        "broker": "zerodha",
        "total_invested": total_invested,
        "total_current": total_current,
        "total_pnl": total_current - total_invested,
        "total_position_pnl": total_position_pnl,
        "holdings": holding_rows,
        "positions": net_positions,
        "day_positions": day_positions,
    }


def _summarize_positions(positions: list[dict[str, Any]], include_closed: bool) -> list[dict[str, Any]]:
    rows = []
    for item in positions:
        quantity = float(item.get("quantity") or 0)
        day_buy_quantity = float(item.get("day_buy_quantity") or item.get("buy_quantity") or 0)
        day_sell_quantity = float(item.get("day_sell_quantity") or item.get("sell_quantity") or 0)
        if not include_closed and quantity == 0:
            continue
        if include_closed and quantity == 0 and day_buy_quantity == 0 and day_sell_quantity == 0:
            continue

        rows.append(
            {
                "symbol": item.get("tradingsymbol"),
                "exchange": item.get("exchange"),
                "product": item.get("product"),
                "quantity": quantity,
                "average_price": float(item.get("average_price") or 0),
                "last_price": float(item.get("last_price") or 0),
                "pnl": float(item.get("pnl") or 0),
                "day_buy_quantity": day_buy_quantity,
                "day_sell_quantity": day_sell_quantity,
            }
        )
    return rows
