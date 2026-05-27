from typing import Any

import httpx

from config import get_settings
from schemas import WhatsAppIncomingMessage


def extract_text_messages(payload: dict[str, Any]) -> list[WhatsAppIncomingMessage]:
    messages: list[WhatsAppIncomingMessage] = []
    entries = payload.get("entry", [])

    for entry in entries:
        for change in entry.get("changes", []):
            value = change.get("value", {})
            profile_names = {
                contact.get("wa_id"): (contact.get("profile") or {}).get("name")
                for contact in value.get("contacts", [])
            }
            for item in value.get("messages", []):
                if item.get("type") != "text":
                    continue
                text = item.get("text", {}).get("body", "").strip()
                sender = item.get("from")
                message_id = item.get("id")
                if not text or not sender or not message_id:
                    continue
                messages.append(
                    WhatsAppIncomingMessage(
                        message_id=message_id,
                        from_phone=sender,
                        text=text,
                        profile_name=profile_names.get(sender),
                        raw_payload=item,
                    )
                )

    return messages


async def send_whatsapp_text(to_phone: str, body: str) -> dict[str, Any]:
    settings = get_settings()
    url = (
        f"https://graph.facebook.com/{settings.whatsapp_api_version}/"
        f"{settings.whatsapp_phone_number_id}/messages"
    )
    headers = {"Authorization": f"Bearer {settings.whatsapp_access_token}"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "text",
        "text": {"preview_url": False, "body": body[:4096]},
    }

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(url, headers=headers, json=payload)
        if response.is_error:
            raise RuntimeError(f"WhatsApp send failed {response.status_code}: {response.text}")
        return response.json()
