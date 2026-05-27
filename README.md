# STOCK_AGENT

## Stock Portfolio WhatsApp Bot

FastAPI + ARQ backend for an India-first stock portfolio WhatsApp assistant.

## What is included

- `app.py`: FastAPI app, WhatsApp webhook verification, job enqueue endpoints.
- `worker.py`: ARQ worker jobs that execute WhatsApp processing, portfolio sync, and alert checks.
- `services/`: Supabase, WhatsApp Cloud API, Zerodha, LangChain/Ollama, memory, alerts, and paper-order logic.
- `db/schema.sql`: Supabase/Postgres tables for users, broker accounts, chat memory, summaries, alerts, and paper orders.

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill real values in `.env`, then run:

```bash
uvicorn app:app --reload
arq worker.WorkerSettings
```

## Redis

Use the Upstash **Redis TCP/TLS** URL for ARQ:

```env
REDIS_URL=rediss://default:<password>@<host>:6379
```

Do not use the Upstash REST URL for ARQ.

## Database

Run `db/schema.sql` in Supabase SQL editor before starting the app.

Permanent data lives in Supabase. Redis is only for queueing, dedupe, locks, and temporary job state.

## Broker

This prototype uses Zerodha Kite Connect as the broker integration:

```env
BROKER_PROVIDER=zerodha
ZERODHA_API_KEY=<your Kite Connect API key>
ZERODHA_API_SECRET=<your Kite Connect API secret>
ZERODHA_REDIRECT_URL=http://localhost:8000/auth/zerodha/callback
```

The app reads holdings and prices through Zerodha after the user connects through the Kite login flow. Real order placement is still disabled.

## Safety defaults

- Real order placement is not implemented.
- Buy/sell requests create pending paper trades only.
- A paper trade is recorded only after the user replies `confirm`.
- Broker access tokens are encrypted before storage when `TOKEN_ENCRYPTION_KEY` is configured.
- WhatsApp signatures are required in production.
