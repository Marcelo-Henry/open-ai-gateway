# converters_core — Pipeline de Conversão de Payload

## Visão Geral
Núcleo da tradução de mensagens para o formato nativo da Kiro API. Implementa um pipeline de 8 etapas de normalização que garante compatibilidade com as restrições não documentadas da Kiro API, além de funcionalidades opcionais como fake reasoning e auto-trim de payload.

## Responsabilidades
- Normalizar mensagens de qualquer formato (OpenAI/Anthropic) para KiroPayload
- Processar e sanitizar definições de tools (nomes, descrições longas)
- Aplicar 8 transformações de normalização de mensagens em sequência
- Injetar fake reasoning tags quando `FAKE_REASONING_ENABLED=true`
- Construir o `conversationState` final com history e currentMessage
- Aplicar auto-trim quando payload excede `KIRO_MAX_PAYLOAD_BYTES`

## Interface

**Função principal:**
```python
def build_kiro_payload(
    messages: List[UnifiedMessage],
    model: str,
    system_prompt: Optional[str] = None,
    tools: Optional[List[ToolDefinition]] = None,
    thinking_enabled: bool = False,
    thinking_budget: Optional[int] = None,
    images: Optional[List[ImageData]] = None,
) -> KiroPayloadResult

# Retorna:
@dataclass
class KiroPayloadResult:
    payload: Dict[str, Any]   # KiroPayload pronto para envio
    model_id: str             # Modelo normalizado usado
```

**Funções auxiliares exportadas:**
```python
def process_tools_with_long_descriptions(tools, system_prompt) -> Tuple[List, str]
def validate_tool_names(tools: List) -> None          # Raise ValueError se nome > 64 chars
def strip_all_tool_content(messages) -> List          # Converte tool_calls/results para texto
def ensure_assistant_before_tool_results(messages) -> List
def merge_adjacent_messages(messages) -> List
def ensure_first_message_is_user(messages) -> List
def normalize_message_roles(messages) -> List
def ensure_alternating_roles(messages) -> List
def inject_thinking_tags(message, budget) -> Message
def trim_payload_to_limit(payload, max_bytes) -> Dict
```

## Regras de Negócio

