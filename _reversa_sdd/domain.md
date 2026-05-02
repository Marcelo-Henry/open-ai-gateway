# Glossário de Domínio — Kiro Gateway

> Escala de confiança: 🟢 CONFIRMADO | 🟡 INFERIDO | 🔴 LACUNA

---

## Entidades Principais

### Gateway
🟢 Servidor proxy FastAPI que traduz requisições entre formatos de API (OpenAI/Anthropic) e o formato nativo da Kiro API. Não armazena estado de conversação — é stateless por requisição.

### Kiro API
🟢 API da Amazon Q Developer (AWS CodeWhisperer) que processa requisições de LLM. Usa formato AWS Event Stream (binário) para streaming. Endpoint principal: `https://q.{region}.amazonaws.com/generateAssistantResponse`.

### Account
🟢 Conjunto de credenciais Kiro associadas a um usuário/perfil. Cada account tem seu próprio `KiroAuthManager`, `ModelInfoCache` e `ModelResolver`. Identificada pelo caminho do arquivo de credenciais.

### Access Token
🟢 Token JWT de curta duração (tipicamente 1h) usado para autenticar requisições à Kiro API. Obtido via refresh token. Armazenado em memória e persistido em arquivo JSON ou SQLite.

### Refresh Token
🟢 Token de longa duração usado para obter novos access tokens. Pode ser do tipo KIRO_DESKTOP (endpoint `prod.region.auth.desktop.kiro.dev`) ou AWS_SSO_OIDC (endpoint `oidc.region.amazonaws.com`).

### Profile ARN
🟢 Amazon Resource Name que identifica o perfil CodeWhisperer do usuário. Formato: `arn:aws:codewhisperer:us-east-1:...`. Incluído no payload de cada requisição à Kiro API.

### KiroPayload
🟢 Estrutura de dados no formato nativo da Kiro API enviada para `generateAssistantResponse`. Contém `conversationState` com `currentMessage` (userInputMessage) e `history` (chatTriggerType=INLINE_CHAT).

### UnifiedMessage
🟢 Formato interno de mensagem usado como intermediário durante conversão. Normaliza diferenças entre formatos OpenAI e Anthropic antes de construir o KiroPayload.

### Circuit Breaker
🟢 Padrão de resiliência implementado no `AccountManager`. Estados: CLOSED (funcionando), OPEN (em cooldown com backoff exponencial), HALF-OPEN (testando recuperação). Backoff: `60s * 2^(failures-1)`, cap em 1 dia.

### Sticky Behavior
🟢 Preferência por reutilizar a última account bem-sucedida. Implementado via índice global `_current_account_index` compartilhado entre todos os modelos.

### Failover
🟢 Processo de tentar a próxima account disponível quando a atual falha. Controlado por `exclude_accounts` passado recursivamente para `get_next_account`.

### Model Resolution
🟢 Pipeline de 4 camadas para mapear nomes de modelos do cliente para o formato Kiro: (1) normalização, (2) cache dinâmico, (3) modelos ocultos, (4) passthrough.

### Model Normalization
🟢 Transformação de nomes de modelos via 5 padrões regex: dash→dot para versão minor, strip de sufixo de data, formato legado, formato invertido, e passthrough.

### Fake Reasoning / Extended Thinking
🟢 Injeção de tags `<thinking_mode>enabled</thinking_mode>` e `<max_thinking_length>N</max_thinking_length>` no início da mensagem do usuário para simular extended thinking na Kiro API, que não suporta o parâmetro nativamente.

### Thinking Block
🟢 Bloco de raciocínio interno do modelo delimitado por `<parameter name="content">` tags. Extraído pelo `ThinkingParser` FSM e retornado como `thinking` content block no formato Anthropic ou `reasoning_content` no formato OpenAI.

