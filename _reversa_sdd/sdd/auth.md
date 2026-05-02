# KiroAuthManager — Gerenciamento de Autenticação

## Visão Geral
Gerencia o ciclo de vida completo de access tokens para comunicação com a Kiro API. Suporta 4 fontes de credenciais e 2 tipos de autenticação, com refresh automático, graceful degradation e persistência thread-safe.

## Responsabilidades
- Carregar credenciais de 4 fontes: arquivo JSON, SQLite, variável de ambiente, Enterprise
- Detectar automaticamente o tipo de autenticação (KIRO_DESKTOP ou AWS_SSO_OIDC)
- Renovar access tokens antes da expiração via endpoint apropriado por região
- Persistir tokens atualizados de volta à fonte original (arquivo ou SQLite)
- Fornecer degradação graciosa quando refresh falha mas token ainda é válido
- Expor metadados de conta: region, api_host, q_host, profile_arn, fingerprint

## Interface

**Construtor:**
```python
KiroAuthManager(
    credentials_file: Optional[str] = None,   # Caminho para JSON ou SQLite
    refresh_token: Optional[str] = None,       # Token direto via env var
    profile_arn: Optional[str] = None,         # ARN do perfil CodeWhisperer
    region: Optional[str] = None               # Região AWS (fallback: us-east-1)
)
```

**Métodos públicos:**
```python
async def get_access_token() -> str
    # Retorna token válido, renovando se necessário. Thread-safe via asyncio.Lock.

async def force_refresh() -> str
    # Força renovação imediata do token (chamado após 403 da Kiro API).

@property def profile_arn() -> Optional[str]
@property def region() -> str
@property def api_host() -> str   # codewhisperer.{region}.amazonaws.com (legado)
@property def q_host() -> str     # q.{region}.amazonaws.com (atual)
@property def fingerprint() -> str
@property def auth_type() -> AuthType
```

**Tipos:**
```python
class AuthType(Enum):
    KIRO_DESKTOP = "kiro_desktop"
    AWS_SSO_OIDC = "aws_sso_oidc"
```

## Regras de Negócio

- 🟢 **RN-AUTH-01**: Token é considerado válido se `expires_at > now + 5min` (buffer de segurança)
- 🟢 **RN-AUTH-02**: Apenas um refresh ocorre por vez — `asyncio.Lock` previne refreshes paralelos
- 🟢 **RN-AUTH-03**: Tipo de auth detectado pela presença de `clientId` + `clientSecret` nas credenciais → AWS_SSO_OIDC; ausência → KIRO_DESKTOP
- 🟢 **RN-AUTH-04**: Endpoints de auth são construídos dinamicamente com a região detectada das credenciais
- 🟢 **RN-AUTH-05**: Região detectada em ordem: campo `region` explícito → extraído de `startUrl` → env `KIRO_REGION` → fallback `us-east-1`
- 🟢 **RN-AUTH-06**: Degradação graciosa: se refresh retorna 400 mas access token ainda é válido, usa token existente sem falhar
- 🟢 **RN-AUTH-07**: SQLite usa estratégia Read-Merge-Write para evitar sobrescrever campos atualizados por outro processo
- 🟢 **RN-AUTH-08**: AWS_SSO_OIDC com erro 400 em SQLite: recarrega credenciais do SQLite e tenta novamente antes de falhar
- 🟡 **RN-AUTH-09**: Fingerprint é derivado de hash das credenciais para simular cliente Kiro IDE legítimo no User-Agent

## Fluxo Principal

1. `get_access_token()` chamado
2. Verifica se token existe e não está expirando (`expires_at > now + 5min`)
3. Se válido → retorna token imediatamente
4. Se modo SQLite → recarrega credenciais do SQLite antes de tentar refresh
5. Adquire `asyncio.Lock` para prevenir refresh paralelo
6. Chama `_refresh_token_request()` conforme `auth_type`
7. Atualiza `_access_token` e `_expires_at` em memória
8. Persiste token na fonte original (arquivo ou SQLite)
9. Libera lock e retorna novo token

