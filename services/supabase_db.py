from typing import Any
from datetime import datetime, timezone

from supabase import Client, create_client

from config import get_settings


def get_supabase() -> Client:
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def _data_or_none(result: Any) -> Any:
    return result.data if result is not None else None


async def upsert_user_by_phone(phone: str, name: str | None = None) -> dict[str, Any]:
    db = get_supabase()
    payload = {"phone": phone}
    if name:
        payload["name"] = name
    try:
        result = db.table("users").upsert(payload, on_conflict="phone").execute()
    except Exception:
        result = db.table("users").upsert({"phone": phone}, on_conflict="phone").execute()
    return result.data[0]


async def get_user_profile(user_id: str) -> dict[str, Any]:
    db = get_supabase()
    try:
        result = (
            db.table("users")
            .select("id, phone, name, whatsapp_opted_in, terms_accepted_at, privacy_accepted_at")
            .eq("id", user_id)
            .single()
            .execute()
        )
    except Exception:
        result = db.table("users").select("id, phone").eq("id", user_id).single().execute()
    return result.data or {}


async def update_user_name(user_id: str, name: str) -> None:
    db = get_supabase()
    db.table("users").update({"name": name}).eq("id", user_id).execute()


async def accept_user_onboarding(user_id: str) -> None:
    db = get_supabase()
    accepted_at = datetime.now(timezone.utc).isoformat()
    db.table("users").update(
        {
            "whatsapp_opted_in": True,
            "terms_accepted_at": accepted_at,
            "privacy_accepted_at": accepted_at,
        }
    ).eq("id", user_id).execute()


async def get_active_broker_account(user_id: str) -> dict[str, Any] | None:
    db = get_supabase()
    result = (
        db.table("broker_accounts")
        .select("id, broker, broker_user_id, is_active")
        .eq("user_id", user_id)
        .eq("broker", "zerodha")
        .eq("is_active", True)
        .maybe_single()
        .execute()
    )
    return _data_or_none(result)


async def save_chat_message(
    thread_id: str,
    user_id: str,
    role: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    db = get_supabase()
    db.table("chat_messages").insert(
        {
            "thread_id": thread_id,
            "user_id": user_id,
            "role": role,
            "content": content,
            "metadata": metadata or {},
        }
    ).execute()


async def load_recent_messages(thread_id: str, limit: int) -> list[dict[str, Any]]:
    db = get_supabase()
    result = (
        db.table("chat_messages")
        .select("role, content, created_at")
        .eq("thread_id", thread_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return list(reversed(result.data or []))


async def count_messages_since_summary(thread_id: str) -> int:
    db = get_supabase()
    summary = (
        db.table("chat_summaries")
        .select("updated_at")
        .eq("thread_id", thread_id)
        .maybe_single()
        .execute()
    )
    query = db.table("chat_messages").select("id", count="exact").eq("thread_id", thread_id)
    summary_data = _data_or_none(summary)
    if summary_data and summary_data.get("updated_at"):
        query = query.gt("created_at", summary_data["updated_at"])
    result = query.execute()
    return result.count or 0


async def get_chat_summary(thread_id: str) -> str:
    db = get_supabase()
    result = (
        db.table("chat_summaries")
        .select("summary")
        .eq("thread_id", thread_id)
        .maybe_single()
        .execute()
    )
    result_data = _data_or_none(result)
    if not result_data:
        return ""
    return result_data.get("summary") or ""


async def save_chat_summary(thread_id: str, user_id: str, summary: str) -> None:
    db = get_supabase()
    db.table("chat_summaries").upsert(
        {"thread_id": thread_id, "user_id": user_id, "summary": summary},
        on_conflict="thread_id",
    ).execute()


async def create_audit_event(user_id: str, event_type: str, payload: dict[str, Any]) -> None:
    db = get_supabase()
    db.table("audit_events").insert(
        {"user_id": user_id, "event_type": event_type, "payload": payload}
    ).execute()


async def save_pending_action(
    user_id: str,
    thread_id: str,
    action_type: str,
    payload: dict[str, Any],
) -> None:
    db = get_supabase()
    db.table("pending_actions").upsert(
        {
            "user_id": user_id,
            "thread_id": thread_id,
            "action_type": action_type,
            "payload": payload,
            "status": "pending",
        },
        on_conflict="thread_id,action_type",
    ).execute()


async def get_pending_action(thread_id: str, action_type: str) -> dict[str, Any] | None:
    db = get_supabase()
    result = (
        db.table("pending_actions")
        .select("*")
        .eq("thread_id", thread_id)
        .eq("action_type", action_type)
        .eq("status", "pending")
        .maybe_single()
        .execute()
    )
    return _data_or_none(result)


async def clear_pending_action(thread_id: str, action_type: str, status: str) -> None:
    db = get_supabase()
    db.table("pending_actions").update({"status": status}).eq("thread_id", thread_id).eq(
        "action_type", action_type
    ).eq("status", "pending").execute()
