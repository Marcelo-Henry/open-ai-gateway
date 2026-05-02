# ModelResolver — Resolução de Modelos

## Visão Geral
Pipeline de 4 camadas para mapear nomes de modelos enviados pelos clientes para o formato aceito pela Kiro API. Implementa o princípio "gateway, não gatekeeper": modelos desconhecidos são passados diretamente à Kiro API sem rejeição.

## Responsabilidades
- Normalizar nomes de modelos via 5 padrões regex
- Verificar disponibilidade no cache dinâmico (modelos da API)
- Incluir modelos ocultos configurados manualmente
- Fazer passthrough de modelos desconhecidos
- Expor lista de modelos disponíveis para `/v1/models`

## Interface

**Função standalone:**
```python
def normalize_model_name(name: str) -> str
    # Aplica 5 transformações regex ao nome do modelo.
    # Exemplos:
    #   "claude-haiku-4-5-20251001" → "claude-haiku-4.5"
    #   "claude-opus-4-6"          → "claude-opus-4.6"
    #   "4-5-claude-haiku"         → "claude-haiku-4.5"  (formato invertido)
```

**Classe:**
```python
class ModelResolver:
    def __init__(
        self,
        dynamic_models: List[str],      # Da API /ListAvailableModels
        hidden_models: List[str],        # De config.HIDDEN_MODELS
        hidden_from_list: List[str],     # De config.HIDDEN_FROM_LIST
        model_aliases: Dict[str, str],   # De config.MODEL_ALIASES
    )

    def resolve(self, model_name: str) -> str
        # Retorna nome normalizado. Nunca retorna None.

    def get_available_models(self) -> List[str]
        # Lista de modelos para /v1/models (exclui HIDDEN_FROM_LIST).

    def is_available(self, model_name: str) -> bool
        # True se modelo está no cache dinâmico ou hidden_models.
```

## Regras de Negócio

- 🟢 **RN-MR-01**: Normalização aplica 5 padrões em sequência: (1) dash→dot para versão minor, (2) strip sufixo de data 8 dígitos, (3) formato legado, (4) formato invertido, (5) passthrough
- 🟢 **RN-MR-02**: Modelos desconhecidos são retornados normalizados sem erro (princípio passthrough — ADR-006)
- 🟢 **RN-MR-03**: `HIDDEN_MODELS` são incluídos na resolução mas não listados em `/v1/models`
- 🟢 **RN-MR-04**: `HIDDEN_FROM_LIST` são excluídos da listagem pública mas funcionam normalmente
- 🟢 **RN-MR-05**: `MODEL_ALIASES` mapeiam nomes alternativos para nomes canônicos antes da normalização
- 🟡 **RN-MR-06**: Cache dinâmico é atualizado pelo `AccountManager` a cada `ACCOUNT_CACHE_TTL` (12h)

## Fluxo Principal (normalize_model_name)

1. Verifica `MODEL_ALIASES` — substitui se encontrar alias
2. Padrão 1: `claude-X-Y-Z` onde Z é dígito único → `claude-X-Y.Z` (dash→dot versão minor)
3. Padrão 2: strip sufixo de 8 dígitos numéricos (ex: `-20251001`)
4. Padrão 3: formato legado (ex: `claude-v1`) → normalizado
5. Padrão 4: formato invertido (ex: `4-5-claude-haiku`) → `claude-haiku-4.5`
6. Retorna nome transformado (ou original se nenhum padrão aplicou)

## Fluxos Alternativos

- **Alias encontrado**: substitui antes de normalizar
- **Nenhum padrão aplica**: retorna nome original sem modificação
- **Modelo não no cache**: retorna nome normalizado mesmo assim (passthrough)

## Dependências

- `kiro/config.py` — `HIDDEN_MODELS`, `HIDDEN_FROM_LIST`, `MODEL_ALIASES`
- `kiro/cache.py` — `ModelInfoCache` (fonte do cache dinâmico)

## Requisitos Não Funcionais

| Tipo | Requisito inferido | Evidência no código | Confiança |
|------|--------------------|---------------------|-----------|
| Compatibilidade | Normalização suporta múltiplos formatos de nome de cliente | `kiro/model_resolver.py` — 5 padrões regex | 🟢 |
| Extensibilidade | Novos modelos suportados automaticamente via cache dinâmico | `kiro/model_resolver.py` — passthrough | 🟢 |

## Critérios de Aceitação

```gherkin
Dado o nome "claude-haiku-4-5-20251001"
Quando normalize_model_name() é chamado
Então retorna "claude-haiku-4.5"

Dado o nome "claude-opus-4-6"
Quando normalize_model_name() é chamado
Então retorna "claude-opus-4.6"

Dado o nome "modelo-completamente-desconhecido"
Quando normalize_model_name() é chamado
Então retorna "modelo-completamente-desconhecido" sem erro

Dado o nome "4-5-claude-haiku" (formato invertido)
Quando normalize_model_name() é chamado
Então retorna "claude-haiku-4.5"
```

## Prioridade

| Requisito | MoSCoW | Justificativa |
|-----------|--------|---------------|
| normalize_model_name() | Must | Chamado em toda requisição — nomes de clientes variam muito |
| Passthrough de desconhecidos | Must | Princípio fundamental do gateway (ADR-006) |
| Cache dinâmico | Should | Sem cache, não sabe quais modelos estão disponíveis |
| HIDDEN_MODELS | Could | Apenas para modelos não documentados pela Kiro API |
| MODEL_ALIASES | Could | Conveniência para nomes alternativos |

## Rastreabilidade de Código

| Arquivo | Função / Classe | Cobertura |
|---------|-----------------|-----------|
| `kiro/model_resolver.py` | `normalize_model_name` | 🟢 |
| `kiro/model_resolver.py` | `ModelResolver` | 🟢 |
| `kiro/model_resolver.py` | `ModelResolver.resolve` | 🟢 |
| `kiro/model_resolver.py` | `ModelResolver.get_available_models` | 🟢 |
