# PortfolioPing

## WhatsApp Stock Portfolio Assistant

PortfolioPing is a WhatsApp-based stock portfolio assistant built for the OpenAI x Outskill Hackathon. It lets a user chat with a WhatsApp bot, opt in, connect Zerodha through the official Kite login flow, ask portfolio-related questions, manage a watchlist, and create stock price alerts.

The current version is a working MVP/prototype. It is deployed on Render and uses a single web service for the hackathon demo.

## Demo Video

[Watch the demo video](https://github.com/kirpalsingh225/PortfolioPing/blob/main/assets/VID_20260528_225547_1.mp4)

## Demo Flow

```text
User sends: hi
Bot asks for consent and shares privacy/terms links
User replies: AGREE
Bot sends a secure Zerodha connect link
User connects Zerodha
User asks: show my portfolio
User asks: add TCS to watchlist
User asks: what all stocks are in my watchlist?
User asks: set alert for INFY above 1600
User asks: /search latest news about INFY
Bot answers with source links when web search is needed
```

## What It Does

- Receives and replies to WhatsApp messages using Meta WhatsApp Cloud API.
- Stores users, chat history, consent state, alerts, and broker connection data in Supabase.
- Generates Zerodha Kite Connect login links for each WhatsApp user.
- Stores broker access tokens in encrypted form.
- Uses LangChain with OpenRouter for chatbot replies.
- Uses Tavily web search for current public information when needed.
- Maintains chat context using cleaned backend state, raw recent messages, and summarized conversation memory.
- Supports portfolio questions, stock price questions, watchlists, alert creation/cancellation, source-backed web search, and basic profile memory.
- Supports simple user control commands such as `/connect` for a fresh Zerodha login link, `/watchlist`, `/watch TCS`, `/unwatch TCS`, and `/search` for forced web search.
- Supports scheduled alert checking through an external cron trigger in the free Render deployment.
- Provides privacy and terms pages.
- Supports paper-trade style buy/sell confirmation, but does not place real trades.

## Tech Stack

- Python
- FastAPI
- Meta WhatsApp Cloud API
- Zerodha Kite Connect
- Supabase Postgres
- LangChain
- OpenRouter
- Tavily
- Render
- cron-job.org or external scheduler for periodic alert checks
- Redis/ARQ support for production worker mode

## Project Structure

```text
app.py                  FastAPI app, WhatsApp webhook, legal pages, Zerodha auth routes
worker.py               ARQ worker jobs for production worker mode
config.py               Environment-based settings
schemas.py              Pydantic request/response models
services/whatsapp.py    WhatsApp message extraction and sending
services/chatbot.py     Main chatbot orchestration and user flows
services/llm.py         LangChain/OpenRouter prompts, intent classification, summaries
services/web_search.py  Tavily search integration for current public information
services/broker.py      Portfolio and market-data logic
services/zerodha_auth.py Zerodha login/callback helpers
services/supabase_db.py Supabase data access
services/memory.py      Chat history and summarization logic
db/schema.sql           Supabase database schema
render.yaml             Render single-service deployment config
deck/                   Phase 1 pitch deck files
```

## Environment Variables

Create `.env` locally using `.env.example` as a reference.

Important production variables:

```env
APP_ENV=production
QUEUE_MODE=inline
APP_BASE_URL=https://your-render-service.onrender.com

SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...

WHATSAPP_VERIFY_TOKEN=...
WHATSAPP_APP_SECRET=...
WHATSAPP_ACCESS_TOKEN=...
WHATSAPP_PHONE_NUMBER_ID=...
WHATSAPP_API_VERSION=v25.0

BROKER_PROVIDER=zerodha
ZERODHA_API_KEY=...
ZERODHA_API_SECRET=...
ZERODHA_REDIRECT_URL=https://your-render-service.onrender.com/auth/zerodha/callback

LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=...
OPENROUTER_MODEL=openai/gpt-oss-120b:free
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
TAVILY_API_KEY=...

TOKEN_ENCRYPTION_KEY=...
API_SECRET=...
```

Do not commit `.env` or any real secrets.

## Local Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill in `.env`, then run:

```bash
uvicorn app:app --reload
```

For local ARQ worker mode, set:

```env
QUEUE_MODE=arq
REDIS_URL=redis://localhost:6379/0
```

Then run:

```bash
arq worker.WorkerSettings
```

## Database Setup

Run the SQL in:

```text
db/schema.sql
```

inside the Supabase SQL editor.

The database stores:

- WhatsApp users
- Broker accounts
- Holdings snapshots
- Chat messages
- Chat summaries
- Pending actions
- Alerts
- Watchlist items
- Paper orders
- Audit events

## Render Deployment

The hackathon deployment uses one free Render Web Service:

```env
QUEUE_MODE=inline
```

Build command:

```bash
pip install -r requirements.txt
```

Start command:

```bash
uvicorn app:app --host 0.0.0.0 --port $PORT
```

Health check:

```text
https://your-render-service.onrender.com/health
```

Expected response:

```json
{"status":"ok","app_env":"production"}
```

## Alert Checking

In the free Render deployment, the app uses `QUEUE_MODE=inline`, so ARQ cron jobs do not run automatically.

To check alerts periodically, use an external scheduler such as cron-job.org and call:

```text
POST https://your-render-service.onrender.com/jobs/check-alerts?api_secret=YOUR_API_SECRET
```

Recommended MVP schedule:

```text
Every 5-10 minutes
```

This path is wired for scheduled checks. Live alert delivery requires Zerodha quote/LTP permission for the connected Kite app. Without that permission, alerts remain saved in Supabase but cannot be triggered from Zerodha live prices.

## Web Search

The chatbot can use Tavily for recent/current public information that is not available from Supabase, Zerodha, or memory.

Natural language examples:

```text
latest news about INFY
what happened to TCS today
```

Forced search command:

```text
/search latest RBI update about markets
```

Search replies include source links and remain informational only, not investment advice.

The bot uses web search only when the user asks for recent/current public information, or when the `/search` command is used. Portfolio facts still come from Supabase and Zerodha, not from web search.

## WhatsApp Setup

In Meta Developers, configure the webhook:

```text
Callback URL: https://your-render-service.onrender.com/webhooks/whatsapp
Verify token: same value as WHATSAPP_VERIFY_TOKEN
Subscribed field: messages
```

For the current prototype, users must be added as test recipients if using Meta's WhatsApp test number.

## Zerodha Setup

In Zerodha Kite Developer Console, set the redirect URL:

```text
https://your-render-service.onrender.com/auth/zerodha/callback
```

The app uses Zerodha's official login flow. Users should never share Zerodha passwords, PINs, OTPs, or API secrets in WhatsApp.

## Safety And Scope

This is a hackathon MVP, not a regulated financial advisory product.

- Real order placement is disabled.
- Buy/sell flows are paper-trade simulations only.
- The bot should not provide personalized investment advice.
- Users must opt in before portfolio features.
- Broker tokens are encrypted before storage.
- WhatsApp webhook signatures are verified in production.
- Periodic alert checking is handled by an external scheduler in free Render mode, or by ARQ cron jobs in worker mode.

## Current Status

The production demo flow is working:

```text
WhatsApp message
→ Render webhook
→ Supabase-backed user flow
→ cleaned backend context + chatbot response
→ WhatsApp reply
```

The MVP is ready for hackathon Phase 1 demo and now includes consent onboarding, Zerodha linking, WhatsApp chat, cleaned LLM context, Tavily search with sources, saved alerts, and external cron wiring.

Known prototype limitations:

- Mixed multi-part questions currently follow the primary detected intent first.
- Live alert triggering depends on Zerodha LTP/quote permission.
- Real trading is disabled; buy/sell flows are confirmation-only paper simulations.
- A real WhatsApp Business number is needed before opening access beyond Meta test recipients.
