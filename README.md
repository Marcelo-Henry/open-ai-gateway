<div align="center">

# codex-gateway

<p>
  <a href="https://github.com/jwadow/kiro-gateway/releases">
    <img src="https://img.shields.io/badge/version-2.3-6366f1?style=for-the-badge" alt="Version" />
  </a>
  <img src="https://img.shields.io/badge/python-%3E%3D3.10-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python >= 3.10" />
  <a href="./LICENSE">
    <img src="https://img.shields.io/badge/license-AGPL--3.0-22c55e?style=for-the-badge" alt="AGPL-3.0 License" />
  </a>
  <img src="https://img.shields.io/badge/FastAPI-0.100+-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI" />
</p>

**OpenAI & Anthropic-compatible proxy for Kiro (Amazon Q Developer / AWS CodeWhisperer).**

Use any AI client — Cursor, Claude Code, Continue, Cline, and more — with your Kiro subscription.

[Quick Start](#-quick-start) · [Authentication](#-authentication) · [Configuration](#-configuration) · [Docker](#-docker) · [FAQ](#-faq)

</div>

---

## ✨ Features

- **🔌 Drop-in compatible** — OpenAI (`/v1/chat/completions`) and Anthropic (`/v1/messages`) APIs
- **🛠️ Incremental tool call streaming** — Streams `tool_use`/`tool_calls` argument deltas incrementally to reduce malformed tool-call edge cases in clients
- **🔐 4 auth methods** — JSON file, refresh token, SQLite DB (kiro-cli), AWS SSO OIDC
- **🧠 Extended thinking** — Fake reasoning via tag injection, exposed as `reasoning_content`
- **⚡ Streaming** — Full SSE streaming support for both API formats
- **🐳 Docker ready** — Single-command deploy with docker-compose
- **🌐 VPN/Proxy support** — HTTP and SOCKS5 proxy for restricted networks (China, corporate)
- **🔁 Auto-retry** — Exponential backoff on 429, 5xx, and timeouts
- **🗂️ Model aliases** — Map custom names to real model IDs
- **🐛 Debug logging** — Save full request/response logs for troubleshooting

---

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- Active Kiro / Amazon Q Developer subscription
- Kiro credentials (see [Authentication](#-authentication))

### Installation

```bash
# Clone the repository
git clone https://github.com/jwadow/kiro-gateway.git
cd kiro-gateway

# Install dependencies
pip install -r requirements.txt

# Configure credentials
cp .env.example .env
# Edit .env with your credentials
```

### Run

```bash
python main.py
```

Server starts at `http://localhost:8000`. Check `http://localhost:8000/health` to confirm it's up.

```bash
# Custom port
python main.py --port 9000

# Local connections only
python main.py --host 127.0.0.1 --port 9000
```

---

## 🔐 Authentication

Choose **one** of the four methods and configure it in your `.env` file.

### Option 1 — JSON credentials file (Kiro IDE) ✅ Recommended

```env
KIRO_CREDS_FILE=~/.aws/sso/cache/kiro-auth-token.json
```

The file is created automatically when you log in to the Kiro IDE.

### Option 2 — Refresh token

```env
REFRESH_TOKEN=your_refresh_token_here
```

Capture the token from Kiro IDE network traffic (look for `refreshToken` in requests to `auth.desktop.kiro.dev`).

### Option 3 — kiro-cli SQLite database

```env
KIRO_CLI_DB_FILE=~/.local/share/kiro-cli/data.sqlite3
```

Created automatically after running `kiro login` with the [kiro-cli](https://github.com/aws/amazon-q-developer-cli).

### Option 4 — AWS SSO OIDC (Enterprise / Builder ID)

Credentials are auto-detected from the JSON file when `clientId` and `clientSecret` are present. No extra configuration needed beyond `KIRO_CREDS_FILE`.

---

## ⚙️ Configuration

Copy `.env.example` to `.env` and adjust as needed.

### Required

| Variable        | Description                                           | Default                        |
| --------------- | ----------------------------------------------------- | ------------------------------ |
| `PROXY_API_KEY` | Password clients use to authenticate with the gateway | `my-super-secret-password-123` |

### Authentication (choose one)

| Variable           | Description                            |
| ------------------ | -------------------------------------- |
| `KIRO_CREDS_FILE`  | Path to Kiro IDE JSON credentials file |
| `REFRESH_TOKEN`    | Kiro refresh token                     |
| `KIRO_CLI_DB_FILE` | Path to kiro-cli SQLite database       |

### Optional

| Variable                      | Description                                                | Default     |
| ----------------------------- | ---------------------------------------------------------- | ----------- |
| `SERVER_HOST`                 | Bind address                                               | `0.0.0.0`   |
| `SERVER_PORT`                 | Port                                                       | `8000`      |
| `KIRO_REGION`                 | AWS region                                                 | `us-east-1` |
| `LOG_LEVEL`                   | Log verbosity (`DEBUG`, `INFO`, `WARNING`)                 | `INFO`      |
| `DEBUG_MODE`                  | Save request/response logs (`off`, `errors`, `all`)        | `off`       |
| `VPN_PROXY_URL`               | HTTP/SOCKS5 proxy URL                                      | —           |
| `FAKE_REASONING`              | Enable extended thinking via tag injection                 | `true`      |
| `FAKE_REASONING_MAX_TOKENS`   | Max thinking tokens                                        | `4000`      |
| `TOOL_DESCRIPTION_MAX_LENGTH` | Max tool description length before moving to system prompt | `10000`     |
| `FIRST_TOKEN_TIMEOUT`         | Seconds to wait for first streaming token before retry     | `15`        |
| `STREAMING_READ_TIMEOUT`      | Max seconds between streaming chunks                       | `300`       |

---

## 🌐 API Endpoints

### OpenAI-compatible

```
GET  /v1/models                  List available models
POST /v1/chat/completions        Chat completions (streaming + non-streaming)
```

### Anthropic-compatible

```
POST /v1/messages                Messages API (streaming + non-streaming)
```

### Utility

```
GET  /health                     Health check
GET  /docs                       Interactive API docs (Swagger UI)
```

### Authentication

```bash
# OpenAI format
Authorization: Bearer YOUR_PROXY_API_KEY

# Anthropic format
x-api-key: YOUR_PROXY_API_KEY
```

---

## 🐳 Docker

### docker-compose (recommended)

```bash
# Start
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down

# Rebuild after code changes
docker-compose up -d --build
```

### docker run

```bash
# With refresh token
docker run -d \
  -p 8000:8000 \
  -e PROXY_API_KEY="your-secret-key" \
  -e REFRESH_TOKEN="your-refresh-token" \
  --name kiro-gateway \
  ghcr.io/jwadow/kiro-gateway:latest

# With credentials file
docker run -d \
  -p 8000:8000 \
  -v ~/.aws/sso/cache:/home/kiro/.aws/sso/cache:ro \
  -e KIRO_CREDS_FILE=/home/kiro/.aws/sso/cache/kiro-auth-token.json \
  -e PROXY_API_KEY="your-secret-key" \
  --name kiro-gateway \
  ghcr.io/jwadow/kiro-gateway:latest

# With kiro-cli database
docker run -d \
  -p 8000:8000 \
  -v ~/.local/share/kiro-cli:/home/kiro/.local/share/kiro-cli:ro \
  -e KIRO_CLI_DB_FILE=/home/kiro/.local/share/kiro-cli/data.sqlite3 \
  -e PROXY_API_KEY="your-secret-key" \
  --name kiro-gateway \
  ghcr.io/jwadow/kiro-gateway:latest
```

---

## 🧠 Extended Thinking

AI Gateway injects `<thinking_mode>` tags into requests so models reason before responding. The thinking block is extracted and returned as `reasoning_content` (OpenAI-compatible).

```env
FAKE_REASONING=true                        # Enable (default)
FAKE_REASONING_MAX_TOKENS=4000             # Thinking budget
FAKE_REASONING_HANDLING=as_reasoning_content  # or: remove, pass, strip_tags
```

> This is a prompt-level hack, not native extended thinking — it works great but relies on the model following the injected instructions.

---

## 🌐 VPN / Proxy Support

For restricted networks (China, corporate firewalls):

```env
VPN_PROXY_URL=http://127.0.0.1:7890        # HTTP proxy
VPN_PROXY_URL=socks5://127.0.0.1:1080      # SOCKS5 proxy
VPN_PROXY_URL=http://user:pass@proxy:8080  # With authentication
```

---

## 🗂️ Model Aliases

Map custom names to real model IDs — useful to avoid conflicts with IDE-specific names (e.g., Cursor's `auto`):

```python
# In kiro/config.py
MODEL_ALIASES = {
    "auto-kiro": "auto",          # Default: avoids Cursor conflict
    "my-opus": "claude-opus-4.5", # Custom shortcut
}
```

---

## 🐛 Debug Logging

```env
DEBUG_MODE=errors   # Save logs only for failed requests (recommended for troubleshooting)
DEBUG_MODE=all      # Save logs for every request
DEBUG_MODE=off      # Disabled (default)
```

Logs are saved to `debug_logs/` with full request and response details.

---

## 🧪 Tests

```bash
# Run all tests
pytest -v

# Unit tests only
pytest tests/unit/ -v

# Integration tests only
pytest tests/integration/ -v

# With coverage
pytest --cov=kiro --cov-report=html
```

All tests run with complete network isolation — no real API calls are made.

---

## ❓ FAQ

<details>
<summary><strong>Which AI clients work with AI Gateway?</strong></summary>

Any client that supports OpenAI or Anthropic API format:
- **Cursor** — set base URL to `http://localhost:8000/v1`
- **Claude Code** — use `ANTHROPIC_BASE_URL=http://localhost:8000`
- **Continue** — configure as OpenAI provider
- **Cline**, **Roo**, **Aider**, **Open WebUI**, and more

</details>

<details>
<summary><strong>I'm getting "Improperly formed request" errors.</strong></summary>

This is a notoriously vague Kiro API error that can mean many things: message structure issues, tool definition problems, content format errors, or undocumented constraints. Enable debug logging (`DEBUG_MODE=errors`) to capture the full request/response and identify the cause.

</details>

<details>
<summary><strong>How do I get my refresh token?</strong></summary>

Open the Kiro IDE, open DevTools (F12), go to the Network tab, and look for requests to `auth.desktop.kiro.dev`. The `refreshToken` field in the request body is what you need.

</details>

<details>
<summary><strong>Can I use this with a free Kiro plan?</strong></summary>

Yes, but some models (like Opus) may not be available on free plans. The gateway will return whatever Kiro API allows for your subscription.

</details>

<details>
<summary><strong>Token refresh is failing. What do I do?</strong></summary>

1. Check that your credentials file or refresh token is still valid (tokens expire)
2. Re-login to Kiro IDE to get fresh credentials
3. Enable `DEBUG_MODE=errors` and check `debug_logs/` for the exact error

</details>

---

## 📄 License

AGPL-3.0 — see [LICENSE](LICENSE) for details.

---

## Credits

This project is a fork of kiro-gateway by Jwadow, licensed under AGPL-3.0.

---

<div align="center">
  <sub>Made with ❤️ by <a href="https://github.com/jwadow">@jwadow</a> · <a href="https://github.com/jwadow/kiro-gateway/issues">Report an issue</a></sub>
</div>
