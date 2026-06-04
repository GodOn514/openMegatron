# Feishu Integration

The gateway exposes a Feishu event callback endpoint:

```text
POST /integrations/feishu/events
```

Run the gateway with:

```powershell
$env:FEISHU_APP_ID="cli_xxx"
$env:FEISHU_APP_SECRET="xxx"
$env:FEISHU_VERIFICATION_TOKEN="xxx"
$env:FEISHU_ENCRYPT_KEY="xxx" # optional, only when callback encryption/signature is enabled
venv\Scripts\python.exe pysrc\agent.py --serve --host 0.0.0.0 --port 8080
```

For local dry-run testing without sending replies to Feishu:

```powershell
$env:FEISHU_REPLY_ENABLED="0"
venv\Scripts\python.exe pysrc\agent.py --serve --host 127.0.0.1 --port 8080
venv\Scripts\python.exe scripts\simulate_feishu_event.py "帮我查一下2024年以来人机协同的论文"
```

Supported behavior:

- URL verification returns the Feishu `challenge` value.
- Text message events are mapped to session IDs like `feishu_<tenant_key>_<chat_id>`.
- Duplicate event IDs are ignored for a short TTL to reduce retry duplication.
- Agent replies are sent as message replies when `FEISHU_APP_ID` and `FEISHU_APP_SECRET` are configured.
- Tool execution confirmations are sent as an interactive card with Allow/Deny buttons.
- Local fallback confirmation commands are also supported:

```text
/approve <request_id>
/deny <request_id>
```

Equivalent environment variables:

```text
FEISHU_APP_ID
FEISHU_APP_SECRET
FEISHU_VERIFICATION_TOKEN
FEISHU_ENCRYPT_KEY
FEISHU_API_BASE
FEISHU_REQUEST_TIMEOUT_SEC
FEISHU_REPLY_ENABLED
FEISHU_CONFIRMATION_WATCH_SEC
```
