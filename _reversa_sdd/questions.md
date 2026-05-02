# Lacunas e Perguntas para Validação — Open AI Gateway

> Gerado pelo Revisor em 2026-05-01
> `answer_mode: chat` — perguntas para validação direta com Marcelo

---

## Bloco 1: Comportamento Padrão de FAKE_REASONING

**Contexto**: A spec `sdd/converters-core.md` e `adrs/007-fake-reasoning-injection.md` documentam `FAKE_REASONING_ENABLED=false` como padrão. Porém o código em `kiro/config.py:430` mostra:

```python
_FAKE_REASONING_RAW: str = os.getenv("FAKE_REASONING", "").lower()
FAKE_REASONING_ENABLED: bool = _FAKE_REASONING_RAW not in ("false", "0", "no", "disabled", "off")
```

Isso significa que quando `FAKE_REASONING` não está definida (string vazia `""`), `FAKE_REASONING_ENABLED` é **True** (pois `""` não está na lista de valores falsos).

**Pergunta 1**: O comportamento padrão de `FAKE_REASONING_ENABLED` é **True** (ativo por padrão) ou **False** (inativo por padrão)? O código sugere True, mas a documentação diz False.

---

## Bloco 2: Tags de Thinking

**Contexto**: A spec `sdd/thinking-parser.md` documenta as tags como `<parameter name="content">` e `</parameter>`. Porém o código em `kiro/config.py:487` mostra:

```python
FAKE_REASONING_OPEN_TAGS: List[str] = ["<thinking>", "<think>", "<reasoning>", "<thought>"]
```

As tags reais são `<thinking>`, `<think>`, `<reasoning>`, `<thought>` — não `<parameter name="content">`.

**Pergunta 2**: As tags `<parameter name="content">` eram o formato antigo da Kiro API? As tags atuais são `<thinking>`, `<think>`, `<reasoning>`, `<thought>`?

---

## Bloco 3: WEB_SEARCH_ENABLED padrão

**Contexto**: A spec `sdd/routes.md` documenta `WEB_SEARCH_ENABLED` como "desativado por padrão". O código em `kiro/config.py:518` mostra:

```python
WEB_SEARCH_ENABLED: bool = os.getenv("WEB_SEARCH_ENABLED", "true").lower() in ("true", "1", "yes")
```

O padrão real é **True** (ativo por padrão).

**Pergunta 3**: `WEB_SEARCH_ENABLED` é ativo por padrão (`true`)? Isso significa que todo cliente que não desabilitar explicitamente receberá a tool `web_search` auto-injetada?

---

## Bloco 4: ACCOUNT_SYSTEM padrão

**Contexto**: A spec `sdd/routes.md` menciona `ACCOUNT_SYSTEM` mas não documenta o padrão. O código em `kiro/config.py:527` mostra:

```python
ACCOUNT_SYSTEM: bool = os.getenv("ACCOUNT_SYSTEM", "false").lower() in ("true", "1", "yes")
```

O padrão é **False** — o sistema multi-account está **desativado** por padrão.

**Pergunta 4**: Com `ACCOUNT_SYSTEM=false` (padrão), o gateway usa `get_first_account()` sem failover. Isso é intencional para simplificar a configuração inicial?

---

## Bloco 5: Endpoint MCP para Web Search

**Contexto**: A spec `sdd/mcp-codex.md` marca o endpoint MCP como 🔴 LACUNA. Não foi possível confirmar o endpoint exato pelo código.

**Pergunta 5**: Qual é o endpoint exato da Kiro MCP API para web search (Path A)? É `q.{region}.amazonaws.com/mcp/...` ou outro formato?

---

## Bloco 6: Codex Provider — Formato da Responses API

**Contexto**: A spec `sdd/mcp-codex.md` marca o mapeamento de campos da Responses API como 🔴 LACUNA.

**Pergunta 6**: O Codex Provider (`codex_provider.py`) está em uso ativo em produção? O endpoint `chatgpt.com/backend-api/codex/responses` ainda funciona?
