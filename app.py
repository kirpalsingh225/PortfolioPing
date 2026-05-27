from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from config import get_settings
from schemas import EnqueueResponse, HealthResponse, WhatsAppIncomingMessage
from services.redis_queue import get_redis_pool
from services.security import verify_meta_signature
from services.zerodha_auth import build_login_url, exchange_request_token
from services.whatsapp import extract_text_messages


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = await get_redis_pool()
    yield
    await app.state.redis.close()


settings = get_settings()
app = FastAPI(title="Stock Portfolio WhatsApp Bot", version="0.1.0", lifespan=lifespan)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", app_env=settings.app_env)


@app.get("/legal/privacy", response_class=PlainTextResponse)
async def privacy_policy() -> str:
    return """Privacy Policy - WhatsApp Portfolio Assistant

We collect your WhatsApp phone number, chat messages, profile name if provided by WhatsApp or by you, Zerodha connection status, portfolio snapshots, alerts, paper-order confirmations, and audit events needed to operate the assistant.

We use this data to identify your account, respond to your messages, show portfolio information, manage alerts, and maintain safety/audit logs.

We do not sell your data. Broker access tokens are stored encrypted. Do not share sensitive credentials in chat.

This prototype is for portfolio information and alerts. It does not provide personalized investment advice and does not place real trades.

To stop using the assistant, message STOP or contact the operator to delete your data."""


@app.get("/legal/terms", response_class=PlainTextResponse)
async def terms() -> str:
    return """Terms - WhatsApp Portfolio Assistant

By replying AGREE, you opt in to receive WhatsApp messages from this assistant and allow the app to process your messages and connected Zerodha account information for portfolio features.

The assistant is not a SEBI-registered investment adviser. It does not provide personalized investment advice, research recommendations, or guarantees about returns.

Buy/sell flows in this prototype are paper-trade simulations only. Real order placement is disabled.

Market and portfolio data may be delayed, incomplete, or unavailable. Always verify important information in Zerodha before making financial decisions.

You can stop interacting with the bot at any time."""


@app.get("/webhooks/whatsapp")
async def verify_whatsapp_webhook(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
):
    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token:
        return PlainTextResponse(hub_challenge or "")
    raise HTTPException(status_code=403, detail="Invalid WhatsApp verification token")


@app.post("/webhooks/whatsapp", response_model=list[EnqueueResponse])
async def whatsapp_webhook(request: Request) -> list[EnqueueResponse]:
    body = await request.body()
    signature = request.headers.get("x-hub-signature-256")
    if not verify_meta_signature(body, signature):
        raise HTTPException(status_code=403, detail="Invalid WhatsApp signature")

    payload: dict[str, Any] = await request.json()
    messages = extract_text_messages(payload)
    responses: list[EnqueueResponse] = []

    for message in messages:
        job = await request.app.state.redis.enqueue_job(
            "process_whatsapp_message",
            message.model_dump(),
            _job_id=f"wa:{message.message_id}",
        )
        responses.append(
            EnqueueResponse(
                queued=job is not None,
                job_id=job.job_id if job else None,
                reason=None if job else "duplicate_or_rejected",
            )
        )

    return responses


@app.post("/debug/enqueue-message", response_model=EnqueueResponse)
async def debug_enqueue_message(message: WhatsAppIncomingMessage, request: Request) -> EnqueueResponse:
    if settings.app_env == "production":
        raise HTTPException(status_code=404, detail="Not found")

    job = await request.app.state.redis.enqueue_job(
        "process_whatsapp_message",
        message.model_dump(),
        _job_id=f"debug:{message.message_id}",
    )
    return EnqueueResponse(
        queued=job is not None,
        job_id=job.job_id if job else None,
        reason=None if job else "duplicate_or_rejected",
    )


@app.post("/jobs/sync-portfolios", response_model=EnqueueResponse)
async def enqueue_portfolio_sync(request: Request, api_secret: str) -> EnqueueResponse:
    if api_secret != settings.api_secret:
        raise HTTPException(status_code=403, detail="Invalid API secret")

    job = await request.app.state.redis.enqueue_job("sync_all_portfolios")
    return EnqueueResponse(queued=job is not None, job_id=job.job_id if job else None)


@app.post("/jobs/check-alerts", response_model=EnqueueResponse)
async def enqueue_alert_check(request: Request, api_secret: str) -> EnqueueResponse:
    if api_secret != settings.api_secret:
        raise HTTPException(status_code=403, detail="Invalid API secret")

    job = await request.app.state.redis.enqueue_job("check_price_alerts")
    return EnqueueResponse(queued=job is not None, job_id=job.job_id if job else None)


@app.get("/auth/zerodha/login-url")
async def zerodha_login_url(user_id: str, api_secret: str) -> dict[str, str]:
    if api_secret != settings.api_secret:
        raise HTTPException(status_code=403, detail="Invalid API secret")
    return {"login_url": build_login_url(user_id)}


@app.get("/auth/zerodha/callback")
async def zerodha_callback(request_token: str, state: str) -> dict[str, str]:
    user_id = await exchange_request_token(request_token, state)
    return {"status": "connected", "user_id": user_id}
