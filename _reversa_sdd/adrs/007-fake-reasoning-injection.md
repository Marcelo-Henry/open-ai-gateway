# ADR-007: Fake Reasoning via Injeção de Tags

**Status**: Aceito  
**Data**: 2025  
**Contexto**: kiro/converters_core.py:417, kiro/config.py (FAKE_REASONING_ENABLED)

---

## Contexto

A Kiro API não suporta o parâmetro `thinking` do formato Anthropic nativamente. Clientes como Claude Code enviam `"thinking": {"type": "enabled", "budget_tokens": N}` esperando receber blocos de raciocínio (`thinking` content blocks) na resposta.

A Kiro API, no entanto, suporta extended thinking quando provocada via tags especiais no conteúdo da mensagem do usuário.

## Decisão

Quando `FAKE_REASONING_ENABLED=true` (padrão: false) e a requisição não tem tools definidas, injetar tags de thinking mode no início da mensagem do usuário atual:

```
<thinking_mode>enabled</thinking_mode>
<max_thinking_length>{budget}</max_thinking_length>

{mensagem original do usuário}
```

O `ThinkingParser` FSM então extrai os blocos de thinking da resposta e os retorna no formato correto (Anthropic `thinking` block ou OpenAI `reasoning_content`).

A injeção é feita apenas na mensagem atual (não no histórico) e apenas quando não há tools (tools e thinking simultâneos causam problemas na Kiro API).

## Consequências

**Positivas**:
- Habilita extended thinking para clientes que o solicitam
- Transparente para o cliente: recebe blocos `thinking` no formato esperado

**Negativas**:
- Modifica o conteúdo da mensagem do usuário (viola transparência)
- Desativado por padrão — requer opt-in explícito
- Incompatível com tool use simultâneo
- Comportamento dependente de feature não documentada da Kiro API

**Neutras**:
- 🟢 `FAKE_REASONING_ENABLED=true` por padrão (quando env var não definida — string vazia não está na lista de valores falsos). Para desativar: `FAKE_REASONING=false`
- Budget de tokens usa valor do cliente ou fallback configurável
