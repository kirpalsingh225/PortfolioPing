# Render Deployment

This app needs two Render services:

- Web Service: FastAPI webhook/API
- Background Worker: ARQ worker

## 1. Push Code To GitHub

Make sure `.env` and `secrets.md` are not committed.

## 2. Create Redis

Use Upstash Redis and copy the TCP/TLS URL:

```env
REDIS_URL=rediss://default:<password>@<host>:6379
```

Do not use the Upstash REST URL for ARQ.

## 3. Create Render Blueprint

In Render:

```text
New → Blueprint → connect GitHub repo → select render.yaml
```

Render will create:

```text
stock-portfolio-whatsapp-api
stock-portfolio-whatsapp-worker
```

## 4. Add Environment Variables To Both Services

Add the same secrets to both the web service and worker:

```env
APP_BASE_URL=https://<render-api-url>
API_SECRET=<strong-random-secret>
TOKEN_ENCRYPTION_KEY=<fernet-key>
REDIS_URL=<upstash-rediss-url>
SUPABASE_URL=<supabase-url>
SUPABASE_SERVICE_ROLE_KEY=<supabase-service-role-key>
WHATSAPP_VERIFY_TOKEN=<your-verify-token>
WHATSAPP_APP_SECRET=<meta-app-secret>
WHATSAPP_ACCESS_TOKEN=<meta-system-user-token>
WHATSAPP_PHONE_NUMBER_ID=<real-or-test-phone-number-id>
WHATSAPP_API_VERSION=v25.0
BROKER_PROVIDER=zerodha
ZERODHA_API_KEY=<kite-api-key>
ZERODHA_API_SECRET=<kite-api-secret>
ZERODHA_REDIRECT_URL=https://<render-api-url>/auth/zerodha/callback
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=<openrouter-key>
OPENROUTER_MODEL=openai/gpt-oss-120b:free
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
MAX_RAW_MESSAGES=10
SUMMARY_TRIGGER_MESSAGES=18
```

Generate Fernet key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## 5. Update Dashboards

Meta WhatsApp webhook:

```text
https://<render-api-url>/webhooks/whatsapp
```

Zerodha redirect URL:

```text
https://<render-api-url>/auth/zerodha/callback
```

## 6. Verify

```bash
curl https://<render-api-url>/health
```

Expected:

```json
{"status":"ok","app_env":"production"}
```
