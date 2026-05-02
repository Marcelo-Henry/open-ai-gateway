# AccountManager — Gerenciamento Multi-Account

## Visão Geral
Gerencia múltiplas contas Kiro com seleção inteligente via Circuit Breaker, sticky behavior e failover automático. Inicializa contas de forma lazy, persiste estado entre reinicializações e expõe métricas de uso por conta.

## Responsabilidades
- Manter registro de todas as contas configuradas com seus estados de Circuit Breaker
- Selecionar a próxima conta disponível para um modelo dado (sticky + failover)
- Inicializar contas de forma lazy (apenas quando necessária pela primeira vez)
- Reportar sucesso/falha por conta para atualizar o Circuit Breaker
- Persistir estado (índice atual, failures, timestamps) em `state.json` atomicamente
- Agregar lista de modelos disponíveis de todas as contas para `/v1/models`

## Interface

**Construtor:**
```python
AccountManager(credentials_file: str, state_file: str)
# credentials_file: JSON com lista de contas ou conta única
# state_file: caminho para state.json de persistência
```

**Métodos públicos:**
```python
async def load_state() -> None
    # Carrega estado persistido do state.json. Chamado no startup.

async def get_next_account(
    model: str,
    exclude_accounts: Optional[set] = None
) -> Optional[Account]
    # Retorna próxima conta disponível para o modelo.
    # None se nenhuma conta disponível (→ 503).

async def report_success(account_id: str) -> None
    # Reseta failures, atualiza sticky index, incrementa stats.

async def report_failure(
    account_id: str,
    error_type: ErrorType,
    status_code: Optional[int] = None
) -> None
    # Incrementa failures, registra timestamp, determina se faz failover.

async def get_all_models() -> List[str]
    # Agrega modelos de todas as contas (para /v1/models).

async def save_state_periodically() -> None
    # Background task: salva state.json a cada STATE_SAVE_INTERVAL_SECONDS (10s).
```

**Dataclasses:**
```python
@dataclass
class Account:
    id: str                          # Caminho do arquivo de credenciais
    auth_manager: Optional[KiroAuthManager]
    model_cache: Optional[ModelInfoCache]
    model_resolver: Optional[ModelResolver]
    failures: int = 0
    last_failure_time: float = 0.0
    models_cached_at: float = 0.0
    stats: AccountStats = field(default_factory=AccountStats)
```

## Regras de Negócio

- 🟢 **RN-AM-01**: Com uma única conta, Circuit Breaker é desativado — conta sempre retornada independente de failures
- 🟢 **RN-AM-02**: Índice sticky é global (não por modelo) — todos os modelos usam a mesma conta preferida
- 🟢 **RN-AM-03**: Backoff exponencial: `ACCOUNT_RECOVERY_TIMEOUT * 2^(failures-1)`, cap em `ACCOUNT_MAX_BACKOFF_MULTIPLIER` (1440x = 1 dia)
- 🟢 **RN-AM-04**: 10% de chance de retry probabilístico mesmo durante cooldown ativo (`ACCOUNT_PROBABILISTIC_RETRY_CHANCE`)
- 🟢 **RN-AM-05**: Conta em cooldown com `time_since_failure >= effective_timeout` entra em Half-Open e é testada
- 🟢 **RN-AM-06**: Inicialização lazy — `auth_manager` é `None` até primeira chamada; falha de init incrementa failures
- 🟢 **RN-AM-07**: Cache de modelos tem TTL de 12h (`ACCOUNT_CACHE_TTL`); refresca automaticamente quando expirado
- 🟢 **RN-AM-08**: state.json salvo atomicamente via arquivo temporário + rename para evitar corrupção
- 🟢 **RN-AM-09**: Failover via `exclude_accounts`: conta com falha é adicionada ao set e `get_next_account` é chamado recursivamente
- 🟡 **RN-AM-10**: Conta sem o modelo solicitado é pulada silenciosamente (sem incrementar failures)

## Fluxo Principal

1. `get_next_account(model)` chamado pela route
2. Se conta única → retorna diretamente (sem Circuit Breaker)
3. Normaliza nome do modelo
4. Itera sobre todas as contas a partir do índice global sticky
5. Pula contas em `exclude_accounts`
6. Verifica Circuit Breaker: se `failures > 0` e `time_since_failure < effective_timeout` → pula (exceto 10% probabilístico)
7. Se `auth_manager is None` → inicializa conta lazy; falha → incrementa failures, continua
8. Se cache de modelos expirado → refresca (falha não bloqueia)
9. Verifica se modelo está disponível na conta → pula se não
10. Retorna conta selecionada

