# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the gateway
python main.py

# Run all tests
pytest

# Run a single test file
pytest tests/unit/test_converters.py

# Run a single test
pytest tests/unit/test_converters.py::test_function_name

# Run with verbose output
pytest -v

# Install dependencies
pip install -r requirements.txt
```

## Architecture

**codex-gateway** is a FastAPI proxy that translates OpenAI, Anthropic, and Gemini API requests into the Kiro (Amazon Q Developer / AWS CodeWhisperer) wire format. Any AI client (Cursor, Claude Code, Cline, Continue) can point at this gateway and use a Kiro subscription.

### Layered architecture

```
┌─────────────────────────────────────────────────────────────┐
│  ENTRY LAYER: routes_openai.py / routes_anthropic.py        │
│  GET /v1/models  POST /v1/chat/completions  POST /v1/messages│
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│  ORCHESTRATION: account_manager.py / model_resolver.py / auth.py │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│  CONVERSION: converters_core.py + converters_openai/anthropic│
│  truncation_recovery.py / mcp_tools.py                      │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│  TRANSPORT: http_client.py (retry, per-request for streaming)│
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│  STREAMING: parsers.py → thinking_parser.py → streaming_core │
│  → streaming_openai.py / streaming_anthropic.py             │
└─────────────────────────────────────────────────────────────┘
```

### Request flow

1. Client sends request with `PROXY_API_KEY`
2. Route authenticates, detects format, applies pre-processing (truncation recovery, web_search inject)
3. `AccountManager` selects best available account (sticky + Circuit Breaker)
4. Converter translates to `KiroPayload` (8-step message normalization pipeline)
5. `KiroHttpClient` sends to `q.{region}.amazonaws.com/generateAssistantResponse`
6. `StreamingEngine` parses AWS Event Stream → extracts thinking blocks → formats SSE
7. Client receives response in the originally requested format

### Key modules

| Module | Responsibility |
|--------|---------------|
| `auth.py` | `KiroAuthManager` — token lifecycle, 4 auth sources, 2 auth types (KIRO_DESKTOP / AWS_SSO_OIDC), thread-safe auto-refresh via `asyncio.Lock` |
| `account_manager.py` | Multi-account failover with Circuit Breaker (exponential backoff, 10% probabilistic retry), sticky index, lazy init, atomic `state.json` persistence |
| `http_client.py` | `KiroHttpClient` — retry on 403 (force_refresh), 429/5xx (exponential backoff); per-request client for streaming to avoid CLOSE_WAIT leaks (ADR-001) |
| `model_resolver.py` + `cache.py` | 4-layer pipeline: alias → normalize (5 regex patterns) → dynamic cache → passthrough. Unknown models are never rejected (ADR-006) |
| `converters_core.py` | 8-step normalization pipeline; handles tool definitions, images, thinking tag injection, payload size limits (~615KB cap) |
| `converters_openai.py` / `_anthropic.py` | Format-specific adapters built on top of `converters_core` |
| `streaming_core.py` | Orchestrates `AwsEventStreamParser` + `ThinkingParser` FSM; first-token timeout with retry |
| `streaming_openai.py` / `_anthropic.py` | Converts `KiroEvent` stream to target SSE format |
| `parsers.py` | AWS Event Stream binary parser; detects cumulative snapshots of tool args; deduplicates by ID |
| `thinking_parser.py` | 3-state FSM (PRE_CONTENT → IN_THINKING → STREAMING); extracts `<thinking>` blocks from stream |
| `mcp_tools.py` | Web search: Path A (native Anthropic tool, bypasses generateAssistantResponse) and Path B (auto-inject) |
| `codex_provider.py` | Routes `gpt-*` / `codex-*` models to `chatgpt.com/backend-api/codex/responses` via ChatGPT OAuth |
| `truncation_recovery.py` | Detects silently truncated tool call payloads (Issue #56) and injects warning messages |
| `config.py` | All settings from `.env`; single source of truth for all constants |

### Auth methods (detection order)

Auth type is auto-detected: credentials with `clientId` + `clientSecret` → `AWS_SSO_OIDC`; otherwise → `KIRO_DESKTOP`.

| Source | Config | Auth type |
|--------|--------|-----------|
| JSON file (Kiro IDE) | `KIRO_CREDS_FILE` | KIRO_DESKTOP or AWS_SSO_OIDC |
| SQLite (kiro-cli) | `KIRO_CLI_DB_FILE` | KIRO_DESKTOP or AWS_SSO_OIDC |
| Env var token | `REFRESH_TOKEN` | KIRO_DESKTOP |
| Enterprise JSON | `KIRO_CREDS_FILE` with `clientId` | AWS_SSO_OIDC |

SQLite writes use Read-Merge-Write strategy to avoid race conditions with kiro-cli (ADR-004).

### Key config defaults (from `kiro/config.py`)

| Variable | Default | Notes |
|----------|---------|-------|
| `PROXY_API_KEY` | `my-super-secret-password-123` | Change in production |
| `FAKE_REASONING_ENABLED` | `true` | Active when env var is unset (empty string is not in the false list) |
| `WEB_SEARCH_ENABLED` | `true` | Auto-injects `web_search` tool into every request |
| `ACCOUNT_SYSTEM` | `false` | Multi-account failover disabled by default |
| `TRUNCATION_RECOVERY` | `true` | Auto-recovery for truncated tool calls |
| `AUTO_TRIM_PAYLOAD` | `false` | Auto-trim history when payload > ~615KB |
| `FIRST_TOKEN_TIMEOUT` | `15s` | Retry if no token received within this window |
| `DEBUG_MODE` | `off` | Set to `errors` or `all` to save full req/resp to `debug_logs/` |

### Kiro API constraints (non-obvious, enforced by converters_core.py)

These are undocumented Kiro API restrictions that the converter pipeline silently fixes:

- First message must be `user` role — inserts empty user message if needed (Issue #60)
- Strict user/assistant alternation required — inserts synthetic messages between consecutive same-role messages (Issue #64)
- Tool names max 64 characters — raises `ValueError` before sending
- `required: []` and `additionalProperties` must be removed from tool JSON schemas — causes 400 otherwise
- Payload max ~615KB — causes misleading "Improperly formed request" error if exceeded
- Tool descriptions > `TOOL_DESCRIPTION_MAX_LENGTH` are moved to system prompt with a reference

### Circuit Breaker (AccountManager)

- Exponential backoff: `60s × 2^(failures-1)`, capped at 1 day
- 10% probabilistic retry chance even during active cooldown
- With a single account configured, Circuit Breaker is disabled entirely — the account is always returned so the user sees real Kiro API errors

### Fake reasoning (extended thinking)

When `FAKE_REASONING_ENABLED=true` and the request has no tools, the gateway injects:
```
<thinking_mode>enabled</thinking_mode>
<max_thinking_length>{budget}</max_thinking_length>
```
at the start of the current user message. `ThinkingParser` FSM then extracts the `<thinking>` blocks from the response stream and returns them as proper `thinking` content blocks (Anthropic) or `reasoning_content` (OpenAI). Thinking injection is skipped when tools are present (ADR-007).

### Alternative routing

- Models `gpt-*` / `codex-*` → `codex_provider.py` → `chatgpt.com/backend-api/codex/responses` (requires `CODEX_AUTH_TOKEN`)
- Web search Path A: native Anthropic `web_search` tool → `mcp_tools.py` → Kiro MCP API (bypasses `generateAssistantResponse`)
- Web search Path B: `WEB_SEARCH_ENABLED=true` auto-injects `web_search` as a regular tool

### Architecture Decision Records

Full ADRs are in `_reversa_sdd/adrs/`. Summary:

| ADR | Decision |
|-----|----------|
| ADR-001 | Per-request httpx client for streaming (avoids CLOSE_WAIT on VPN disconnect) |
| ADR-002 | Truncation Recovery — notify model when Kiro silently truncates tool call payloads |
| ADR-003 | Message role normalization — fix undocumented Kiro API strict alternation requirement |
| ADR-004 | SQLite Read-Merge-Write — avoid race condition with kiro-cli on token save |
| ADR-005 | Dynamic region detection — auth endpoints vary by AWS region |
| ADR-006 | Model passthrough — unknown models forwarded to Kiro API without rejection |
| ADR-007 | Fake reasoning via tag injection — Kiro API doesn't support `thinking` param natively |

### Tests

Unit tests live in `tests/unit/` and are network-isolated (no real API calls). `manual_api_test.py` in the root is a manual integration script — run it directly with `python manual_api_test.py`, not via pytest.

### Full SDD documentation

Detailed specs, flowcharts, state machines, C4 diagrams, and traceability matrices are in `_reversa_sdd/`:

| Path | Contents |
|------|----------|
| `_reversa_sdd/architecture.md` | Layered architecture overview and all external integrations |
| `_reversa_sdd/sdd/` | Component SDDs for auth, account-manager, converters-core, streaming-core, parsers, http-client, routes, model-resolver, thinking-parser, mcp-codex |
| `_reversa_sdd/adrs/` | 7 Architecture Decision Records |
| `_reversa_sdd/flowcharts/` | Auth flow, full request flow, converter pipeline |
| `_reversa_sdd/state-machines.md` | FSMs for token lifecycle, Circuit Breaker, ThinkingParser, HTTP retry, streaming, account lazy-init |
| `_reversa_sdd/c4-context.md` / `c4-containers.md` / `c4-components.md` | C4 diagrams (levels 1–3) |
| `_reversa_sdd/data-dictionary.md` | All data structures: credentials.json, state.json, KiroPayload, UnifiedMessage, KiroEvent, MCP request/response |
| `_reversa_sdd/domain.md` | Domain glossary and 20 business rules |
| `_reversa_sdd/permissions.md` | Auth model: client→gateway (PROXY_API_KEY) and gateway→Kiro (access token) |
| `_reversa_sdd/traceability/` | Code-spec matrix and spec impact matrix (high-risk components: config.py, converters_core.py, streaming_core.py, parsers.py, auth.py, account_manager.py) |
| `_reversa_sdd/user-stories/` | 10 user stories across 4 epics |
| `_reversa_sdd/questions.md` | 6 open questions for validation (FAKE_REASONING default, WEB_SEARCH default, ACCOUNT_SYSTEM default, MCP endpoint, Codex Provider status) |
