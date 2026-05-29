from config import get_settings
from schemas import PaperOrderDraft, WhatsAppIncomingMessage
from services.alerts import cancel_price_alerts, create_price_alert
from services.broker import get_current_price, get_portfolio_summary
from services.llm import classify_intent, generate_reply, generate_web_search_reply
from services.memory import load_memory, maybe_summarize, thread_id_for_phone
from services.orders import create_paper_order
from services.supabase_db import (
    accept_user_onboarding,
    add_watchlist_item,
    clear_pending_action,
    create_audit_event,
    get_active_broker_account,
    get_user_profile,
    get_pending_action,
    list_watchlist_items,
    remove_watchlist_item,
    save_chat_message,
    save_pending_action,
    update_user_name,
    upsert_user_by_phone,
)
from services.web_search import search_web
from services.whatsapp import send_whatsapp_text
from services.zerodha_auth import build_login_url


async def handle_whatsapp_message(message: WhatsAppIncomingMessage) -> None:
    user = await upsert_user_by_phone(message.from_phone, message.profile_name)
    user_id = user["id"]
    thread_id = thread_id_for_phone(message.from_phone)

    await save_chat_message(
        thread_id=thread_id,
        user_id=user_id,
        role="user",
        content=message.text,
        metadata={"message_id": message.message_id},
    )

    onboarding_reply = await _maybe_handle_onboarding(user_id, message.text)
    if onboarding_reply:
        await save_chat_message(thread_id=thread_id, user_id=user_id, role="assistant", content=onboarding_reply)
        await send_whatsapp_text(message.from_phone, onboarding_reply)
        await create_audit_event(user_id, "onboarding_message", {"text": message.text})
        await maybe_summarize(thread_id, user_id)
        return

    command_reply = await _maybe_handle_command(user_id, thread_id, message.text)
    if command_reply:
        await save_chat_message(thread_id=thread_id, user_id=user_id, role="assistant", content=command_reply)
        await send_whatsapp_text(message.from_phone, command_reply)
        await maybe_summarize(thread_id, user_id)
        return

    pending_reply = await _maybe_handle_pending_action(user_id, thread_id, message.text)
    if pending_reply:
        await save_chat_message(thread_id=thread_id, user_id=user_id, role="assistant", content=pending_reply)
        await send_whatsapp_text(message.from_phone, pending_reply)
        await maybe_summarize(thread_id, user_id)
        return

    name_reply = await _maybe_save_user_name(user_id, message.text)
    if name_reply:
        await save_chat_message(thread_id=thread_id, user_id=user_id, role="assistant", content=name_reply)
        await send_whatsapp_text(message.from_phone, name_reply)
        await maybe_summarize(thread_id, user_id)
        return

    profile_reply = await _maybe_direct_profile_question(user_id, message.text)
    if profile_reply:
        await save_chat_message(thread_id=thread_id, user_id=user_id, role="assistant", content=profile_reply)
        await send_whatsapp_text(message.from_phone, profile_reply)
        await maybe_summarize(thread_id, user_id)
        return

    summary, recent_messages = await load_memory(thread_id)
    intent = await classify_intent(message.text, summary)
    direct_reply = await _maybe_handle_alert_intent(user_id, intent)
    if direct_reply:
        await save_chat_message(thread_id=thread_id, user_id=user_id, role="assistant", content=direct_reply)
        await send_whatsapp_text(message.from_phone, direct_reply)
        await create_audit_event(user_id, "whatsapp_message_processed", {"intent": intent.model_dump()})
        await maybe_summarize(thread_id, user_id)
        return

    watchlist_reply = await _maybe_handle_watchlist_intent(user_id, intent)
    if watchlist_reply:
        await save_chat_message(thread_id=thread_id, user_id=user_id, role="assistant", content=watchlist_reply)
        await send_whatsapp_text(message.from_phone, watchlist_reply)
        await create_audit_event(user_id, "whatsapp_message_processed", {"intent": intent.model_dump()})
        await maybe_summarize(thread_id, user_id)
        return

    if intent.intent == "web_search":
        search_context = await search_web(message.text)
        reply = await generate_web_search_reply(message.text, summary, recent_messages, search_context)
        await save_chat_message(thread_id=thread_id, user_id=user_id, role="assistant", content=reply)
        await send_whatsapp_text(message.from_phone, reply)
        await create_audit_event(user_id, "web_search_answered", {"query": message.text, "status": search_context.get("status")})
        await maybe_summarize(thread_id, user_id)
        return

    context = await _build_backend_context(user_id, intent, message.text)
    reply = _deterministic_reply(intent, context)
    if reply is None:
        reply = await generate_reply(message.text, summary, recent_messages, context)

    if intent.intent in {"paper_buy", "paper_sell"}:
        reply = await _handle_paper_trade(user_id, thread_id, intent)

    await save_chat_message(thread_id=thread_id, user_id=user_id, role="assistant", content=reply)
    await send_whatsapp_text(message.from_phone, reply)
    await create_audit_event(user_id, "whatsapp_message_processed", {"intent": intent.model_dump()})
    await maybe_summarize(thread_id, user_id)


