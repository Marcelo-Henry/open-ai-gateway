# ADR-002: Truncation Recovery para Tool Call Payloads

**Status**: Aceito  
**Data**: 2025 (Issue #56)  
**Contexto**: kiro/truncation_recovery.py:26, kiro/routes_openai.py:513

---

## Contexto

A Kiro API trunca silenciosamente tool call payloads grandes no meio do stream, sem retornar um `stop_reason` de erro. O modelo recebe uma resposta incompleta e não tem como saber que o conteúdo foi cortado, levando a comportamentos imprevisíveis nas chamadas subsequentes.

O problema é especialmente grave porque o cliente (ex: Claude Code) pode continuar a conversa assumindo que o tool result foi processado completamente, quando na verdade foi truncado.

## Decisão

Implementar um módulo `truncation_recovery.py` que:

1. **Detecta** `tool_result` com conteúdo marcado como truncado pela Kiro API
2. **Modifica** o conteúdo do `tool_result` para incluir aviso explícito ao modelo:
   ```
   [TRUNCATED - the original content was too large and was cut off by the API.
    The model should be aware that this result is incomplete.]
   ```
3. **Aplica** a modificação antes de enviar o payload à Kiro API (no pipeline de conversão)

O módulo é ativado automaticamente — não requer configuração do usuário.

## Consequências

**Positivas**:
- O modelo recebe informação explícita sobre o truncamento e pode reagir adequadamente
- Evita que o modelo continue a conversa com dados incompletos sem saber
- Comportamento transparente: o cliente vê o aviso no histórico da conversa

**Negativas**:
- Modifica o conteúdo original do `tool_result` (viola o princípio de transparência mínima)
- Depende de marcadores específicos da Kiro API que podem mudar sem aviso

**Neutras**:
- Não afeta requisições sem tool calls
- Não afeta tool results que não foram truncados
