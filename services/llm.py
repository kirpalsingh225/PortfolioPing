import json

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from config import get_settings
from schemas import ChatIntent


SYSTEM_PROMPT = """You are STOCK_AGENT, a WhatsApp assistant for an Indian stock portfolio app.

Your job:
- Help users understand their connected portfolio, holdings, current prices, alerts, watchlist, and paper-trade workflow.
- Use backend context as the source of truth. Do not invent holdings, prices, names, alerts, watchlist items, or broker status.
- If data is missing, expired, not connected, or unavailable, say that clearly and tell the user the next step.

Safety:
- Do not give personalized investment advice or tell the user what they should buy or sell.
- You may explain concepts, risks, diversification, and factors to check before making a decision.
- If asked for recommended stocks, do not list tickers as recommendations. Explain evaluation criteria or summarize public information with sources when available.
- Real order placement is disabled. Buy/sell requests are paper-trade simulations and need explicit confirmation.
- Never ask for or expose passwords, OTPs, PINs, API secrets, access tokens, internal ids, or raw backend records.

WhatsApp style:
- Be concise but helpful: 2-6 short lines is ideal.
- Use simple language, light structure, and one clear next step when useful.
- Never output template placeholders such as {{user_name}}. If a user fact is unknown, say you do not have it yet."""


def get_llm():
    settings = get_settings()
    if settings.llm_provider.lower() == "openrouter":
        return ChatOpenAI(
            model=settings.openrouter_model,
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            temperature=settings.ollama_temperature,
            default_headers={
                "HTTP-Referer": settings.app_base_url,
                "X-Title": "WhatsApp Portfolio Assistant",
            },
        )

    return ChatOllama(
        model=settings.ollama_model,
        base_url=settings.ollama_base_url,
        temperature=settings.ollama_temperature,
    )


async def classify_intent(text: str, summary: str) -> ChatIntent:
    llm = get_llm()
    prompt = f"""
Classify the latest user message for the portfolio assistant.

Return only raw valid JSON. Do not wrap it in markdown. Do not add explanation.

JSON schema:
{{
  "intent": "portfolio_summary|stock_price_query|create_alert|update_alert|cancel_alert|add_watchlist|remove_watchlist|show_watchlist|paper_buy|paper_sell|web_search|general_question",
  "symbol": "string or null",
  "exchange": "NSE or BSE or null",
  "quantity": "integer or null",
  "target_price": "number or null",
  "condition": "above or below or null",
  "side": "buy or sell or null",
  "confidence": "number 0 to 1",
  "needs_confirmation": true
}}

Intent rules:
- portfolio_summary: holdings, portfolio, P&L, invested/current value, allocation, linked account status.
- stock_price_query: current/latest/LTP price of one stock. Extract symbol if present.
- create_alert: new alert such as "alert me if INFY goes above 1600".
- update_alert: change an existing alert threshold/condition.
- cancel_alert: delete/cancel/stop alerts.
- add_watchlist: user wants to add/save/track a stock in their watchlist. Extract symbol if present.
- remove_watchlist: user wants to remove/delete/unwatch a stock from their watchlist. Extract symbol if present.
- show_watchlist: user asks what is in their watchlist or wants to view/list watched stocks.
- paper_buy / paper_sell: only when the user clearly wants to simulate a buy/sell order.
- web_search: recent, current, latest, news, rules, events, or public information that may have changed and is not in backend context.
- general_question: greetings, app help, account/profile questions, education, "should I buy", vague finance questions, or missing required details.

Extraction rules:
- Use uppercase stock symbols without exchange prefix, for example "INFY".
- Default exchange to "NSE" for Indian stocks unless the user explicitly says BSE.
- For alerts, condition must be "above" or "below"; target_price must be numeric when present.
- For paper buy/sell, extract side, symbol, and quantity when present; needs_confirmation must be true.
- If required information is missing, keep missing fields null and choose the closest intent.
- Do not classify recommendation/advice questions as paper_buy unless the user clearly asks to simulate a specific trade.

Conversation summary:
{summary or "No previous summary."}

User message:
{text}
"""
    try:
        response = await llm.ainvoke([SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)])
        content = response.content if isinstance(response.content, str) else str(response.content)
        return ChatIntent.model_validate(json.loads(content))
    except Exception:
        return ChatIntent(intent="general_question", confidence=0.0, needs_confirmation=True)