async def _build_backend_context(user_id: str, intent, text: str) -> dict:
    user_profile = await get_user_profile(user_id)
    broker_account = await get_active_broker_account(user_id)
    base_context = {
        "assistant_mode": "whatsapp_portfolio_assistant",
        "user_profile": _llm_user_profile(user_profile),
        "broker": _llm_broker_context(broker_account),
        "intent": intent.model_dump(),
        "zerodha_connect_url": build_login_url(user_id),
        "user_message": text,
        "available_actions": [
            "answer_general_question",
            "show_portfolio_if_connected",
            "fetch_stock_price_if_connected",
            "create_or_cancel_price_alert",
            "add_remove_or_show_watchlist_items",
            "simulate_paper_trade_with_confirmation",
            "search_web_for_current_public_information",
        ],
        "important_limits": [
            "not_investment_advice",
            "real_order_placement_disabled",
            "do_not_request_passwords_otps_or_api_keys",
        ],
    }

    if intent.intent == "portfolio_summary":
        base_context["portfolio"] = await get_portfolio_summary(user_id)
        return base_context
    if intent.intent == "stock_price_query" and intent.symbol:
        base_context["price"] = await get_current_price(user_id, intent.symbol, intent.exchange or "NSE")
        return base_context
    return base_context


def _llm_user_profile(user_profile: dict) -> dict:
    return {
        "name": user_profile.get("name"),
        "whatsapp_opted_in": bool(user_profile.get("whatsapp_opted_in")),
        "terms_accepted": bool(user_profile.get("terms_accepted_at")),
        "privacy_accepted": bool(user_profile.get("privacy_accepted_at")),
    }


def _llm_broker_context(broker_account: dict | None) -> dict:
    if not broker_account:
        return {
            "provider": "zerodha",
            "connected": False,
            "message": "Zerodha account is not connected.",
        }
    return {
        "provider": broker_account.get("broker") or "zerodha",
        "connected": True,
        "broker_user_id": broker_account.get("broker_user_id"),
    }


async def _maybe_handle_onboarding(user_id: str, text: str) -> str | None:
    normalized = text.strip().lower()
    user_profile = await get_user_profile(user_id)

    if normalized in {"agree", "i agree", "yes i agree", "accept", "i accept"}:
        await accept_user_onboarding(user_id)
        connect_url = build_login_url(user_id)
        return (
            "Thanks. You’re opted in for WhatsApp updates from this portfolio assistant.\n\n"
            "Next, connect Zerodha securely:\n"
            f"{connect_url}\n\n"
            "We use Zerodha only to read your account/portfolio data for this assistant. "
            "Real order placement is disabled in this prototype."
        )

    if not user_profile.get("whatsapp_opted_in"):
        settings = get_settings()
        return (
            "Welcome to the WhatsApp Portfolio Assistant.\n\n"
            "Before we continue, please review:\n"
            f"Privacy: {settings.app_base_url}/legal/privacy\n"
            f"Terms: {settings.app_base_url}/legal/terms\n\n"
            "Reply AGREE to opt in to WhatsApp messages and continue. "
            "This bot is for portfolio information and alerts only, not investment advice."
        )

    broker = await get_active_broker_account(user_id)
    wants_portfolio = any(word in normalized for word in ["portfolio", "holding", "holdings", "zerodha", "connect"])
    if not broker and wants_portfolio:
        return (
            "Your Zerodha account is not linked yet.\n\n"
            "Connect it securely here:\n"
            f"{build_login_url(user_id)}\n\n"
            "After linking, ask: show my portfolio."
        )

    return None


