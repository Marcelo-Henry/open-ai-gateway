# Dicionário de Dados — codex-gateway

> Gerado pelo Reversa Archaeologist em 2026-05-01
> Escala de confiança: 🟢 CONFIRMADO | 🟡 INFERIDO | 🔴 LACUNA

---

## credentials.json 🟢

Arquivo de configuração de contas. Gerado/migrado do `.env` na inicialização.

| Campo | Tipo | Obrigatório | Valores | Descrição |
|---|---|---|---|---|
| `type` | string | ✅ | `json`, `sqlite`, `refresh_token` | Tipo de credencial |
| `path` | string | Condicional | caminho de arquivo ou pasta | Obrigatório para `json` e `sqlite` |
| `refresh_token` | string | Condicional | token string | Obrigatório para `refresh_token` |
| `profile_arn` | string | ❌ | ARN string | ARN do perfil AWS CodeWhisperer |
| `region` | string | ❌ | `us-east-1`, etc. | Região SSO |
| `api_region` | string | ❌ | `us-east-1`, etc. | Override de região da API Q |
| `enabled` | bool | ❌ | `true`/`false` | Padrão: `true` |

---

## state.json 🟢

Estado persistido do AccountManager. Salvo atomicamente a cada 10s (se dirty).

| Campo | Tipo | Descrição |
|---|---|---|
| `current_account_index` | int | Índice global da conta atual (sticky) |
| `accounts` | object | Mapa account_id → estado da conta |
| `accounts[id].failures` | int | Contador de falhas consecutivas |
| `accounts[id].last_failure_time` | float | Timestamp Unix da última falha |
| `accounts[id].models_cached_at` | float | Timestamp Unix do último cache de modelos |
| `accounts[id].stats.total_requests` | int | Total de requisições |
| `accounts[id].stats.successful_requests` | int | Requisições bem-sucedidas |
| `accounts[id].stats.failed_requests` | int | Requisições com falha |
| `model_to_accounts` | object | Mapa model_id → lista de account_ids |

---

## SQLite `auth_kv` table 🟢

Banco de dados do kiro-cli. Lido (e opcionalmente escrito) pelo gateway.

| Chave | Campos do JSON | Descrição |
|---|---|---|
| `kirocli:social:token` | access_token, refresh_token, expires_at, region, profile_arn, scopes | Login social |
| `kirocli:odic:token` | access_token, refresh_token, expires_at, region, profile_arn, scopes | AWS SSO OIDC |
| `codewhisperer:odic:token` | access_token, refresh_token, expires_at, region, profile_arn | Legado |
| `kirocli:odic:device-registration` | client_id, client_secret, region | Registro de dispositivo |
| `codewhisperer:odic:device-registration` | client_id, client_secret, region | Registro legado |

**Nota:** `expires_at` está em formato ISO 8601 com nanosegundos (9 dígitos) — truncado para 6 dígitos (microsegundos) antes do parse.

---

## SQLite `state` table 🟢

| Chave | Campos do JSON | Descrição |
|---|---|---|
| `api.codewhisperer.profile` | arn | ARN do perfil para auto-detecção de região API |

---

## Kiro API Payload (`conversationState`) 🟢

Payload enviado para `POST /generateAssistantResponse`.

```json
{
  "conversationState": {
    "chatTriggerType": "MANUAL",
    "conversationId": "uuid-v4",
    "currentMessage": {
      "userInputMessage": {
        "content": "string",
        "modelId": "claude-sonnet-4.5",
        "origin": "AI_EDITOR",
        "images": [{"format": "jpeg", "source": {"bytes": "base64"}}],
        "userInputMessageContext": {
          "tools": [{"toolSpecification": {"name": "str", "description": "str", "inputSchema": {"json": {}}}}],
          "toolResults": [{"content": [{"text": "str"}], "status": "success", "toolUseId": "str"}]
        }
      }
    },
    "history": [
      {"userInputMessage": {"content": "str", "modelId": "str", "origin": "AI_EDITOR"}},
      {"assistantResponseMessage": {"content": "str", "toolUses": [{"name": "str", "input": {}, "toolUseId": "str"}]}}
    ]
  },
  "profileArn": "arn:aws:codewhisperer:..."
}
```

---

## Kiro API Response (AWS Event Stream) 🟢

Eventos SSE retornados por `/generateAssistantResponse`.

| Padrão JSON | Tipo de Evento | Campos |
|---|---|---|
| `{"content": "..."}` | content | `content`: texto da resposta |
| `{"toolUseId": "...", "name": "...", "input": "..."}` | tool_start | `toolUseId`, `name`, `input` |
| `{"input": "..."}` | tool_input | `input`: snapshot cumulativo de argumentos |
| `{"stop": true}` | tool_stop | `stop`: boolean |
| `{"usage": N}` | usage | `usage`: créditos consumidos |
| `{"contextUsagePercentage": N}` | context_usage | `contextUsagePercentage`: float 0-100 |

