import json

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from config import get_settings
from schemas import ChatIntent


SYSTEM_PROMPT = """You are a WhatsApp assistant for an Indian stock portfolio app.
You help users understand their own holdings, prices, alerts, and paper-trading workflow.
Never give personalized financial advice. Do not say a user should buy or sell.
For buy/sell intent, ask verification questions and mark it as requiring confirmation.
Keep responses concise for WhatsApp.
Never output template placeholders such as {{user_name}}. If a user fact is unknown, say you do not have it yet."""


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
Return only valid JSON matching this schema:
{{
  "intent": "portfolio_summary|stock_price_query|create_alert|update_alert|cancel_alert|paper_buy|paper_sell|general_question",
  "symbol": "string or null",
  "exchange": "NSE or BSE or null",
  "quantity": "integer or null",
  "target_price": "number or null",
  "condition": "above or below or null",
  "side": "buy or sell or null",
  "confidence": "number 0 to 1",
  "needs_confirmation": true
}}

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

Write a helpful WhatsApp reply. Keep it short. Do not provide financial advice.
"""
    response = await llm.ainvoke([SystemMessage(content=system_prompt), HumanMessage(content=prompt)])
    return response.content if isinstance(response.content, str) else str(response.content)


async def summarize_conversation(existing_summary: str, recent_messages: list[dict]) -> str:
    llm = get_llm()
    history = "\n".join(f"{m['role']}: {m['content']}" for m in recent_messages)
    prompt = f"""
Existing summary:
{existing_summary or "No previous summary."}

New messages:
{history}

Create an updated durable conversation summary. Preserve:
- user goals and preferences
- stock symbols, alert thresholds, and quantities
- pending paper buy/sell verification state
- anything already confirmed or rejected
"""
    response = await llm.ainvoke([SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)])
    return response.content if isinstance(response.content, str) else str(response.content)
