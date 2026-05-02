# ThinkingParser — FSM de Extração de Thinking Blocks

## Visão Geral
Máquina de estados finita (FSM) de 3 estados que extrai blocos de raciocínio interno (`thinking blocks`) do stream de texto da Kiro API. Usa buffering cauteloso para detectar tags que chegam fragmentadas entre chunks HTTP.

## Responsabilidades
- Detectar tags de abertura/fechamento de thinking blocks no stream de texto
- Acumular conteúdo de thinking blocks separadamente do conteúdo normal
- Emitir conteúdo de thinking no formato configurado (4 modos)
- Lidar com tags fragmentadas entre chunks via buffer cauteloso

## Interface

```python
class ThinkingParser:
    def __init__(
        self,
        mode: str = "strip",
        # "as_thinking_block"    → emite como content block Anthropic
        # "as_reasoning_content" → emite como reasoning_content OpenAI
        # "strip"                → descarta thinking, emite apenas conteúdo normal
        # "passthrough"          → mantém tags como texto literal
        max_tag_length: int = 100,
    )

    def feed(self, chunk: str) -> Tuple[Optional[str], Optional[str]]
        # Retorna: (conteudo_normal, conteudo_thinking)
        # Qualquer dos dois pode ser None se não houver conteúdo desse tipo no chunk.

    def flush(self) -> Tuple[Optional[str], Optional[str]]
        # Força emissão do buffer restante ao final do stream.

    @property
    def state(self) -> str
        # "PRE_CONTENT" | "IN_THINKING" | "STREAMING"
```

## Regras de Negócio

- 🟢 **RN-TP-01**: FSM tem 3 estados: PRE_CONTENT → IN_THINKING → STREAMING
- 🟢 **RN-TP-02**: Buffer cauteloso mantém apenas os últimos `max_tag_length` chars para detectar tags fragmentadas
- 🟢 **RN-TP-03**: Uma vez em STREAMING, nunca volta para PRE_CONTENT ou IN_THINKING (estado terminal por requisição)
- 🟢 **RN-TP-04**: Modo `as_reasoning_content` usado para OpenAI (logs de 2026-04-27 confirmam)
- 🟢 **RN-TP-05**: Modo `as_thinking_block` usado para Anthropic
- 🟢 **RN-TP-06**: Tags de abertura suportadas: `<thinking>`, `<think>`, `<reasoning>`, `<thought>` (configurável via `FAKE_REASONING_OPEN_TAGS` em config.py:487)
- 🟢 **RN-TP-07**: Tag de fechamento derivada automaticamente da tag de abertura detectada: `<thinking>` → `</thinking>`, `<think>` → `</think>`, etc.

## Fluxo Principal

1. `feed(chunk)` recebe texto do stream
2. Estado PRE_CONTENT: acumula no buffer, verifica se tag de abertura está presente
3. Se tag detectada → transição para IN_THINKING, emite conteúdo pré-tag como normal
4. Estado IN_THINKING: acumula no `thinking_buffer`
5. Se tag de fechamento detectada → extrai thinking, transição para STREAMING
6. Emite thinking no formato configurado pelo modo
7. Estado STREAMING: emite conteúdo diretamente sem buffering

## Fluxos Alternativos

- **Tag fragmentada entre chunks**: buffer retém últimos `max_tag_length` chars até tag completa
- **Sem thinking block**: transição direta PRE_CONTENT → STREAMING no primeiro conteúdo normal
- **Modo strip**: thinking block extraído mas descartado (não emitido)
- **Modo passthrough**: tags mantidas como texto literal, sem extração

## Dependências

- `kiro/streaming_core.py` — instancia e usa ThinkingParser
- `kiro/config.py` — `THINKING_TAG_MAX_LENGTH`

## Requisitos Não Funcionais

| Tipo | Requisito inferido | Evidência no código | Confiança |
|------|--------------------|---------------------|-----------|
| Corretude | Buffer cauteloso evita perda de tags fragmentadas | `kiro/thinking_parser.py:228` | 🟢 |
| Performance | Buffer limitado a max_tag_length chars (não acumula todo o stream) | `kiro/thinking_parser.py` | 🟢 |

## Critérios de Aceitação

```gherkin
Dado stream com thinking block completo em um único chunk
Quando feed() é chamado
Então retorna (conteudo_normal, conteudo_thinking) separados

Dado stream onde a tag de abertura chega fragmentada entre dois chunks
Quando feed() é chamado para cada chunk
Então a tag é detectada corretamente no segundo chunk via buffer

Dado modo="strip"
Quando thinking block é detectado
Então conteudo_thinking retornado é None (descartado)

Dado stream sem nenhum thinking block
Quando feed() é chamado
Então transição direta para STREAMING, todo conteúdo retornado como normal
```

## Prioridade

| Requisito | MoSCoW | Justificativa |
|-----------|--------|---------------|
| Extração de thinking blocks | Must | Sem isso, thinking aparece como texto literal na resposta |
| Buffer cauteloso para tags fragmentadas | Must | Chunks HTTP podem fragmentar tags |
| Modo as_reasoning_content (OpenAI) | Should | Necessário para clientes OpenAI com thinking |
| Modo as_thinking_block (Anthropic) | Should | Necessário para clientes Anthropic com thinking |
| Modo strip | Could | Útil para descartar thinking quando não necessário |

## Rastreabilidade de Código

| Arquivo | Função / Classe | Cobertura |
|---------|-----------------|-----------|
| `kiro/thinking_parser.py` | `ThinkingParser` | 🟢 |
| `kiro/thinking_parser.py:228` | `_handle_pre_content` | 🟢 |
| `kiro/streaming_core.py:147` | inicialização com modo configurado | 🟢 |
