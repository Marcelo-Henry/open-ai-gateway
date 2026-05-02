# Routes — Endpoints HTTP (OpenAI e Anthropic)

## Visão Geral
Camada de entrada HTTP do gateway. Expõe endpoints compatíveis com OpenAI (`routes_openai.py`) e Anthropic (`routes_anthropic.py`), gerenciando autenticação de clientes, validação de requests, orquestração do fluxo de requisição e formatação de respostas.

## Responsabilidades
- Autenticar clientes via `PROXY_API_KEY`
- Validar requests via modelos Pydantic
- Aplicar pré-processamentos (truncation recovery, web_search auto-inject)
- Orquestrar AccountManager → Converter → HTTPClient → StreamingEngine
- Implementar loop de failover multi-account
- Retornar respostas em formato streaming (SSE) ou não-streaming

## Interface

### OpenAI (`routes_openai.py`)

```
GET  /v1/models
     Auth: Authorization: Bearer {PROXY_API_KEY}
     Response: ModelList (JSON)

POST /v1/chat/completions
     Auth: Authorization: Bearer {PROXY_API_KEY}
     Body: ChatCompletionRequest (JSON)
     Response: ChatCompletionResponse (JSON) ou SSE stream
```

### Anthropic (`routes_anthropic.py`)

```
POST /v1/messages
     Auth: x-api-key: {PROXY_API_KEY} ou Authorization: Bearer {PROXY_API_KEY}
     Body: AnthropicMessagesRequest (JSON)
     Response: AnthropicResponse (JSON) ou SSE stream

POST /v1/messages/count_tokens
     Auth: x-api-key: {PROXY_API_KEY} ou Authorization: Bearer {PROXY_API_KEY}
     Body: AnthropicMessagesRequest (JSON)
     Response: {"input_tokens": N}
```

### Públicos (sem auth)

```
GET  /
     Response: {"status": "ok", "version": "..."}

GET  /health
     Response: {"status": "healthy", "accounts": N, "models": [...]}
```

## Regras de Negócio

- 🟢 **RN-RT-01**: OpenAI usa `Authorization: Bearer {key}`; Anthropic aceita `x-api-key: {key}` ou `Authorization: Bearer {key}`
- 🟢 **RN-RT-02**: Auth inválida retorna 401 imediatamente, sem processar o request
- 🟢 **RN-RT-03**: Truncation Recovery aplicado em `tool_result` antes da conversão (routes_openai.py:513)
- 🟢 **RN-RT-04**: Web search auto-injetado se `WEB_SEARCH_ENABLED=true` (padrão: **True** — ativo por padrão, `kiro/config.py:518`)
- 🟢 **RN-RT-05**: Loop de failover: se account falha, `report_failure()` + `get_next_account(exclude=tried)` até esgotar contas
- 🟢 **RN-RT-06**: Se `ACCOUNT_SYSTEM=false`, usa `get_first_account()` (modo legado sem failover)
- 🟢 **RN-RT-07**: Modelos `gpt-*` e `codex-*` são roteados para `codex_provider` em vez da Kiro API
- 🟢 **RN-RT-08**: Path A de web_search (nativo Anthropic) bypassa `generateAssistantResponse` e vai direto para MCP
- 🟢 **RN-RT-09**: Streaming usa `StreamingResponse` com `media_type="text/event-stream"`
- 🟢 **RN-RT-10**: Non-streaming coleta stream completo via `collect_stream_response` antes de retornar

## Fluxo Principal (POST /v1/messages)

1. Verifica `x-api-key` ou `Authorization: Bearer` → 401 se inválido
2. Parseia body como `AnthropicMessagesRequest` via Pydantic → 422 se inválido
3. Detecta se é modelo Codex → rota para `codex_provider`
4. Detecta se é web_search nativo (Path A) → rota para `mcp_tools`
5. Auto-injeta web_search tool se `WEB_SEARCH_ENABLED=true` (Path B)
6. `account_manager.get_next_account(model)` → 503 se None
7. `build_kiro_payload_anthropic(request, account)` → KiroPayload
8. `http_client.request_with_retry(url, payload, stream=request.stream)`
9. Se streaming → `StreamingResponse(stream_kiro_to_anthropic(response))`
10. Se non-streaming → `collect_anthropic_response(response)` → JSON

## Fluxos Alternativos