### Truncation Recovery
🟢 Mecanismo para detectar e notificar truncamento de tool call payloads pela Kiro API (Issue #56). Modifica `tool_result` com conteúdo truncado para incluir aviso ao modelo.

### AWS Event Stream
🟢 Formato binário de streaming da AWS usado pela Kiro API. Cada frame tem header com `:event-type` e body JSON. Parseado pelo `AwsEventStreamParser`.

### MCP Tool / Web Search
🟢 Ferramenta de busca web via Kiro MCP API. Dois caminhos: Path A (requisição nativa Anthropic com `web_search` tool, bypassa `generateAssistantResponse`) e Path B (auto-injeção da tool `web_search` em requisições normais).

### Codex Provider
🟢 Roteamento alternativo para modelos `gpt-*` e `codex-*` via endpoint privado do ChatGPT (`chatgpt.com/backend-api/codex/responses`). Usa OAuth do ChatGPT, não credenciais Kiro.

### Debug Logger
🟢 Sistema de logging de requisições/respostas completas em disco. Modos: `off` (padrão), `errors` (apenas falhas 4xx/5xx), `all` (todas as requisições). Salva em `debug_logs/`.

### PROXY_API_KEY
🟢 Chave de API configurada pelo operador do gateway. Usada para autenticar clientes. Verificada via header `Authorization: Bearer {key}` (OpenAI) ou `x-api-key: {key}` (Anthropic).

### Tool Description Overflow
🟢 Mecanismo que move descrições de tools muito longas (> `TOOL_DESCRIPTION_MAX_LENGTH`) para o system prompt, substituindo a descrição original por uma referência. Contorna limite de tamanho da Kiro API.

### Auto-Trim Payload
🟢 Remoção automática de pares de mensagens antigas quando o payload excede `KIRO_MAX_PAYLOAD_BYTES` (~615KB). Remove pares user+assistant do início do histórico preservando a mensagem atual.

### Cumulative Snapshot
🟢 Comportamento da Kiro API de retornar o JSON completo acumulado de argumentos de tool call a cada evento, em vez de deltas incrementais. O `AwsEventStreamParser` detecta e deduplica via ID + hash de nome+args.

---

## Regras de Negócio

### RN-001 — Autenticação do Cliente
🟢 Todo endpoint requer autenticação via `PROXY_API_KEY`. OpenAI usa `Authorization: Bearer {key}`. Anthropic aceita `x-api-key: {key}` ou `Authorization: Bearer {key}`. Retorna 401 se inválido.

### RN-002 — Resolução de Modelo
🟢 Modelos desconhecidos são passados diretamente à Kiro API (princípio passthrough). O gateway não rejeita modelos — a Kiro API é o árbitro final.

### RN-003 — Normalização de Nomes de Modelos
🟢 `claude-haiku-4-5-20251001` → `claude-haiku-4.5`. Dash antes de dígito único vira ponto (versão minor). Sufixo de data (8 dígitos) é removido. Formato invertido (`4-5-claude-haiku`) é reordenado.

### RN-004 — Primeira Mensagem Deve Ser User
🟢 A Kiro API exige que a primeira mensagem do histórico seja do role `user`. Se a conversa começar com `assistant`, um user message vazio é inserido no início (Issue #60).

### RN-005 — Roles Alternados Obrigatórios
🟢 A Kiro API exige alternância estrita user/assistant. Mensagens consecutivas do mesmo role são separadas por uma mensagem sintética do role oposto (Issue #64).

### RN-006 — Roles Desconhecidos Viram User
🟢 Roles diferentes de `user` e `assistant` são normalizados para `user` (Issue #64).

### RN-007 — Tool Content Sem Tools Definidas
🟢 Se a requisição não define tools, todo conteúdo de tool_call e tool_result é convertido para texto plano via `strip_all_tool_content`.

### RN-008 — Circuit Breaker Single Account
🟢 Com apenas uma account configurada, o Circuit Breaker é desativado. A account é sempre retornada independente de falhas — o usuário deve ver os erros reais da Kiro API.

### RN-009 — Backoff Exponencial de Account
🟢 Após falha: cooldown = `60s * 2^(failures-1)`, cap em 1 dia (1440x). 10% de chance de retry probabilístico mesmo em cooldown.

### RN-010 — Sticky Account Global
🟢 O índice de account atual é global (não por modelo). Após sucesso, o índice é atualizado para a account bem-sucedida. Todos os modelos usam a mesma account preferida.

### RN-011 — Refresh Token SQLite Read-Merge-Write
🟢 Ao salvar credenciais no SQLite, o gateway lê o estado atual, faz merge com os novos valores, e escreve de volta. Evita sobrescrever campos atualizados por outro processo (Issue #131).

### RN-012 — Degradação Graciosa de Token
🟢 Se o refresh falhar com 400 mas o access token atual ainda for válido, o gateway continua usando o token existente em vez de falhar (graceful degradation).

### RN-013 — Detecção de Região
🟢 A região é detectada a partir das credenciais (campo `region` ou `startUrl`). Fallback para `us-east-1`. Endpoints de auth variam por região (Issues #58, #132, #133).

### RN-014 — Per-Request Client para Streaming
🟢 Requisições de streaming usam um `httpx.AsyncClient` por requisição (não compartilhado) para evitar vazamento de conexões CLOSE_WAIT em desconexões de VPN (Issue #38, #54).

### RN-015 — Truncation Recovery
🟢 Se um `tool_result` contém marcador de truncamento da Kiro API, o conteúdo é modificado para incluir aviso explícito ao modelo sobre o truncamento (Issue #56).

### RN-016 — Payload Size Guard
🟢 Se `AUTO_TRIM_PAYLOAD=true` e o payload excede `KIRO_MAX_PAYLOAD_BYTES`, pares de mensagens antigas são removidos do início do histórico até o payload caber.

### RN-017 — Tool Name Validation
🟢 Nomes de tools devem ter no máximo 64 caracteres. Violações levantam `ValueError` com lista das tools problemáticas antes de enviar à Kiro API.

### RN-018 — System Prompt no Primeiro User Message
🟢 A Kiro API não tem campo dedicado para system prompt. O system prompt é prefixado ao conteúdo do primeiro user message do histórico.

### RN-019 — Fake Reasoning Injection
🟢 Se `FAKE_REASONING_ENABLED=true` e a requisição não tem tools, tags de thinking mode são injetadas no início da mensagem do usuário atual (não no histórico).

### RN-020 — Modelos Ocultos
🟢 Modelos em `HIDDEN_MODELS` (config.py) são incluídos na resolução mas não listados em `/v1/models`. Modelos em `HIDDEN_FROM_LIST` são excluídos da listagem pública.