- 🟢 **RN-CC-01**: Descrições de tools > `TOOL_DESCRIPTION_MAX_LENGTH` são movidas para o system prompt com referência `[See tool documentation in system prompt]`
- 🟢 **RN-CC-02**: Nomes de tools > 64 chars levantam `ValueError` com lista das tools problemáticas
- 🟢 **RN-CC-03**: Se não há tools definidas, todo conteúdo `tool_use` e `tool_result` é convertido para texto plano
- 🟢 **RN-CC-04**: Se há tools, `tool_result` sem `assistant` precedente recebe um assistant sintético
- 🟢 **RN-CC-05**: Mensagens adjacentes do mesmo role são fundidas em uma única mensagem
- 🟢 **RN-CC-06**: Se a primeira mensagem é `assistant`, um user message vazio é inserido antes (Issue #60)
- 🟢 **RN-CC-07**: Roles desconhecidos são normalizados para `user` (Issue #64)
- 🟢 **RN-CC-08**: Mensagens consecutivas do mesmo role recebem mensagem sintética do role oposto (Issue #64)
- 🟢 **RN-CC-09**: System prompt é prefixado ao conteúdo do primeiro user message do histórico
- 🟢 **RN-CC-10**: Se `FAKE_REASONING_ENABLED=true` (padrão: **True** quando env var não definida) e sem tools, injeta tags de thinking no início da mensagem atual. Tags suportadas: `<thinking>`, `<think>`, `<reasoning>`, `<thought>` (configurável via `FAKE_REASONING_OPEN_TAGS`)
- 🟢 **RN-CC-11**: Se `AUTO_TRIM_PAYLOAD=true` e payload > `KIRO_MAX_PAYLOAD_BYTES`, remove pares user+assistant do início do histórico
- 🟢 **RN-CC-12**: Se a mensagem atual é `assistant`, é adicionada ao histórico e `currentMessage` vira `"Continue"`
- 🟡 **RN-CC-13**: `KIRO_MAX_PAYLOAD_BYTES` default é ~615KB (limite empírico da Kiro API)

## Fluxo Principal

1. `process_tools_with_long_descriptions`: move descrições longas para system prompt
2. `validate_tool_names`: valida comprimento de nomes (max 64 chars)
3. Monta `full_system_prompt`: system_prompt + tool_documentation + thinking_addition + truncation_addition
4. Se sem tools → `strip_all_tool_content`; se com tools → `ensure_assistant_before_tool_results`
5. `merge_adjacent_messages`: funde mensagens consecutivas do mesmo role
6. `ensure_first_message_is_user`: insere user vazio se necessário
7. `normalize_message_roles`: converte roles desconhecidos para `user`
8. `ensure_alternating_roles`: insere mensagens sintéticas entre roles iguais consecutivos
9. Valida que há mensagens — raise `ValueError("No messages to send")` se vazio
10. Separa `history` (todas menos a última) e `current_message` (última)
11. Adiciona system_prompt ao primeiro user message do history
12. `build_kiro_history`: converte history para formato Kiro
13. Processa `current_message`: se assistant → move para history, current = "Continue"
14. Se sem tools e role=user → `inject_thinking_tags` se habilitado
15. Monta `userInputMessage` e `conversationState`
16. Se `AUTO_TRIM_PAYLOAD` e tamanho > limite → `trim_payload_to_limit`
17. Retorna `KiroPayloadResult`

## Fluxos Alternativos

- **Payload vazio após normalização**: raise `ValueError("No messages to send")`
- **Tool name > 64 chars**: raise `ValueError` com lista de tools problemáticas
- **Mensagem atual é assistant**: adicionada ao history, current_message = "Continue"
- **Sem system_prompt e sem history**: `userInputMessage` sem prefixo de system
- **Payload excede limite**: remove pares do início até caber (preserva mensagem atual)

## Dependências

- `kiro/config.py` — `TOOL_DESCRIPTION_MAX_LENGTH`, `KIRO_MAX_PAYLOAD_BYTES`, `AUTO_TRIM_PAYLOAD`, `FAKE_REASONING_ENABLED`, `TRUNCATION_RECOVERY`
- `kiro/model_resolver.py` — `normalize_model_name`
- `kiro/truncation_recovery.py` — modificação de tool_results truncados

## Requisitos Não Funcionais

| Tipo | Requisito inferido | Evidência no código | Confiança |
|------|--------------------|---------------------|-----------|
| Compatibilidade | 8 transformações corrigem restrições não documentadas da Kiro API | `kiro/converters_core.py:1164-1479` | 🟢 |
| Performance | Auto-trim evita rejeição por payload muito grande | `kiro/converters_core.py` — `trim_payload_to_limit` | 🟢 |
| Segurança | Validação de tool names antes do envio | `kiro/converters_core.py` — `validate_tool_names` | 🟢 |

## Critérios de Aceitação

```gherkin
Dado uma conversa que começa com mensagem assistant
Quando build_kiro_payload() é chamado
Então um user message vazio é inserido antes da primeira mensagem

Dado mensagens consecutivas do mesmo role (user, user)
Quando build_kiro_payload() é chamado
Então uma mensagem assistant sintética é inserida entre elas

Dado uma tool com nome de 65 caracteres
Quando build_kiro_payload() é chamado
Então ValueError é levantado com o nome da tool problemática

Dado uma tool com descrição maior que TOOL_DESCRIPTION_MAX_LENGTH
Quando build_kiro_payload() é chamado
Então a descrição é movida para o system prompt e substituída por referência

Dado payload resultante maior que KIRO_MAX_PAYLOAD_BYTES com AUTO_TRIM=true
Quando build_kiro_payload() é chamado
Então pares de mensagens antigas são removidos até o payload caber no limite
```

## Prioridade

| Requisito | MoSCoW | Justificativa |
|-----------|--------|---------------|
| Pipeline de 8 normalizações | Must | Sem isso, Kiro API rejeita a maioria das requisições |
| validate_tool_names | Must | Kiro API rejeita nomes > 64 chars sem mensagem clara |
| build_kiro_history | Must | Estrutura obrigatória do KiroPayload |
| process_tools_with_long_descriptions | Should | Necessário apenas para tools com descrições longas |
| inject_thinking_tags | Should | Apenas quando FAKE_REASONING_ENABLED=true |
| trim_payload_to_limit | Should | Apenas quando AUTO_TRIM_PAYLOAD=true |

## Rastreabilidade de Código

| Arquivo | Função / Classe | Cobertura |
|---------|-----------------|-----------|
| `kiro/converters_core.py` | `build_kiro_payload` | 🟢 |
| `kiro/converters_core.py:1164` | `ensure_first_message_is_user` | 🟢 |
| `kiro/converters_core.py:1471` | pipeline de normalização | 🟢 |
| `kiro/converters_core.py:417` | `inject_thinking_tags` | 🟢 |
| `kiro/converters_core.py` | `validate_tool_names` | 🟢 |
| `kiro/converters_core.py` | `trim_payload_to_limit` | 🟢 |