- **Falha de account (4xx/5xx)**: `report_failure()`, tenta próxima account via `exclude_accounts`
- **Todas accounts esgotadas**: retorna 503 "No accounts available"
- **Modelo Codex**: delega para `codex_provider.stream_codex_response()`
- **Web search Path A**: delega para `mcp_tools.handle_native_web_search()`
- **Erro de rede**: classificado via `network_errors.py`, retorna erro user-friendly

## Dependências

- `kiro/account_manager.py` — seleção de conta
- `kiro/converters_openai.py` / `kiro/converters_anthropic.py` — conversão de payload
- `kiro/streaming_openai.py` / `kiro/streaming_anthropic.py` — formatação de stream
- `kiro/http_client.py` — transporte HTTP
- `kiro/mcp_tools.py` — web search nativo
- `kiro/codex_provider.py` — modelos gpt-*/codex-*
- `kiro/truncation_recovery.py` — pré-processamento de tool_results
- `kiro/models_openai.py` / `kiro/models_anthropic.py` — validação Pydantic
- `kiro/config.py` — `PROXY_API_KEY`, `WEB_SEARCH_ENABLED`, `ACCOUNT_SYSTEM`

## Requisitos Não Funcionais

| Tipo | Requisito inferido | Evidência no código | Confiança |
|------|--------------------|---------------------|-----------|
| Segurança | Autenticação obrigatória em todos os endpoints funcionais | `routes_openai.py:64`, `routes_anthropic.py:70` | 🟢 |
| Disponibilidade | Loop de failover multi-account | `routes_anthropic.py:673` | 🟢 |
| Performance | Streaming via SSE evita buffering de respostas grandes | `routes_openai.py:598`, `routes_anthropic.py:808` | 🟢 |

## Critérios de Aceitação

```gherkin
Dado uma requisição com PROXY_API_KEY inválida
Quando POST /v1/messages é chamado
Então retorna 401 com mensagem de erro

Dado uma requisição válida com stream=true
Quando POST /v1/chat/completions é chamado
Então retorna StreamingResponse com Content-Type: text/event-stream

Dado que a primeira account falha com 500
Quando POST /v1/messages é chamado com múltiplas accounts configuradas
Então tenta a próxima account automaticamente

Dado que todas as accounts estão indisponíveis
Quando POST /v1/messages é chamado
Então retorna 503 "No accounts available"

Dado modelo "gpt-4o" na requisição
Quando POST /v1/chat/completions é chamado
Então roteia para codex_provider, não para Kiro API
```

## Prioridade

| Requisito | MoSCoW | Justificativa |
|-----------|--------|---------------|
| Autenticação de clientes | Must | Sem isso, qualquer um pode usar o gateway |
| POST /v1/chat/completions | Must | Endpoint principal para clientes OpenAI |
| POST /v1/messages | Must | Endpoint principal para clientes Anthropic |
| Loop de failover | Must | Garante disponibilidade com múltiplas accounts |
| Streaming SSE | Must | Clientes como Claude Code dependem de streaming |
| GET /v1/models | Should | Necessário para descoberta de modelos |
| Web search auto-inject | Could | Feature opcional, desativada por padrão |
| POST /v1/messages/count_tokens | Could | Raramente usado, não afeta fluxo principal |

## Rastreabilidade de Código

| Arquivo | Função / Classe | Cobertura |
|---------|-----------------|-----------|
| `kiro/routes_openai.py:64` | `verify_api_key` | 🟢 |
| `kiro/routes_openai.py:121` | `GET /v1/models` | 🟢 |
| `kiro/routes_openai.py:159` | `POST /v1/chat/completions` | 🟢 |
| `kiro/routes_openai.py:510` | loop de failover OpenAI | 🟢 |
| `kiro/routes_openai.py:598` | per-request client streaming | 🟢 |
| `kiro/routes_anthropic.py:70` | `verify_anthropic_api_key` | 🟢 |
| `kiro/routes_anthropic.py:122` | `POST /v1/messages` | 🟢 |
| `kiro/routes_anthropic.py:367` | web_search auto-inject | 🟢 |
| `kiro/routes_anthropic.py:673` | loop de failover Anthropic | 🟢 |
| `kiro/routes_anthropic.py:808` | per-request client streaming | 🟢 |
| `kiro/routes_anthropic.py:999` | `POST /v1/messages/count_tokens` | 🟢 |
