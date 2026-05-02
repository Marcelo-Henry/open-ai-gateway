# streaming_core — Motor de Streaming

## Visão Geral
Orquestra o processamento do stream binário AWS Event Stream retornado pela Kiro API, coordenando o `AwsEventStreamParser` e o `ThinkingParser` FSM. Gerencia first-token timeout com retry e emite `KiroEvent`s normalizados para os formatadores OpenAI e Anthropic.

## Responsabilidades
- Receber chunks binários do stream HTTP e alimentar o `AwsEventStreamParser`
- Passar conteúdo textual pelo `ThinkingParser` para extração de thinking blocks
- Implementar first-token timeout com retry automático
- Emitir `KiroEvent`s tipados para os formatadores de saída
- Detectar truncamento de stream (ausência de `stop_reason`)
- Classificar erros de rede em categorias user-friendly

## Interface

**Função principal:**
```python
async def parse_kiro_stream(
    response_stream: AsyncIterator[bytes],
    thinking_mode: str = "strip",        # "as_thinking_block" | "as_reasoning_content" | "strip" | "passthrough"
    first_token_timeout: float = 15.0,
    max_retries: int = 3,
    retry_callback: Optional[Callable] = None,
) -> AsyncIterator[KiroEvent]
```

**KiroEvent (tipos emitidos):**
```python
@dataclass
class KiroEvent:
    type: str   # "content" | "tool_start" | "tool_input" | "tool_stop" | "usage" | "stop" | "thinking"
    content: Optional[str] = None
    tool_id: Optional[str] = None
    tool_name: Optional[str] = None
    tool_args: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    stop_reason: Optional[str] = None
    thinking: Optional[str] = None
```

## Regras de Negócio

- 🟢 **RN-SC-01**: First-token timeout padrão de 15s — se nenhum token chegar nesse tempo, faz retry
- 🟢 **RN-SC-02**: Retry de first-token usa `retry_callback` para criar nova requisição HTTP
- 🟢 **RN-SC-03**: Após `max_retries` tentativas sem primeiro token, propaga `TimeoutError`
- 🟢 **RN-SC-04**: `ThinkingParser` inicializado com modo configurado — `as_reasoning_content` para OpenAI, `as_thinking_block` para Anthropic
- 🟢 **RN-SC-05**: Stream sem `stop_reason` ao final indica truncamento pela Kiro API
- 🟡 **RN-SC-06**: Erros de rede durante streaming são classificados via `network_errors.py` antes de propagar

## Fluxo Principal

1. Inicializa `AwsEventStreamParser` e `ThinkingParser` com modo configurado
2. Aguarda primeiro chunk com timeout de `first_token_timeout` segundos
3. Ao receber primeiro chunk, loga "First token received"
4. Para cada chunk: alimenta `AwsEventStreamParser.feed(chunk)`
5. Parser emite `KiroEvent`s conforme frames AWS são completados
6. Eventos de conteúdo textual passam pelo `ThinkingParser.feed(content)`
7. ThinkingParser emite conteúdo normal ou thinking blocks conforme estado FSM
8. Eventos de tool_use, usage e stop são emitidos diretamente
9. Ao final do stream, verifica presença de `stop_reason`
10. Se ausente → emite evento de truncamento

## Fluxos Alternativos

- **First-token timeout**: chama `retry_callback()` para nova requisição, reinicia parser
- **Esgotamento de retries**: propaga `TimeoutError` ao caller
- **Erro de rede durante stream**: classifica via `network_errors.py`, propaga exceção tipada
- **Thinking block detectado**: ThinkingParser extrai e emite como `KiroEvent(type="thinking")`
- **Stream truncado**: emite evento especial de truncamento para notificar o cliente

## Dependências

- `kiro/parsers.py` — `AwsEventStreamParser` para frames binários AWS
- `kiro/thinking_parser.py` — `ThinkingParser` FSM para extração de thinking
- `kiro/network_errors.py` — classificação de erros de rede
- `kiro/config.py` — `FIRST_TOKEN_TIMEOUT`, `MAX_RETRIES`

## Requisitos Não Funcionais

| Tipo | Requisito inferido | Evidência no código | Confiança |
|------|--------------------|---------------------|-----------|
| Performance | First-token timeout de 15s evita espera indefinida | `kiro/streaming_core.py:155` | 🟢 |
| Disponibilidade | Retry automático em timeout de primeiro token | `kiro/streaming_core.py` — `stream_with_first_token_retry` | 🟢 |
| Observabilidade | Log de "First token received" para diagnóstico de latência | `kiro/streaming_core.py:160` | 🟢 |

## Critérios de Aceitação

```gherkin
Dado um stream que retorna o primeiro token dentro de 15s
Quando parse_kiro_stream() é chamado
Então emite KiroEvents normalmente sem retry

Dado um stream que não retorna nenhum token em 15s
Quando parse_kiro_stream() é chamado
Então chama retry_callback() e tenta novamente

Dado que max_retries tentativas falharam por timeout
Quando parse_kiro_stream() é chamado
Então propaga TimeoutError ao caller

Dado um stream com thinking block (<parameter name="content">...</parameter>)
Quando thinking_mode="as_thinking_block"
Então emite KiroEvent(type="thinking") com o conteúdo extraído

Dado um stream que termina sem stop_reason
Quando parse_kiro_stream() finaliza
Então emite evento de truncamento
```

## Prioridade

| Requisito | MoSCoW | Justificativa |
|-----------|--------|---------------|
| parse_kiro_stream() | Must | Toda resposta da Kiro API passa por aqui |
| First-token timeout + retry | Must | Sem isso, requisições travadas bloqueiam indefinidamente |
| Integração com AwsEventStreamParser | Must | Sem parser, stream binário é ilegível |
| ThinkingParser integration | Should | Necessário apenas quando thinking habilitado |
| Detecção de truncamento | Should | Melhora UX mas não bloqueia funcionalidade |

## Rastreabilidade de Código

| Arquivo | Função / Classe | Cobertura |
|---------|-----------------|-----------|
| `kiro/streaming_core.py:147` | `parse_kiro_stream` | 🟢 |
| `kiro/streaming_core.py:155` | first-token timeout logic | 🟢 |
| `kiro/streaming_core.py` | `stream_with_first_token_retry` | 🟢 |