---

## OpenAI ChatCompletionRequest 🟢

Campos relevantes do modelo Pydantic `ChatCompletionRequest`.

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `model` | string | ✅ | Nome do modelo |
| `messages` | list[ChatMessage] | ✅ | Histórico de mensagens |
| `stream` | bool | ❌ | Padrão: `false` |
| `tools` | list[Tool] | ❌ | Ferramentas disponíveis |
| `max_tokens` | int | ❌ | Limite de tokens de saída |
| `max_completion_tokens` | int | ❌ | Alias de max_tokens |
| `reasoning_effort` | string | ❌ | `none`, `low`, `medium`, `high`, `xhigh` |
| `temperature` | float | ❌ | Ignorado (Kiro não suporta) |

---

## Anthropic MessagesRequest 🟢

Campos relevantes do modelo Pydantic `AnthropicMessagesRequest`.

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `model` | string | ✅ | Nome do modelo |
| `messages` | list[AnthropicMessage] | ✅ | Histórico de mensagens |
| `max_tokens` | int | ✅ | Limite de tokens de saída |
| `system` | string ou list | ❌ | System prompt (suporta cache_control) |
| `tools` | list[AnthropicTool] | ❌ | Ferramentas disponíveis |
| `stream` | bool | ❌ | Padrão: `false` |
| `thinking` | dict | ❌ | `{"type": "enabled"/"disabled", "budget_tokens": N}` |

---

## UnifiedMessage (formato interno) 🟢

| Campo | Tipo | Descrição |
|---|---|---|
| `role` | string | `user`, `assistant` |
| `content` | Any | Texto ou lista de content blocks |
| `tool_calls` | list[dict] | `[{id, type, function: {name, arguments}}]` |
| `tool_results` | list[dict] | `[{type, tool_use_id, content}]` |
| `images` | list[dict] | `[{media_type, data}]` |

---

## KiroEvent (formato interno de streaming) 🟢

| Campo | Tipo | Descrição |
|---|---|---|
| `type` | string | `content`, `thinking`, `tool_use`, `usage`, `context_usage`, `error` |
| `content` | string | Texto regular |
| `thinking_content` | string | Conteúdo de thinking/reasoning |
| `tool_use` | dict | Tool call completo |
| `usage` | dict | Dados de uso |
| `context_usage_percentage` | float | % do contexto usado |
| `is_first_thinking_chunk` | bool | Primeiro chunk de thinking |
| `is_last_thinking_chunk` | bool | Último chunk de thinking |

---

## ModelResolution (resultado de resolução) 🟢

| Campo | Tipo | Descrição |
|---|---|---|
| `internal_id` | string | ID a enviar para Kiro API |
| `source` | string | `cache`, `hidden`, `passthrough` |
| `original_request` | string | Nome original do cliente |
| `normalized` | string | Nome após normalização |
| `is_verified` | bool | `true` se encontrado em cache/hidden |

---

## PayloadTrimStats 🟢

| Campo | Tipo | Descrição |
|---|---|---|
| `original_bytes` | int | Tamanho original em bytes |
| `final_bytes` | int | Tamanho final em bytes |
| `original_entries` | int | Entradas originais no histórico |
| `final_entries` | int | Entradas após trim |
| `trimmed` | bool | Se houve trim |

---

## Codex Auth (`~/.codex/auth.json`) 🟡

| Campo | Tipo | Descrição |
|---|---|---|
| `accessToken` | string | Token OAuth do ChatGPT |
| `expiresAt` | string | ISO 8601 de expiração |
| `refreshToken` | string | Token de refresh (se disponível) |

---

## MCP Request/Response 🟢

**Request:**
```json
{
  "id": "web_search_tooluse_{22random}_{timestamp_ms}_{8random}",
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {"name": "web_search", "arguments": {"query": "string"}}
}
```

**Response:**
```json
{
  "id": "...",
  "jsonrpc": "2.0",
  "result": {
    "content": [{"type": "text", "text": "{\"results\":[...],\"totalResults\":N,\"query\":\"...\"}"}],
    "isError": false
  }
}
```

**Nota crítica:** `result.content[0].text` é uma **string JSON** que precisa de parse duplo.

**Resultado individual:**
```json
{
  "title": "string",
  "url": "string",
  "snippet": "string",
  "publishedDate": 1234567890000
}
```
(`publishedDate` em milissegundos Unix)
