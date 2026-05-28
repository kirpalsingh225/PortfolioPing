from typing import Any

import httpx

from config import get_settings


async def search_web(query: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.tavily_api_key or settings.tavily_api_key.startswith("dummy-"):
        return {"status": "disabled", "query": query, "results": []}

    payload = {
        "api_key": settings.tavily_api_key,
        "query": query,
        "max_results": 5,
        "search_depth": "basic",
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

    return _normalize_tavily_response(query, raw)


def _normalize_tavily_response(query: str, raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {"status": "ok", "query": query, "answer": str(raw), "results": []}

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
        "answer": raw.get("answer"),
        "results": results[:5],
    }
