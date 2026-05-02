# User Stories — Kiro Gateway

> Escala de confiança: 🟢 CONFIRMADO | 🟡 INFERIDO | 🔴 LACUNA

---

## Épico 1: Uso Básico do Gateway

### US-001 — Completar uma conversa via API OpenAI
**Como** desenvolvedor usando Claude Code ou outro cliente OpenAI-compatível,  
**Quero** enviar mensagens para `POST /v1/chat/completions`,  
**Para** obter respostas do modelo Kiro sem precisar gerenciar autenticação AWS.

**Critérios de Aceitação:**
```gherkin
Dado que tenho PROXY_API_KEY configurada no cliente
Quando envio POST /v1/chat/completions com model e messages válidos
Então recebo resposta no formato ChatCompletionResponse com status 200

Dado que envio stream=true
Quando a requisição é processada
Então recebo SSE stream com chunks delta no formato OpenAI

Dado que envio API key inválida
Quando a requisição chega ao gateway
Então recebo 401 imediatamente sem processar o request
```

**Prioridade**: Must  
**Rastreabilidade**: `kiro/routes_openai.py:159`

---

### US-002 — Completar uma conversa via API Anthropic
**Como** desenvolvedor usando SDK Anthropic ou Cursor,  
**Quero** enviar mensagens para `POST /v1/messages`,  
**Para** usar modelos Kiro com a interface Anthropic que já conheço.

**Critérios de Aceitação:**
```gherkin
Dado que tenho x-api-key configurada no cliente
Quando envio POST /v1/messages com model, messages e max_tokens
Então recebo resposta no formato AnthropicResponse com status 200

Dado que uso Authorization: Bearer em vez de x-api-key
Quando a requisição chega ao gateway
Então é autenticada com sucesso (ambos os formatos aceitos)

Dado que envio stream=true
Quando a requisição é processada
Então recebo SSE stream com eventos no formato Anthropic (message_start, content_block_delta, etc.)
```

**Prioridade**: Must  
**Rastreabilidade**: `kiro/routes_anthropic.py:122`

---

### US-003 — Descobrir modelos disponíveis
**Como** desenvolvedor configurando meu cliente,  
**Quero** chamar `GET /v1/models`,  
**Para** saber quais modelos estão disponíveis no gateway.

**Critérios de Aceitação:**
```gherkin
Dado que tenho múltiplas accounts configuradas
Quando chamo GET /v1/models
Então recebo lista agregada de modelos de todas as accounts

Dado que um modelo está em HIDDEN_FROM_LIST
Quando chamo GET /v1/models
Então esse modelo não aparece na lista (mas ainda funciona se usado diretamente)
```

**Prioridade**: Should  
**Rastreabilidade**: `kiro/routes_openai.py:121`

---

## Épico 2: Resiliência e Failover

### US-004 — Failover automático entre accounts
**Como** operador do gateway com múltiplas contas Kiro configuradas,  
**Quero** que o gateway tente automaticamente outra conta quando uma falha,  
**Para** garantir disponibilidade mesmo com falhas individuais de conta.

**Critérios de Aceitação:**
```gherkin
Dado que tenho 3 accounts configuradas e a primeira retorna 500
Quando envio uma requisição
Então o gateway tenta a segunda account automaticamente

Dado que todas as accounts estão em cooldown (Circuit Breaker)
Quando envio uma requisição
Então recebo 503 "No accounts available"

Dado que uma account estava em cooldown e o timeout expirou
Quando envio uma requisição
Então o gateway testa essa account novamente (Half-Open)
```

**Prioridade**: Must  
**Rastreabilidade**: `kiro/account_manager.py:597`, `kiro/routes_anthropic.py:673`

---

### US-005 — Recuperação automática de token expirado
**Como** usuário do gateway em sessão longa (> 1h),  
**Quero** que o gateway renove automaticamente o access token quando expirar,  
**Para** não precisar reiniciar o gateway ou reconfigurar credenciais.

**Critérios de Aceitação:**
```gherkin
Dado que o access token está prestes a expirar (< 5min)
Quando uma nova requisição chega
Então o gateway renova o token antes de enviar à Kiro API

Dado que a Kiro API retorna 403 (token expirado inesperadamente)
Quando o gateway recebe o 403
Então faz force_refresh() e tenta a requisição novamente

Dado que o refresh falha mas o token atual ainda é válido
Quando o gateway tenta renovar
Então usa o token existente com graceful degradation (sem falhar)
```

