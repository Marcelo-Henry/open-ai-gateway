# Análise de Código — codex-gateway

> Gerado pelo Reversa Archaeologist em 2026-05-01
> Escala de confiança: 🟢 CONFIRMADO | 🟡 INFERIDO | 🔴 LACUNA

---

## Visão Geral da Arquitetura

O codex-gateway é um **proxy transparente** que traduz requisições entre formatos OpenAI/Anthropic e a API Kiro (Amazon Q Developer / AWS CodeWhisperer). A arquitetura é em camadas:

```
Cliente (OpenAI/Anthropic) → Routes → Converters → HTTP Client → Kiro API
                                                                      ↓
Cliente ← Streaming (SSE) ← Parsers ← ThinkingParser ← AWS Event Stream
```

---

## Módulo: `auth` 🟢

**Arquivos:** `kiro/auth.py`, `kiro/codex_auth.py`

### Classe `KiroAuthManager`

Gerencia o ciclo de vida de tokens de acesso para a Kiro API.

**Métodos principais:**

| Método | Parâmetros | Retorno | Descrição |
|---|---|---|---|
| `__init__` | refresh_token, profile_arn, region, creds_file, client_id, client_secret, sqlite_db, api_region | — | Inicializa, carrega credenciais, detecta tipo de auth |
| `get_access_token()` | — | `str` | Retorna token válido, refreshando se necessário (thread-safe via asyncio.Lock) |
| `force_refresh()` | — | `str` | Força refresh imediato (chamado em 403) |
| `is_token_expiring_soon()` | — | `bool` | Verifica se expira em < TOKEN_REFRESH_THRESHOLD (600s) |
| `is_token_expired()` | — | `bool` | Verifica se já expirou |
| `_load_credentials_from_sqlite(db_path)` | `str` | — | Lê auth_kv table, suporta 3 chaves de token |
| `_load_credentials_from_file(file_path)` | `str` | — | Lê JSON com refreshToken/accessToken/profileArn |
| `_save_credentials_to_sqlite()` | — | — | Read-Merge-Write para preservar campos desconhecidos |
| `_refresh_token_kiro_desktop()` | — | — | POST para prod.{region}.auth.desktop.kiro.dev/refreshToken |
| `_refresh_token_aws_sso_oidc()` | — | — | POST para oidc.{region}.amazonaws.com/token (JSON, camelCase) |

**Enum `AuthType`:**
- `KIRO_DESKTOP` — credenciais Kiro IDE (sem clientId/clientSecret)
- `AWS_SSO_OIDC` — credenciais kiro-cli (com clientId/clientSecret)

**Algoritmo de detecção de tipo:** presença de `clientId` + `clientSecret` → AWS_SSO_OIDC, caso contrário → KIRO_DESKTOP.

**Algoritmo de prioridade de região API:**
1. Parâmetro `api_region` explícito (por conta)
2. Variável de ambiente `KIRO_API_REGION`
3. Auto-detectado do ARN no SQLite (`state` table, campo `api.codewhisperer.profile`)
4. Região SSO (fallback)
5. Região padrão (`us-east-1`)

**Chaves SQLite suportadas (em ordem de prioridade):**
- `kirocli:social:token` — login social (Google, GitHub, Microsoft)
- `kirocli:odic:token` — AWS SSO OIDC corporativo
- `codewhisperer:odic:token` — legado AWS SSO OIDC

**Regra de negócio crítica:** No modo SQLite, se o refresh falhar com 400, o gateway tenta recarregar credenciais do SQLite (kiro-cli pode ter atualizado) e tenta novamente. Se ainda falhar, usa o access_token existente enquanto não expirar (degradação graciosa).

---

## Módulo: `account_manager` 🟢

**Arquivos:** `kiro/account_manager.py`, `kiro/account_errors.py`

### Classe `AccountManager`

Sistema de múltiplas contas com failover inteligente.

**Dataclasses:**
- `Account` — conta com auth_manager, model_cache, model_resolver, failures, last_failure_time, stats
- `AccountStats` — total_requests, successful_requests, failed_requests
- `ModelAccountList` — lista de account_ids que suportam um modelo

**Métodos principais:**