## Fluxos Alternativos

- **Token ainda válido após lock adquirido**: outro coroutine já fez refresh — retorna token atualizado sem novo request
- **KIRO_DESKTOP refresh**: POST `prod.{region}.auth.desktop.kiro.dev/refreshToken` com `{"refreshToken": "..."}`
- **AWS_SSO_OIDC refresh**: POST `oidc.{region}.amazonaws.com/token` com grant_type, client_id, client_secret, refresh_token
- **400 + SQLite (AWS_SSO_OIDC)**: recarrega SQLite, tenta POST novamente uma vez
- **400 + token ainda válido**: loga warning, usa token existente (graceful degradation)
- **400 + token inválido**: raise `ValueError("run kiro-cli login")`
- **Outros erros HTTP**: propaga exceção ao caller

## Dependências

- `httpx` — requisições HTTP para endpoints de auth
- `sqlite3` — leitura/escrita de credenciais SQLite
- `asyncio.Lock` — serialização de refreshes concorrentes
- `kiro.config` — constantes de região, endpoints, timeouts

## Requisitos Não Funcionais

| Tipo | Requisito inferido | Evidência no código | Confiança |
|------|--------------------|---------------------|-----------|
| Segurança | Tokens nunca logados em nível INFO ou superior | `kiro/auth.py` — ausência de log de token | 🟡 |
| Disponibilidade | Graceful degradation em falha de refresh | `kiro/auth.py:867` — `get_access_token` | 🟢 |
| Concorrência | asyncio.Lock previne refreshes paralelos | `kiro/auth.py` — `_refresh_lock` | 🟢 |
| Compatibilidade | Read-Merge-Write para SQLite compartilhado | `kiro/auth.py:525` | 🟢 |

## Critérios de Aceitação

```gherkin
Dado que o access token está válido (expires_at > now + 5min)
Quando get_access_token() é chamado
Então retorna o token existente sem fazer request HTTP

Dado que o access token está expirando (expires_at < now + 5min)
Quando get_access_token() é chamado
Então faz POST ao endpoint de refresh e retorna novo token

Dado que o refresh retorna 400 e o token atual ainda é válido
Quando get_access_token() é chamado
Então loga warning e retorna o token existente sem falhar

Dado que o refresh retorna 400 e o token atual está expirado
Quando get_access_token() é chamado
Então raise ValueError com instrução "run kiro-cli login"

Dado que dois coroutines chamam get_access_token() simultaneamente com token expirado
Quando ambos tentam fazer refresh
Então apenas um request HTTP é feito (Lock serializa)
```

## Prioridade

| Requisito | MoSCoW | Justificativa |
|-----------|--------|---------------|
| get_access_token() | Must | Chamado em toda requisição à Kiro API |
| Detecção automática de auth_type | Must | Sem isso, nenhuma autenticação funciona |
| Refresh automático | Must | Tokens expiram em ~1h — sem refresh, serviço para |
| Graceful degradation | Should | Melhora resiliência mas token eventualmente expira |
| Read-Merge-Write SQLite | Should | Necessário apenas em modo SQLite com kiro-cli ativo |
| force_refresh() | Should | Chamado apenas após 403 da Kiro API |
| Suporte Enterprise | Could | Caso de uso específico de organizações |

## Rastreabilidade de Código

| Arquivo | Função / Classe | Cobertura |
|---------|-----------------|-----------|
| `kiro/auth.py:85` | `KiroAuthManager` | 🟢 |
| `kiro/auth.py:867` | `get_access_token` | 🟢 |
| `kiro/auth.py:933` | `force_refresh` | 🟢 |
| `kiro/auth.py:664` | `_refresh_token_request` | 🟢 |
| `kiro/auth.py:681` | `_refresh_token_kiro_desktop` | 🟢 |
| `kiro/auth.py:740` | `_refresh_token_aws_sso_oidc` | 🟢 |
| `kiro/auth.py:521` | `_save_credentials_to_sqlite` | 🟢 |
| `kiro/auth.py:234` | `_detect_auth_type` | 🟢 |