## Fluxos Alternativos

- **Nenhuma conta disponível**: retorna `None` → route retorna 503
- **Falha de inicialização lazy**: `failures += 1`, tenta próxima conta
- **Erro RECOVERABLE (429, 5xx)**: `failures += 1`, failover para próxima conta
- **Erro UNRECOVERABLE (400, 401)**: não incrementa failures (problema de request, não de conta)
- **Erro QUOTA (402)**: marca conta como em quota, não faz failover imediato
- **Sucesso após Half-Open**: `failures = 0`, sticky index atualizado para esta conta

## Dependências

- `kiro/auth.py` — `KiroAuthManager` por conta
- `kiro/cache.py` — `ModelInfoCache` por conta
- `kiro/model_resolver.py` — `ModelResolver` por conta
- `kiro/http_client.py` — `KiroHttpClient` para inicialização e refresh de modelos
- `kiro/account_errors.py` — classificação de erros para decisão de failover
- `kiro/config.py` — `ACCOUNT_RECOVERY_TIMEOUT`, `ACCOUNT_MAX_BACKOFF_MULTIPLIER`, `ACCOUNT_PROBABILISTIC_RETRY_CHANCE`, `ACCOUNT_CACHE_TTL`, `STATE_SAVE_INTERVAL_SECONDS`

## Requisitos Não Funcionais

| Tipo | Requisito inferido | Evidência no código | Confiança |
|------|--------------------|---------------------|-----------|
| Disponibilidade | Circuit Breaker com backoff exponencial | `kiro/account_manager.py:670` | 🟢 |
| Disponibilidade | Retry probabilístico 10% em cooldown | `kiro/account_manager.py:693` | 🟢 |
| Performance | Inicialização lazy — sem overhead no startup | `kiro/account_manager.py:686` | 🟢 |
| Durabilidade | Persistência atômica via tmp + rename | `kiro/account_manager.py:373` | 🟢 |
| Escalabilidade | Cache de modelos com TTL evita chamadas repetidas | `kiro/account_manager.py:560` | 🟢 |

## Critérios de Aceitação

```gherkin
Dado que há múltiplas contas e a conta atual está funcionando
Quando get_next_account() é chamado
Então retorna a mesma conta (sticky behavior)

Dado que a conta atual falhou (failures > 0, em cooldown)
Quando get_next_account() é chamado
Então retorna a próxima conta disponível (failover)

Dado que há apenas uma conta configurada
Quando a conta falha repetidamente
Então get_next_account() continua retornando a mesma conta (Circuit Breaker desativado)

Dado que todas as contas estão em cooldown
Quando get_next_account() é chamado
Então retorna None e a route responde com 503

Dado que uma conta estava em cooldown e o timeout expirou
Quando get_next_account() é chamado
Então a conta entra em Half-Open e é retornada para teste
```

## Prioridade

| Requisito | MoSCoW | Justificativa |
|-----------|--------|---------------|
| get_next_account() | Must | Chamado em toda requisição — caminho crítico |
| Circuit Breaker | Must | Sem isso, contas com falha continuam sendo usadas |
| Sticky behavior | Must | Evita troca desnecessária de conta a cada requisição |
| Failover automático | Must | Garante disponibilidade com múltiplas contas |
| Persistência de estado | Should | Perde estado em restart sem isso, mas funciona |
| Retry probabilístico | Should | Melhora recuperação mas não é crítico |
| Agregação de modelos | Could | Apenas para /v1/models — não afeta fluxo principal |

## Rastreabilidade de Código

| Arquivo | Função / Classe | Cobertura |
|---------|-----------------|-----------|
| `kiro/account_manager.py:169` | `AccountManager.__init__` | 🟢 |
| `kiro/account_manager.py:597` | `get_next_account` | 🟢 |
| `kiro/account_manager.py:719` | `report_success` | 🟢 |
| `kiro/account_manager.py:759` | `report_failure` | 🟢 |
| `kiro/account_manager.py:299` | `load_state` | 🟢 |
| `kiro/account_manager.py:344` | `_save_state` | 🟢 |
| `kiro/account_manager.py:389` | `save_state_periodically` | 🟢 |