**Prioridade**: Must  
**Rastreabilidade**: `kiro/auth.py:867`, `kiro/http_client.py:227`

---

## Épico 3: Funcionalidades Avançadas

### US-006 — Usar extended thinking (fake reasoning)
**Como** desenvolvedor que quer raciocínio estendido do modelo,  
**Quero** enviar `thinking: {type: "enabled"}` na requisição Anthropic,  
**Para** receber blocos de thinking na resposta mesmo que a Kiro API não suporte nativamente.

**Critérios de Aceitação:**
```gherkin
Dado que FAKE_REASONING_ENABLED=true e envio thinking.type="enabled"
Quando a requisição é processada
Então tags <thinking_mode> são injetadas na mensagem do usuário

Dado que o modelo retorna conteúdo com thinking blocks
Quando o stream é processado
Então recebo content blocks do tipo "thinking" na resposta Anthropic

Dado que a requisição tem tools definidas
Quando thinking está habilitado
Então thinking NÃO é injetado (incompatível com tool use)
```

**Prioridade**: Should  
**Rastreabilidade**: `kiro/converters_core.py:417`, `kiro/thinking_parser.py`

---

### US-007 — Web search automático
**Como** desenvolvedor usando Claude Code com web search,  
**Quero** que o gateway injete automaticamente a tool web_search,  
**Para** que o modelo possa buscar informações na web sem configuração manual.

**Critérios de Aceitação:**
```gherkin
Dado que WEB_SEARCH_ENABLED=true e a requisição não tem tools
Quando envio POST /v1/messages
Então a tool web_search é automaticamente adicionada à requisição (Path B)

Dado que a requisição já tem a tool web_search definida (Path A nativo)
Quando o modelo chama web_search
Então o gateway roteia para a Kiro MCP API diretamente
```

**Prioridade**: Could  
**Rastreabilidade**: `kiro/routes_anthropic.py:367`, `kiro/mcp_tools.py`

---

### US-008 — Usar modelos GPT/Codex via gateway
**Como** desenvolvedor que quer usar modelos OpenAI via interface unificada,  
**Quero** enviar requisições com model="gpt-4o" ou "codex-*",  
**Para** usar o ChatGPT via o mesmo gateway sem configuração adicional.

**Critérios de Aceitação:**
```gherkin
Dado que envio model="gpt-4o" em POST /v1/chat/completions
Quando a requisição é processada
Então é roteada para chatgpt.com/backend-api/codex/responses (não para Kiro API)

Dado que envio model="claude-sonnet-4-6" (não Codex)
Quando a requisição é processada
Então é roteada para a Kiro API normalmente
```

**Prioridade**: Could  
**Rastreabilidade**: `kiro/routes_anthropic.py`, `kiro/codex_provider.py`

---

## Épico 4: Operação e Diagnóstico

### US-009 — Debugar requisições com falha
**Como** operador do gateway investigando um problema,  
**Quero** habilitar DEBUG_MODE="errors" no .env,  
**Para** ter logs completos de requisições e respostas com falha em disco.

**Critérios de Aceitação:**
```gherkin
Dado que DEBUG_MODE="errors"
Quando uma requisição retorna 4xx ou 5xx
Então um arquivo JSON é salvo em debug_logs/ com headers, body e resposta completos

Dado que DEBUG_MODE="off" (padrão)
Quando qualquer requisição é processada
Então nenhum arquivo é salvo em debug_logs/

Dado que DEBUG_MODE="all"
Quando qualquer requisição é processada (sucesso ou falha)
Então um arquivo JSON é salvo em debug_logs/
```

**Prioridade**: Should  
**Rastreabilidade**: `kiro/debug_logger.py`, `kiro/debug_middleware.py`

---

### US-010 — Contar tokens antes de enviar
**Como** desenvolvedor gerenciando custos e limites de contexto,  
**Quero** chamar `POST /v1/messages/count_tokens`,  
**Para** estimar tokens de entrada sem fazer uma chamada real à Kiro API.

**Critérios de Aceitação:**
```gherkin
Dado uma requisição com messages e system prompt
Quando chamo POST /v1/messages/count_tokens
Então recebo {"input_tokens": N} sem fazer chamada à Kiro API

Dado que a estimativa usa tiktoken cl100k_base
Quando o resultado é comparado com o uso real reportado pela Kiro API
Então a diferença é aceitável (estimativa, não exata)
```

**Prioridade**: Could  
**Rastreabilidade**: `kiro/routes_anthropic.py:999`, `kiro/tokenizer.py`