async def _maybe_handle_command(user_id: str, thread_id: str, text: str) -> str | None:
    normalized = text.strip().lower()
    if normalized.startswith("/search"):
        query = text.strip()[len("/search") :].strip()
        if not query:
            return "Send it like: /search latest news about INFY"
        summary, recent_messages = await load_memory(thread_id)
        search_context = await search_web(query)
        return await generate_web_search_reply(query, summary, recent_messages, search_context)

    if normalized == "/watchlist":
        return await _format_watchlist(user_id)

    if normalized.startswith("/watch "):
        symbol, exchange = _parse_watch_command(text)
        if not symbol:
            return "Send it like: /watch TCS"
        return await _add_watchlist_symbol(user_id, symbol, exchange)

    if normalized.startswith("/unwatch "):
        symbol, exchange = _parse_watch_command(text)
        if not symbol:
            return "Send it like: /unwatch TCS"
        return await _remove_watchlist_symbol(user_id, symbol, exchange)

    if normalized not in {"/connect", "/reconnect", "reconnect zerodha", "connect zerodha"}:
        return None

    if normalized in {"/connect", "/reconnect", "reconnect zerodha", "connect zerodha"}:
        return (
            "Here is your fresh Zerodha connect link:\n"
            f"{build_login_url(user_id)}\n\n"
            "Use this when your Zerodha session expires or you want to reconnect."
        )

    return None


async def _maybe_handle_watchlist_intent(user_id: str, intent) -> str | None:
    if intent.intent == "show_watchlist":
        return await _format_watchlist(user_id)

    if intent.intent == "add_watchlist":
        if not intent.symbol:
            return "Which stock should I add to your watchlist? Send it like: add TCS to watchlist."
        return await _add_watchlist_symbol(user_id, intent.symbol, intent.exchange or "NSE")

    if intent.intent == "remove_watchlist":
        if not intent.symbol:
            return "Which stock should I remove from your watchlist? Send it like: remove TCS from watchlist."
        return await _remove_watchlist_symbol(user_id, intent.symbol, intent.exchange or "NSE")

    return None


async def _add_watchlist_symbol(user_id: str, symbol: str, exchange: str) -> str:
    try:
        item = await add_watchlist_item(user_id, symbol, exchange)
    except Exception:
        return _watchlist_setup_message()
    return f"Added {item['exchange']}:{item['symbol']} to your watchlist."


async def _remove_watchlist_symbol(user_id: str, symbol: str, exchange: str) -> str:
    try:
        count = await remove_watchlist_item(user_id, symbol, exchange)
    except Exception:
        return _watchlist_setup_message()
    if count:
        return f"Removed {exchange}:{symbol.upper()} from your watchlist."
    return f"I couldn’t find {exchange}:{symbol.upper()} in your watchlist."


async def _format_watchlist(user_id: str) -> str:
    try:
        items = await list_watchlist_items(user_id)
    except Exception:
        return _watchlist_setup_message()
    if not items:
        return "Your watchlist is empty. Add one like: add TCS to watchlist."

    lines = ["Your watchlist:"]
    for item in items:
        lines.append(f"- {item['exchange']}:{item['symbol']}")
    return "\n".join(lines)


def _watchlist_setup_message() -> str:
    return "Watchlist storage is not set up yet. Run the latest db/schema.sql in Supabase, then try again."


def _parse_watch_command(text: str) -> tuple[str | None, str]:
    parts = text.strip().split()
    if len(parts) < 2:
        return None, "NSE"
    symbol = parts[1].strip().upper()
    exchange = next((part.upper() for part in parts[2:] if part.upper() in {"NSE", "BSE"}), "NSE")
    return symbol, exchange


async def _maybe_direct_profile_question(user_id: str, text: str) -> str | None:
    normalized = text.lower()
    if "my name" not in normalized:
        return None
    user_profile = await get_user_profile(user_id)
    name = user_profile.get("name")
    if name:
        return f"Your name is {name}."
    return "I don’t have your name saved yet. I only have your WhatsApp number."


async def _maybe_save_user_name(user_id: str, text: str) -> str | None:
    normalized = text.strip()
    lowered = normalized.lower()
    prefixes = ["my name is ", "i am ", "i'm ", "call me "]
    matched_prefix = next((prefix for prefix in prefixes if lowered.startswith(prefix)), None)
    if not matched_prefix:
        return None

    name = normalized[len(matched_prefix) :].strip(" .,!").strip()
    if not name or len(name) > 80:
        return "I couldn’t save that name. Please send it like: my name is Kirpal."

    await update_user_name(user_id, name)
    return f"Got it. I’ll call you {name}."