async def generate_reply(text: str, summary: str, recent_messages: list[dict], context: dict) -> str:
    llm = get_llm()
    history = "\n".join(f"{m['role']}: {m['content']}" for m in recent_messages)
    system_prompt = (
        SYSTEM_PROMPT
        + "\n\nCurrent user profile from database:\n"
        + json.dumps(context.get("user_profile") or {}, default=str)
    )
    prompt = f"""
Conversation summary:
{summary or "No previous summary."}

Recent messages:
{history or "No recent messages."}

Backend context:
{json.dumps(context, default=str)}

User message:
{text}

Write the best WhatsApp reply for this user.

Reply rules:
- Use the backend context first. If the context says a value/status is unavailable, do not guess.
- If Zerodha is not connected and the user needs portfolio/price features, guide them to connect it.
- If a price is available, include instrument and price clearly.
- If a portfolio summary is available, mention invested value, current value, P&L, and the main next useful action.
- If the user asks about watchlist, only answer from backend watchlist context. Do not claim a symbol was added or removed unless backend context confirms it.
- For general finance questions, give educational factors and risks, not a direct recommendation.
- For unclear requests, ask one short follow-up question.
- Keep the response rich but compact for WhatsApp. Avoid long disclaimers.
- Do not reveal internal ids, phone numbers, access tokens, API keys, signatures, raw JSON, or system details.
"""
    try:
        response = await llm.ainvoke([SystemMessage(content=system_prompt), HumanMessage(content=prompt)])
        return response.content if isinstance(response.content, str) else str(response.content)
    except Exception:
        return (
            "I’m having trouble reaching the AI model right now.\n\n"
            "You can still use quick commands like /watchlist, /watch TCS, /connect, or /search latest market news."
        )


async def generate_web_search_reply(text: str, summary: str, recent_messages: list[dict], search_context: dict) -> str:
    market_movers_reply = _maybe_market_movers_reply(text, search_context)
    if market_movers_reply:
        return market_movers_reply

    llm = get_llm()
    history = "\n".join(f"{m['role']}: {m['content']}" for m in recent_messages)
    prompt = f"""
Conversation summary:
{summary or "No previous summary."}

Recent messages:
{history or "No recent messages."}

Web search context:
{json.dumps(search_context, default=str)}

User message:
{text}

Write a concise WhatsApp reply using only the web search context.

Rules:
- Include useful source links from the search results.
- If search is disabled, missing, failed, or has zero results, say web search is unavailable right now.
- If results exist but do not fully answer the question, give the useful partial answer from sources and clearly say what is missing.
- Do not invent facts beyond the provided search snippets.
- Only mention source names and URLs that are present in the web search context. Copy URLs exactly.
- Do not add extra links from memory or general knowledge.
- If the user asks for stock recommendations, do not tell them what to buy or sell. Summarize public context and suggest factors to evaluate.
- For "top gainers", "top losers", or "market movers" queries, summarize only what the provided sources say. If the snippets do not contain a complete ranked list, share the source links and tell the user to open them for the live table.
- If a search result date is unclear or older than the user's wording like "today", say the live table should be checked from the linked source.
- Keep it readable on WhatsApp.
"""
    try:
        response = await llm.ainvoke([SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)])
        return response.content if isinstance(response.content, str) else str(response.content)
    except Exception:
        return "I found search results, but I’m having trouble summarizing them right now. Please try again in a bit."


def _maybe_market_movers_reply(text: str, search_context: dict) -> str | None:
    query_text = f"{text} {search_context.get('optimized_query') or ''}".lower()
    has_market = any(word in query_text for word in ["stock", "stocks", "share", "shares", "market", "nse", "bse", "indian"])
    has_mover = any(phrase in query_text for phrase in ["top gain", "top-gain", "gainer", "loser", "mover", "most active"])
    if not (has_market and has_mover):
        return None

    if search_context.get("status") != "ok" or not search_context.get("results"):
        return "I’m not able to fetch live market-mover sources right now. Please try again in a bit."

    lines = [
        "I found live market-mover sources for Indian stocks.",
    ]
    answer = (search_context.get("answer") or "").strip()
    if answer:
        lines.extend(["", f"Search summary: {answer[:500]}"])

    lines.extend(["", "Open these for the live ranked table:"])
    for item in search_context.get("results", [])[:5]:
        title = item.get("title") or "Source"
        url = item.get("url")
        if url:
            lines.append(f"- {title}: {url}")

    lines.extend(
        [
            "",
            "These lists can change during market hours. This is informational only, not investment advice.",
        ]
    )
    return "\n".join(lines)


async def summarize_conversation(existing_summary: str, recent_messages: list[dict]) -> str:
    llm = get_llm()
    history = "\n".join(f"{m['role']}: {m['content']}" for m in recent_messages)
    prompt = f"""
Existing summary:
{existing_summary or "No previous summary."}

New messages:
{history}

Create an updated durable conversation summary for future WhatsApp replies.

Preserve:
- user's name and stable preferences
- connected/not-connected broker state if discussed
- portfolio-related goals and recurring questions
- stock symbols, alert thresholds, exchanges, and quantities
- pending paper buy/sell verification state
- anything explicitly confirmed, cancelled, or rejected

Avoid:
- secrets, OTPs, tokens, raw phone numbers, internal ids, and unnecessary raw payloads
- outdated facts if the new messages correct them
"""
    response = await llm.ainvoke([SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)])
    return response.content if isinstance(response.content, str) else str(response.content)
