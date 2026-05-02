# AwsEventStreamParser — Parser de Stream Binário AWS

## Visão Geral
Parseia o formato binário AWS Event Stream retornado pela Kiro API, extraindo eventos tipados (content, tool_use, usage, stop). Implementa detecção de cumulative snapshots para argumentos de tool calls e deduplicação por ID para evitar eventos duplicados.

## Responsabilidades
- Parsear frames binários do protocolo AWS Event Stream
- Extrair tipo de evento do header `:event-type`
- Emitir `KiroEvent`s tipados a partir do body JSON de cada frame
- Detectar e desduplicar cumulative snapshots de argumentos de tool calls
- Diagnosticar truncamento de JSON em argumentos de tool calls

## Interface

**Classe principal:**
```python
class AwsEventStreamParser:
    def feed(self, chunk: bytes) -> List[KiroEvent]
        # Alimenta chunk binário, retorna lista de eventos prontos.
        # Pode retornar lista vazia se frame ainda incompleto.

    def reset(self) -> None
        # Reseta estado interno para nova requisição.
```

**Eventos emitidos:**
```python
KiroEvent(type="content", content="texto parcial")
KiroEvent(type="tool_start", tool_id="id", tool_name="nome")
KiroEvent(type="tool_input", tool_id="id", tool_args='{"partial": "json"}')
KiroEvent(type="tool_stop", tool_id="id")
KiroEvent(type="usage", input_tokens=N, output_tokens=M)
KiroEvent(type="stop", stop_reason="end_turn")
```

## Regras de Negócio

- 🟢 **RN-AP-01**: Cada frame AWS Event Stream tem header com `:event-type` e body JSON
- 🟢 **RN-AP-02**: A Kiro API retorna argumentos de tool calls como snapshots cumulativos (JSON completo a cada evento), não como deltas incrementais
- 🟢 **RN-AP-03**: Deduplicação por `tool_id + hash(name + args)` — eventos idênticos são descartados
- 🟢 **RN-AP-04**: Frames podem chegar fragmentados entre chunks — parser mantém buffer interno até frame completo
- 🟡 **RN-AP-05**: JSON truncado em argumentos de tool call é detectado e logado como diagnóstico de truncamento upstream
- 🟡 **RN-AP-06**: Tool calls em formato bracket `[{...}]` (em vez de `{...}`) são normalizados antes do parse

## Fluxo Principal

1. `feed(chunk)` recebe bytes do stream HTTP
2. Acumula no buffer interno
3. Tenta extrair frames completos do buffer (header length + body length + checksum)
4. Para cada frame completo:
   a. Extrai `:event-type` do header
   b. Parseia body como JSON
   c. Mapeia para `KiroEvent` conforme tipo
   d. Aplica deduplicação para eventos `tool_input`
5. Retorna lista de `KiroEvent`s prontos

## Fluxos Alternativos

- **Frame incompleto**: acumula no buffer, retorna lista vazia, aguarda próximo chunk
- **Cumulative snapshot detectado**: compara hash com último evento do mesmo tool_id; descarta se igual
- **JSON em formato bracket**: extrai objeto do array antes de parsear
- **JSON truncado**: loga diagnóstico, emite evento parcial com flag de truncamento

## Dependências

- Protocolo AWS Event Stream (binário, sem dependência de biblioteca externa)
- `kiro/config.py` — constantes de tamanho de frame

## Requisitos Não Funcionais

| Tipo | Requisito inferido | Evidência no código | Confiança |
|------|--------------------|---------------------|-----------|
| Corretude | Deduplicação evita tool args duplicados no output | `kiro/parsers.py:474` | 🟢 |
| Robustez | Buffer interno lida com fragmentação de chunks | `kiro/parsers.py` | 🟢 |
| Diagnóstico | JSON truncado logado para diagnóstico | `kiro/parsers.py:474` | 🟡 |

## Critérios de Aceitação

```gherkin
Dado um chunk que contém um frame AWS Event Stream completo
Quando feed() é chamado
Então retorna lista com KiroEvent correspondente

Dado um chunk que contém apenas metade de um frame
Quando feed() é chamado
Então retorna lista vazia e acumula no buffer

Dado dois eventos tool_input consecutivos com mesmo tool_id e mesmos args (cumulative snapshot)
Quando feed() processa ambos
Então apenas um KiroEvent é emitido (deduplicação)

Dado argumentos de tool call em formato "[{...}]"
Quando feed() processa o frame
Então extrai o objeto do array e parseia corretamente
```

## Prioridade

| Requisito | MoSCoW | Justificativa |
|-----------|--------|---------------|
| Parse de frames AWS Event Stream | Must | Sem isso, nenhuma resposta da Kiro API é legível |
| Deduplicação de cumulative snapshots | Must | Sem isso, tool args aparecem duplicados no output |
| Buffer para frames fragmentados | Must | Chunks HTTP podem chegar fragmentados |
| Diagnóstico de JSON truncado | Could | Útil para debug mas não bloqueia funcionalidade |

## Rastreabilidade de Código

| Arquivo | Função / Classe | Cobertura |
|---------|-----------------|-----------|
| `kiro/parsers.py` | `AwsEventStreamParser` | 🟢 |
| `kiro/parsers.py:474` | detecção de truncamento e deduplicação | 🟢 |