def _deterministic_reply(intent, context: dict) -> str | None:
    if intent.intent == "general_question":
        return _maybe_user_profile_reply(context)

    if intent.intent != "portfolio_summary":
        return None

    portfolio = context.get("portfolio") or {}
    if portfolio.get("status") == "not_connected":
        return (
            "Your Zerodha account is not linked yet, so I can’t show your holdings.\n\n"
            "Connect it securely here:\n"
            f"{context.get('zerodha_connect_url')}"
        )

    holdings = portfolio.get("holdings") or []
    positions = portfolio.get("positions") or []
    day_positions = portfolio.get("day_positions") or []
    if not holdings and not positions and not day_positions:
        return "Your Zerodha account is linked, but there are no holdings or open positions available right now."

    if not holdings and (positions or day_positions):
        lines = ["No settled holdings yet, but I found Zerodha positions:"]
        for item in (positions or day_positions)[:5]:
            lines.append(
                f"- {item.get('exchange')}:{item.get('symbol')} qty {item.get('quantity')} "
                f"LTP {item.get('last_price')} P&L {item.get('pnl')}"
            )
        return "\n".join(lines)

    return (
        "Portfolio summary:\n"
        f"Invested: {portfolio.get('total_invested', 0)}\n"
        f"Current: {portfolio.get('total_current', 0)}\n"
        f"P&L: {portfolio.get('total_pnl', 0)}\n"
        f"Holdings: {len(holdings)}\n"
        f"Open positions: {len(positions)}"
    )


def _maybe_user_profile_reply(context: dict) -> str | None:
    intent_text = context.get("user_message") or ""
    user_profile = context.get("user_profile") or {}
    if "my name" not in intent_text.lower():
        return None

    name = user_profile.get("name")
    if name:
        return f"Your name is {name}."
    return "I don’t have your name saved yet. I only have your WhatsApp number."


async def _maybe_handle_alert_intent(user_id: str, intent) -> str | None:
    if intent.intent in {"create_alert", "update_alert"}:
        missing = []
        if not intent.symbol:
            missing.append("stock symbol")
        if not intent.condition:
            missing.append("above/below condition")
        if intent.target_price is None:
            missing.append("target price")
        if missing:
            return f"I can create that alert, but I need: {', '.join(missing)}."

        if intent.intent == "update_alert":
            await cancel_price_alerts(user_id, intent.symbol)

        alert = await create_price_alert(
            user_id=user_id,
            symbol=intent.symbol,
            exchange=intent.exchange or "NSE",
            condition=intent.condition,
            target_price=intent.target_price,
        )
        return (
            f"Alert {'updated' if intent.intent == 'update_alert' else 'created'}: {alert['exchange']}:{alert['symbol']} "
            f"{alert['condition']} {alert['target_price']}."
        )

    if intent.intent == "cancel_alert":
        count = await cancel_price_alerts(user_id, intent.symbol)
        if intent.symbol:
            return f"Cancelled {count} active alert(s) for {intent.symbol.upper()}."
        return f"Cancelled {count} active alert(s)."

    return None


async def _maybe_handle_pending_action(user_id: str, thread_id: str, text: str) -> str | None:
    normalized = text.strip().lower()
    pending = await get_pending_action(thread_id, "paper_trade")
    if not pending:
        return None

    if normalized in {"cancel", "no", "stop"}:
        await clear_pending_action(thread_id, "paper_trade", "cancelled")
        return "Cancelled the pending paper trade. No real or paper order was placed."

    if normalized not in {"confirm", "yes confirm", "confirm order"}:
        return None

    draft = PaperOrderDraft(user_id=user_id, **pending["payload"])
    order = await create_paper_order(draft, confirmation_text=text)
    await clear_pending_action(thread_id, "paper_trade", "confirmed")
    return f"Paper order recorded: {order['side'].upper()} {order['quantity']} {order['exchange']}:{order['symbol']}. No real trade was placed."


async def _handle_paper_trade(user_id: str, thread_id: str, intent) -> str:
    missing = []
    if not intent.symbol:
        missing.append("stock symbol")
    if not intent.quantity:
        missing.append("quantity")
    if not intent.side:
        missing.append("buy/sell side")

    if missing:
        return f"I can help with a paper trade, but I still need: {', '.join(missing)}. This will not place a real order."

    draft = PaperOrderDraft(
        user_id=user_id,
        symbol=intent.symbol,
        exchange=intent.exchange or "NSE",
        side=intent.side,
        quantity=intent.quantity,
    )
    await save_pending_action(
        user_id,
        thread_id,
        "paper_trade",
        draft.model_dump(exclude={"user_id"}),
    )
    return (
        f"Please confirm this paper trade: {draft.side.upper()} {draft.quantity} "
        f"{draft.exchange}:{draft.symbol}. Reply with 'confirm' to record it, or 'cancel' to stop. "
        "This will only create a simulated paper order."
    )
