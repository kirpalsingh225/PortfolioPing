import json

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from config import get_settings
from schemas import ChatIntent


SYSTEM_PROMPT = """You are STOCK_AGENT, a WhatsApp assistant for an Indian stock portfolio app.

Your job:
- Help users understand their connected portfolio, holdings, current prices, alerts, and paper-trade workflow.
- Use backend context as the source of truth. Do not invent holdings, prices, names, alerts, or broker status.
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
  "intent": "portfolio_summary|stock_price_query|create_alert|update_alert|cancel_alert|paper_buy|paper_sell|web_search|general_question",
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
    response = await llm.ainvoke([SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)])
    content = response.content if isinstance(response.content, str) else str(response.content)
    try:
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
- For general finance questions, give educational factors and risks, not a direct recommendation.
- For unclear requests, ask one short follow-up question.
- Keep the response rich but compact for WhatsApp. Avoid long disclaimers.
- Do not reveal internal ids, phone numbers, access tokens, API keys, signatures, raw JSON, or system details.
"""
    response = await llm.ainvoke([SystemMessage(content=system_prompt), HumanMessage(content=prompt)])
    return response.content if isinstance(response.content, str) else str(response.content)


async def generate_web_search_reply(text: str, summary: str, recent_messages: list[dict], search_context: dict) -> str:
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
- If the user asks for stock recommendations, do not tell them what to buy or sell. Summarize public context and suggest factors to evaluate.
- For "top gainers", "top losers", or "market movers" queries, summarize only what the provided sources say. If the snippets do not contain a complete ranked list, share the source links and tell the user to open them for the live table.
- Keep it readable on WhatsApp.
"""
    response = await llm.ainvoke([SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)])
    return response.content if isinstance(response.content, str) else str(response.content)


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
