from config import get_settings
from services.llm import summarize_conversation
from services.supabase_db import (
    count_messages_since_summary,
    get_chat_summary,
    load_recent_messages,
    save_chat_summary,
)


INTENT_CONTEXT_MESSAGES = 6


def thread_id_for_phone(phone: str) -> str:
    return f"whatsapp:{phone}"


def _summary_with_recent_context(summary: str, recent_messages: list[dict]) -> str:
    # The latest user message is already stored before load_memory() runs.
    # Exclude it here because classify_intent() receives it separately.
    previous_messages = recent_messages[:-1][-INTENT_CONTEXT_MESSAGES:]
    if not previous_messages:
        return summary

    history = "\n".join(f"{message['role']}: {message['content']}" for message in previous_messages)
    recent_context = f"Recent conversation before the latest user message:\n{history}"
    if not summary:
        return recent_context
    return f"{summary}\n\n{recent_context}"


async def load_memory(thread_id: str) -> tuple[str, list[dict]]:
    settings = get_settings()
    summary = await get_chat_summary(thread_id)
    recent_messages = await load_recent_messages(thread_id, settings.max_raw_messages)
    return _summary_with_recent_context(summary, recent_messages), recent_messages


async def maybe_summarize(thread_id: str, user_id: str) -> None:
    settings = get_settings()
    pending_count = await count_messages_since_summary(thread_id)
    if pending_count < settings.summary_trigger_messages:
        return

    existing_summary = await get_chat_summary(thread_id)
    messages = await load_recent_messages(thread_id, settings.summary_trigger_messages)
    updated_summary = await summarize_conversation(existing_summary, messages)
    await save_chat_summary(thread_id, user_id, updated_summary)