| Método | Descrição |
|---|---|
| `load_credentials()` | Lê credentials.json, suporta tipos: json, sqlite, refresh_token, pastas |
| `load_state()` | Restaura state.json (índice atual, falhas, stats) |
| `_save_state()` | Escrita atômica via tmp + rename |
| `_initialize_account(account_id)` | Lazy init: cria auth_manager, busca modelos, cria cache/resolver |
| `get_next_account(model, exclude_accounts)` | Circuit Breaker + Sticky — seleciona próxima conta disponível |
| `report_success(account_id, model)` | Reseta falhas, atualiza índice global (sticky) |
| `report_failure(account_id, model, error_type, ...)` | Incrementa falhas (apenas RECOVERABLE), atualiza stats |
| `get_all_available_models()` | Agrega modelos de todas as contas inicializadas |

**Algoritmo Circuit Breaker:**
- Backoff exponencial: `BASE * 2^(failures-1)`, cap em `BASE * MAX_MULTIPLIER` (1 dia)
- Retry probabilístico: 10% de chance de tentar conta "quebrada" antes do timeout
- Single account: Circuit Breaker desabilitado (usuário vê erros reais da Kiro API)

**Algoritmo Sticky:**
- `_current_account_index` global para todos os modelos
- Atualizado apenas em `report_success` (nunca em falha)
- Failover via `exclude_accounts` (set de contas já tentadas no loop atual)

**Tipos de credencial suportados:**
- `json` — arquivo JSON (Kiro IDE)
- `sqlite` — banco SQLite (kiro-cli)
- `refresh_token` — token direto (ID determinístico via SHA-256)
- Pasta — escaneia todos os arquivos válidos do tipo especificado

---

## Módulo: `routes` 🟢

**Arquivos:** `kiro/routes_openai.py`, `kiro/routes_anthropic.py`

### Endpoints OpenAI

| Endpoint | Método | Autenticação | Descrição |
|---|---|---|---|
| `/` | GET | Não | Health check básico |
| `/health` | GET | Não | Health check detalhado com timestamp |
| `/v1/models` | GET | Bearer token | Lista modelos disponíveis |
| `/v1/chat/completions` | POST | Bearer token | Chat completions (streaming e não-streaming) |

### Endpoints Anthropic

| Endpoint | Método | Autenticação | Descrição |
|---|---|---|---|
| `/v1/messages` | POST | x-api-key | Messages API (streaming e não-streaming) |

**Autenticação:** `Authorization: Bearer {PROXY_API_KEY}` (OpenAI) ou `x-api-key: {PROXY_API_KEY}` (Anthropic).

**Fluxo de `/v1/chat/completions` (Account System):**
1. Truncation recovery: modifica mensagens com tool_results truncados
2. Auto-inject `web_search` tool (se WEB_SEARCH_ENABLED)
3. Loop de failover: `MAX_ATTEMPTS = len(accounts) * 2`
4. Para cada tentativa: seleciona conta → build payload → POST Kiro API
5. Sucesso (200): report_success, retorna StreamingResponse ou JSONResponse
6. Erro FATAL: report_failure, retorna imediatamente ao cliente
7. Erro RECOVERABLE: report_failure, tenta próxima conta
8. Esgotamento: retorna 503 com último erro

**Fluxo de `/v1/messages` (Anthropic):**
- Detecta `web_search` nativo (Path A): bypass do Kiro, chama MCP API diretamente
- Detecta modelo Codex (gpt-*, codex-*): roteia para `codex_provider`
- Caso padrão: mesmo fluxo do OpenAI com converters Anthropic

---

## Módulo: `converters` 🟢

**Arquivos:** `kiro/converters_core.py`, `kiro/converters_openai.py`, `kiro/converters_anthropic.py`

### Formato Unificado (converters_core.py)

**Dataclasses:**
- `UnifiedMessage` — role, content, tool_calls, tool_results, images
- `UnifiedTool` — name, description, input_schema
- `ThinkingConfig` — enabled, budget_tokens
- `KiroPayloadResult` — payload, tool_documentation

### Pipeline de Construção do Payload Kiro

```
messages → strip_tool_content (se sem tools) → ensure_assistant_before_tool_results
         → merge_adjacent_messages → ensure_first_message_is_user
         → normalize_message_roles → ensure_alternating_roles
         → build_kiro_history → assemble payload
```

