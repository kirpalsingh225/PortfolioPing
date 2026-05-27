from schemas import PaperOrderDraft
from services.supabase_db import create_audit_event, get_supabase


async def create_paper_order(draft: PaperOrderDraft, confirmation_text: str) -> dict:
    db = get_supabase()
    result = db.table("paper_orders").insert(
        {
            "user_id": draft.user_id,
            "symbol": draft.symbol,
            "exchange": draft.exchange,
            "side": draft.side,
            "quantity": draft.quantity,
            "order_type": draft.order_type,
            "limit_price": draft.limit_price,
            "status": "confirmed_paper",
            "confirmation_text": confirmation_text,
        }
    ).execute()
    order = result.data[0]
    await create_audit_event(draft.user_id, "paper_order_created", {"paper_order_id": order["id"]})
    return order
