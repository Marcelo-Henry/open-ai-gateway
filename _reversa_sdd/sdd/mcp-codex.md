# MCP Tools e Codex Provider — Roteamentos Alternativos

## Visão Geral
Dois módulos de roteamento alternativo que desviam do fluxo principal da Kiro API: `mcp_tools.py` gerencia web search via Kiro MCP API (Path A nativo e Path B auto-inject), e `codex_provider.py` roteia modelos `gpt-*`/`codex-*` para o endpoint privado do ChatGPT.

---

## MCP Tools (`mcp_tools.py`)

### Responsabilidades
- Detectar requisições de web search nativo Anthropic (Path A)
- Executar web search via Kiro MCP API (bypassa `generateAssistantResponse`)
- Auto-injetar tool `web_search` em requisições normais (Path B)
- Fazer double JSON parse do resultado MCP (resultado é JSON dentro de JSON)

### Interface

```python
async def handle_native_web_search(
    request: AnthropicMessagesRequest,
    account: Account,
) -> AnthropicResponse
    # Path A: executa web search nativo, retorna resposta formatada.

def inject_web_search_tool(
    tools: Optional[List],
) -> List
    # Path B: adiciona tool web_search à lista existente.
```

### Regras de Negócio

- 🟢 **RN-MCP-01**: Path A ativado quando requisição tem tool `web_search` e é detectada como nativa Anthropic
- 🟢 **RN-MCP-02**: Path A bypassa `generateAssistantResponse` — vai direto para endpoint MCP da Kiro
- 🟢 **RN-MCP-03**: Resultado MCP requer double JSON parse: `result.content[0].text` é string JSON que precisa ser parseada novamente
- 🟢 **RN-MCP-04**: Path B (auto-inject) ativado por `WEB_SEARCH_ENABLED=true` em `routes_anthropic.py:367`
- 🟡 **RN-MCP-05**: Endpoint MCP: `q.{region}.amazonaws.com/mcp/...` (formato exato 🔴 LACUNA)

### Critérios de Aceitação

```gherkin
Dado requisição com tool web_search nativa (Path A)
Quando handle_native_web_search() é chamado
Então executa via Kiro MCP API sem passar por generateAssistantResponse

Dado resultado MCP com content[0].text sendo string JSON
Quando o resultado é processado
Então double JSON parse é aplicado corretamente

Dado WEB_SEARCH_ENABLED=true e requisição sem tools
Quando POST /v1/messages é chamado
Então tool web_search é adicionada automaticamente (Path B)
```

### Prioridade

| Requisito | MoSCoW | Justificativa |
|-----------|--------|---------------|
| Double JSON parse | Must | Sem isso, resultado MCP é ilegível |
| Path A (nativo) | Should | Necessário para web search nativo Anthropic |
| Path B (auto-inject) | Could | Feature opcional, desativada por padrão |

### Rastreabilidade

| Arquivo | Função / Classe | Cobertura |
|---------|-----------------|-----------|
| `kiro/mcp_tools.py` | `handle_native_web_search` | 🟢 |
| `kiro/routes_anthropic.py:367` | auto-inject Path B | 🟢 |

---

## Codex Provider (`codex_provider.py`)

### Responsabilidades
- Detectar modelos `gpt-*` e `codex-*` nas requisições
- Traduzir formato Anthropic/OpenAI para Responses API do ChatGPT
- Enviar para endpoint privado `chatgpt.com/backend-api/codex/responses`
- Carregar system prompt de URL externa (GitHub) no startup

### Interface

```python
async def stream_codex_response(
    request: Union[ChatCompletionRequest, AnthropicMessagesRequest],
    auth_token: str,
) -> AsyncIterator[str]
    # Retorna SSE stream no formato do request original.
```

### Regras de Negócio

- 🟢 **RN-CP-01**: Ativado para modelos com prefixo `gpt-` ou `codex-`
- 🟢 **RN-CP-02**: Usa `CODEX_AUTH_TOKEN` (OAuth ChatGPT) — completamente separado das credenciais Kiro
- 🟢 **RN-CP-03**: Endpoint: `chatgpt.com/backend-api/codex/responses` (endpoint privado, não documentado)
- 🟡 **RN-CP-04**: System prompt carregado de URL no GitHub no startup e cacheado em memória
- 🔴 **RN-CP-05**: Formato exato da Responses API e mapeamento de campos não totalmente documentado

### Critérios de Aceitação

```gherkin
Dado model="gpt-4o" na requisição
Quando a route processa
Então delega para codex_provider, não para Kiro API

Dado CODEX_AUTH_TOKEN não configurado
Quando model="gpt-4o" é solicitado
Então retorna erro de configuração (não tenta usar credenciais Kiro)
```

### Prioridade

| Requisito | MoSCoW | Justificativa |
|-----------|--------|---------------|
| Roteamento para gpt-*/codex-* | Should | Feature útil mas não afeta fluxo Kiro principal |
| Tradução de formato | Should | Necessário para compatibilidade com Responses API |
| Cache de system prompt | Could | Otimização — poderia buscar a cada requisição |

### Rastreabilidade

| Arquivo | Função / Classe | Cobertura |
|---------|-----------------|-----------|
| `kiro/codex_provider.py` | `stream_codex_response` | 🟢 |
| `kiro/routes_anthropic.py` | detecção de modelo Codex | 🟢 |
