# ADR-003: Normalização de Roles de Mensagem para Kiro API

**Status**: Aceito  
**Data**: 2025 (Issue #60, #64)  
**Contexto**: kiro/converters_core.py:1164, 1471, 1474, 1479

---

## Contexto

A Kiro API tem restrições estritas sobre a estrutura de mensagens que não são documentadas explicitamente:

1. **Issue #60**: A Kiro API rejeita conversas que começam com uma mensagem do role `assistant`. Clientes como Claude Code podem enviar históricos que começam com `assistant` (ex: quando o usuário continua uma conversa existente).

2. **Issue #64**: A Kiro API exige alternância estrita entre roles `user` e `assistant`. Mensagens consecutivas do mesmo role causam erro "Improperly formed request". Além disso, roles desconhecidos (ex: `system`, `tool`, `function`) não são aceitos.

Esses erros retornam a mensagem genérica "Improperly formed request" sem indicar a causa específica, tornando o diagnóstico difícil.

## Decisão

Implementar três transformações no pipeline de normalização de mensagens em `converters_core.py`:

1. **`ensure_first_message_is_user`**: Se a primeira mensagem for `assistant`, insere um user message vazio (`""`) antes dela.

2. **`normalize_message_roles`**: Converte qualquer role desconhecido (não `user` ou `assistant`) para `user`.

3. **`ensure_alternating_roles`**: Detecta mensagens consecutivas do mesmo role e insere uma mensagem sintética do role oposto entre elas.

As transformações são aplicadas em sequência, após merge de mensagens adjacentes.

## Consequências

**Positivas**:
- Elimina classe inteira de erros "Improperly formed request" relacionados a roles
- Compatibilidade com clientes que enviam estruturas de conversa não-padrão
- Comportamento previsível e documentado

**Negativas**:
- Modifica a estrutura da conversa enviada pelo cliente (mensagens sintéticas inseridas)
- Mensagens sintéticas vazias podem confundir o modelo em edge cases
- Roles desconhecidos são silenciosamente convertidos para `user` sem aviso ao cliente

**Neutras**:
- Transformações são idempotentes (aplicar duas vezes tem o mesmo efeito que uma)
- Não afeta conversas bem-formadas (user/assistant alternados, começando com user)
