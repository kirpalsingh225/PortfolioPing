from typing import Any

import httpx

from config import get_settings


async def search_web(query: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.tavily_api_key or settings.tavily_api_key.startswith("dummy-"):
        return {"status": "disabled", "query": query, "results": []}

    optimized_query = _optimize_query(query)
    is_market_movers_query = _looks_like_market_movers_query(query)
    payload = {
        "api_key": settings.tavily_api_key,
        "query": optimized_query,
        "max_results": 8 if is_market_movers_query else 5,
        "search_depth": "advanced" if is_market_movers_query else "basic",
        "include_answer": True,
        "topic": "general",
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post("https://api.tavily.com/search", json=payload)
            response.raise_for_status()
            raw = response.json()
    except Exception as exc:
        return {"status": "error", "query": query, "error": type(exc).__name__, "results": []}

    return _normalize_tavily_response(query, optimized_query, raw)


def _normalize_tavily_response(query: str, optimized_query: str, raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {"status": "ok", "query": query, "optimized_query": optimized_query, "answer": str(raw), "results": []}

    results = []
    for item in raw.get("results") or []:
        if not isinstance(item, dict):
            continue
        title = item.get("title")
        url = item.get("url")
        content = item.get("content") or item.get("raw_content")
        if not url:
            continue
        results.append(
            {
                "title": title or url,
                "url": url,
                "content": (content or "")[:900],
            }
        )

    return {
        "status": "ok",
        "query": query,
        "optimized_query": optimized_query,
        "answer": raw.get("answer"),
        "results": results[:5],
    }


def _optimize_query(query: str) -> str:
    if _looks_like_market_movers_query(query):
        return (
            f"{query} NSE India top gainers today live Indian stock market "
            "NSE official Moneycontrol Economic Times"
        )
    return query


def _looks_like_market_movers_query(query: str) -> bool:
    text = query.lower()
    has_market = any(word in text for word in ["stock", "stocks", "share", "shares", "market", "nse", "bse", "indian"])
    has_mover = any(phrase in text for phrase in ["top gain", "top-gain", "gainer", "loser", "mover", "most active"])
    has_today = any(word in text for word in ["today", "current", "latest", "now", "live"])
    return has_market and has_mover and has_today
