from typing import Any, Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    app_env: str


class EnqueueResponse(BaseModel):
    queued: bool
    job_id: str | None = None
    reason: str | None = None


class WhatsAppIncomingMessage(BaseModel):
    message_id: str
    from_phone: str
    text: str
    profile_name: str | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class ChatIntent(BaseModel):
    intent: Literal[
        "portfolio_summary",
        "stock_price_query",
        "create_alert",
        "update_alert",
        "cancel_alert",
        "add_watchlist",
        "remove_watchlist",
        "show_watchlist",
        "paper_buy",
        "paper_sell",
        "web_search",
        "general_question",
    ]
    symbol: str | None = None
    exchange: str | None = None
    quantity: int | None = None
    target_price: float | None = None
    condition: Literal["above", "below"] | None = None
    side: Literal["buy", "sell"] | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    needs_confirmation: bool = True


class PaperOrderDraft(BaseModel):
    user_id: str
    symbol: str
    exchange: str = "NSE"
    side: Literal["buy", "sell"]
    quantity: int
    order_type: Literal["market", "limit"] = "market"
    limit_price: float | None = None
