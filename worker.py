from arq.connections import RedisSettings
from arq.cron import cron

from config import get_settings
from schemas import WhatsAppIncomingMessage
from services.alerts import check_due_alerts
from services.broker import sync_portfolio_snapshots
from services.chatbot import handle_whatsapp_message


async def process_whatsapp_message(ctx, payload: dict) -> None:
    message = WhatsAppIncomingMessage.model_validate(payload)
    await handle_whatsapp_message(message)


async def sync_all_portfolios(ctx) -> None:
    await sync_portfolio_snapshots()


async def check_price_alerts(ctx) -> None:
    await check_due_alerts()


class WorkerSettings:
    settings = get_settings()

    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    functions = [process_whatsapp_message, sync_all_portfolios, check_price_alerts]
    cron_jobs = [
        cron(sync_all_portfolios, minute={0, 15, 30, 45}),
        cron(check_price_alerts, minute={1, 6, 11, 16, 21, 26, 31, 36, 41, 46, 51, 56}),
    ]
    max_jobs = 20
    job_timeout = 180
    keep_result = 3600