**Regras de validação Kiro API (fixes documentados):**
- Primeira mensagem deve ser `user` (issue #60)
- Roles alternados user/assistant obrigatórios (issue #64)
- `required: []` removido dos schemas JSON (causa 400)
- `additionalProperties` removido dos schemas JSON (causa 400)
- Tool names limitados a 64 caracteres
- Payload máximo ~615KB (causa 400 com mensagem enganosa)
- Tool descriptions longas movidas para system prompt (referência por nome)

**Fake Reasoning (inject_thinking_tags):**
- Injeta `<thinking_mode>enabled</thinking_mode>` + `<max_thinking_length>N</max_thinking_length>` no início da última mensagem do usuário
- Desabilitado quando há tools (quebra tool use)
- Budget cap: `min(budget, FAKE_REASONING_BUDGET_CAP)` para evitar consumo excessivo

**Conversão de imagens:**
- OpenAI: `image_url` com data URL → `{format, source: {bytes}}`
- Anthropic: `image` com source base64 → `{format, source: {bytes}}`
- Imagens vão em `userInputMessage.images` (não em `userInputMessageContext`)

**Conversão de tool_results:**
- Unified: `{type, tool_use_id, content}` → Kiro: `{content: [{text}], status: "success", toolUseId}`

---

## Módulo: `streaming` 🟢

**Arquivos:** `kiro/streaming_core.py`, `kiro/streaming_openai.py`, `kiro/streaming_anthropic.py`

### Fluxo de Streaming

```
Kiro SSE (AWS Event Stream) → AwsEventStreamParser → KiroEvent
                                                          ↓
                                                   ThinkingParser (FSM)
                                                          ↓
                                              stream_kiro_to_openai / stream_kiro_to_anthropic
                                                          ↓
                                                   SSE para o cliente
```

**Dataclasses:**
- `KiroEvent` — type, content, thinking_content, tool_use, usage, context_usage_percentage
- `StreamResult` — content, thinking_content, tool_calls, usage, context_usage_percentage

**Retry de primeiro token:**
- `stream_with_first_token_retry`: se modelo não responder em `FIRST_TOKEN_TIMEOUT` segundos, cancela e retenta
- Máximo `FIRST_TOKEN_MAX_RETRIES` tentativas
- Transparente para o cliente (apenas delay)

**Contagem de tokens:**
- Kiro retorna `contextUsagePercentage` (% do contexto usado)
- `prompt_tokens = (contextUsagePercentage/100) * max_input_tokens - completion_tokens`
- Fallback: tiktoken para completion_tokens

---

## Módulo: `parsers` 🟢

**Arquivos:** `kiro/parsers.py`

### Classe `AwsEventStreamParser`

Parser de stream binário AWS Event Stream.

**Padrões de eventos reconhecidos:**
- `{"content":` → content (texto da resposta)
- `{"toolUseId":` → tool_start (início de tool call)
- `{"name":` → tool_start (alternativo)
- `{"input":` → tool_input (continuação de argumentos)
- `{"stop":` → tool_stop (fim de tool call)
- `{"usage":` → usage (créditos consumidos)
- `{"contextUsagePercentage":` → context_usage

**Algoritmo de parsing de tool calls:**
- Kiro envia snapshots cumulativos de argumentos (não deltas)
- Detecção: se novo input começa com `current_args[:-1]`, é snapshot → delta = `new[len(old)-1:]`
- Caso contrário: concatena (comportamento legado)
- Deduplicação: por ID (mantém com mais argumentos) + por name+args

**Diagnóstico de truncamento:**
- Detecta JSON incompleto: chaves/colchetes desbalanceados, string não fechada
- Marca `_truncation_detected` no tool call para o sistema de recovery

**Função `parse_bracket_tool_calls`:**
- Parseia formato `[Called func_name with args: {...}]` (alguns modelos retornam assim)
- Usa `find_matching_brace` para parsing correto de JSON aninhado

---

## Módulo: `parsers` — ThinkingParser 🟢

**Arquivo:** `kiro/thinking_parser.py`

### FSM de Estados

```
PRE_CONTENT → (tag detectada) → IN_THINKING → (closing tag) → STREAMING
     ↓ (buffer > limite ou não é prefixo de tag)
  STREAMING
```

**Estados:**
- `PRE_CONTENT` — bufferiza até encontrar tag ou exceder limite
- `IN_THINKING` — bufferiza conteúdo de thinking, envia com cautela (mantém últimos `max_tag_length` chars)
- `STREAMING` — passa conteúdo diretamente

**Tags suportadas:** `<thinking>`, `<think>`, `<reasoning>`, `<thought>`

**Modos de handling:**
- `as_reasoning_content` — extrai para campo `reasoning_content` (padrão)
- `remove` — descarta completamente
- `pass` — passa com tags originais
- `strip_tags` — remove tags, mantém conteúdo

---

## Módulo: `model_resolver` 🟢

**Arquivos:** `kiro/model_resolver.py`, `kiro/cache.py`

### Pipeline de Resolução (4 camadas)

```
external_name → [0] alias → [1] normalize → [2] cache → [3] hidden → [4] passthrough
```

**Normalizações aplicadas:**
- `claude-haiku-4-5` → `claude-haiku-4.5` (dash→dot para versão minor)
- `claude-haiku-4-5-20251001` → `claude-haiku-4.5` (remove sufixo de data)
- `claude-haiku-4-5-latest` → `claude-haiku-4.5` (remove "latest")
- `claude-sonnet-4-20250514` → `claude-sonnet-4` (sem minor, remove data)
- `claude-3-7-sonnet` → `claude-3.7-sonnet` (formato legado)
- `claude-4.5-opus-high` → `claude-opus-4.5` (formato invertido com sufixo)

**Princípio gateway:** nunca rejeita modelo desconhecido — passa para Kiro decidir.

**Aliases:** mapeamento customizável (padrão: `auto-kiro` → `auto` para evitar conflito com Cursor IDE).

**Hidden models:** modelos que funcionam mas não aparecem em `/ListAvailableModels` (ex: `claude-3.7-sonnet`).

---

## Módulo: `http_client` 🟢

**Arquivo:** `kiro/http_client.py`

### Classe `KiroHttpClient`

**Dois modos:**
- Per-request: cria e gerencia próprio `httpx.AsyncClient` (streaming — evita CLOSE_WAIT leak)
- Shared: usa cliente compartilhado da aplicação (non-streaming — connection pooling)

**Retry automático:**
- 403: `force_refresh()` + retry imediato
- 429: backoff exponencial (1s, 2s, 4s)
- 5xx: backoff exponencial
- Timeouts: backoff exponencial, com classificação de erro amigável

**Importante:** `FIRST_TOKEN_TIMEOUT` NÃO é aplicado aqui — é aplicado em `streaming_core.py` via `asyncio.wait_for()`.

---

## Módulo: `truncation` 🟢

**Arquivos:** `kiro/truncation_recovery.py`, `kiro/truncation_state.py`

**Problema:** Kiro API trunca tool calls grandes mid-stream (issue #56).

**Solução:**
1. `AwsEventStreamParser` detecta JSON incompleto → marca `_truncation_detected`
2. `truncation_state.py` armazena info de truncamento por `tool_use_id`
3. Na próxima requisição, `routes_openai.py` verifica cada `tool_result` — se truncado, injeta mensagem sintética de aviso
4. Para conteúdo truncado: injeta mensagem de usuário sintética após mensagem do assistente

**Mensagens sintéticas:**
- Tool result: `[API Limitation] Your tool call was truncated...`
- Conteúdo: `[System Notice] Your previous response was truncated...`

---

## Módulo: `payload_guards` 🟢

**Arquivo:** `kiro/payload_guards.py`

**Problema:** Kiro API rejeita payloads > ~615KB com erro enganoso "Improperly formed request."

**Algoritmo de trim:**
1. Remove `toolUses: []` vazios
2. Remove pares user/assistant mais antigos (2 entradas por vez) até caber
3. Alinha início ao `userInputMessage`
4. Repara `toolResults` órfãos (sem `toolUseId` correspondente no assistente anterior)

---

## Módulo: `mcp_tools` 🟢

**Arquivo:** `kiro/mcp_tools.py`

**Dois caminhos para web_search:**

**Path A (nativo Anthropic):** cliente envia `web_search` como server-side tool → gateway detecta → chama MCP API diretamente → emula SSE Anthropic/OpenAI → retorna ao cliente (bypassa Kiro generateAssistantResponse).

**Path B (emulação MCP):** auto-injeta `web_search` como tool regular → modelo decide chamar → gateway intercepta tool call → chama MCP API → retorna resultado.

**MCP API:**
- URL: `{q_host}/mcp`
- Método: POST JSON-RPC 2.0
- `result.content[0].text` é uma **string JSON** (não objeto) — parsing duplo necessário

---

## Módulo: `codex_provider` 🟢

**Arquivos:** `kiro/codex_provider.py`, `kiro/codex_auth.py`

**Propósito:** Roteia modelos `gpt-*` e `codex-*` para o endpoint privado do Codex CLI (ChatGPT OAuth).

**Endpoint:** `POST https://chatgpt.com/backend-api/codex/responses`

**Tradução de formato:**
- Anthropic Messages → OpenAI Responses API
- `system` → campo `instructions` + mensagem `developer`
- `tool_use` blocks → `function_call` items
- `tool_result` blocks → `function_call_output` items
- Resposta SSE Codex → SSE Anthropic (tradução evento a evento)

**Modelos disponíveis:** gpt-5.5, gpt-5.4, gpt-5.4-mini, gpt-5.3-codex-spark

---

## Módulo: `errors` 🟢

**Arquivos:** `kiro/network_errors.py`, `kiro/kiro_errors.py`, `kiro/exceptions.py`, `kiro/account_errors.py`

**Classificação de erros de conta (`account_errors.py`):**
- `ErrorType.FATAL` — erro do cliente (400, 401, 403, 404, 422): retorna imediatamente
- `ErrorType.RECOVERABLE` — erro de servidor/rede (429, 500, 502, 503, 504): tenta próxima conta

**Erros de rede (`network_errors.py`):**
- Classifica `httpx.TimeoutException` e `httpx.RequestError` em categorias amigáveis
- Fornece `user_message`, `troubleshooting_steps`, `suggested_http_code`

**Erros Kiro (`kiro_errors.py`):**
- Enriquece erros vagos da Kiro API com mensagens acionáveis
- "Improperly formed request" → diagnóstico específico baseado em `reason`

---

## Módulo: `debug` 🟢

**Arquivos:** `kiro/debug_logger.py`, `kiro/debug_middleware.py`

**Modos:** `off` (padrão), `errors` (salva apenas falhas 4xx/5xx), `all` (salva tudo)

**Middleware:** captura request body ANTES da validação Pydantic (permite logar erros 422).

**Arquivos gerados em `debug_logs/`:**
- `request_body.json` — corpo da requisição original
- `kiro_request_body.json` — payload enviado à Kiro API
- `response_stream_raw.txt` — stream bruto da Kiro API
- `app_logs.txt` — logs da aplicação para a requisição

---

## Módulo: `tokenizer` 🟢

**Arquivo:** `kiro/tokenizer.py`

- Usa `tiktoken` com encoding `cl100k_base` (Claude-compatible)
- Correção Claude: multiplica por 1.1 (Claude usa ~10% mais tokens que GPT para mesmo texto)
- `count_message_tokens`: conta tokens de lista de mensagens incluindo overhead de role
- `count_tokens`: conta tokens de string simples

---

## Módulo: `utils` 🟢

**Arquivo:** `kiro/utils.py`

**Funções principais:**
- `generate_conversation_id()` — UUID v4 para conversationId Kiro
- `generate_tool_call_id()` — `call_{hex24}` para tool calls
- `generate_completion_id()` — `chatcmpl_{hex24}` para respostas OpenAI
- `get_machine_fingerprint()` — hash SHA-256 do hostname para User-Agent
- `get_kiro_headers(auth_manager, token)` — headers padrão para Kiro API

---

## Módulo: `config` 🟢

**Arquivo:** `kiro/config.py`

**Configurações principais:**

| Variável | Padrão | Descrição |
|---|---|---|
| `PROXY_API_KEY` | `my-super-secret-password-123` | Senha do proxy |
| `FAKE_REASONING_ENABLED` | `true` | Injeção de thinking tags |
| `FAKE_REASONING_MAX_TOKENS` | `4000` | Budget padrão de thinking |
| `FAKE_REASONING_BUDGET_CAP` | `10000` | Cap máximo de budget |
| `TRUNCATION_RECOVERY` | `true` | Recovery automático de truncamento |
| `ACCOUNT_SYSTEM` | `false` | Sistema multi-conta com failover |
| `TOOL_DESCRIPTION_MAX_LENGTH` | `10000` | Limite de descrição de tool |
| `KIRO_MAX_PAYLOAD_BYTES` | `600000` | Limite de payload (~600KB) |
| `AUTO_TRIM_PAYLOAD` | `false` | Auto-trim de histórico |
| `FIRST_TOKEN_TIMEOUT` | `15` | Timeout para primeiro token (s) |
| `STREAMING_READ_TIMEOUT` | `300` | Timeout entre chunks (s) |
| `WEB_SEARCH_ENABLED` | `true` | Auto-inject web_search tool |
| `CODEX_ENABLED` | `true` | Provider Codex CLI |
| `CODEX_REASONING_EFFORT` | `low` | Esforço de raciocínio Codex |

**Nota:** `_get_raw_env_value` lê `.env` sem processar escape sequences (fix para paths Windows com `\a`, `\n`, etc.).
