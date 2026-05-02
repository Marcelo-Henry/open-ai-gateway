# Modelo de Permissões e Autenticação — AI Gateway

> Escala de confiança: 🟢 CONFIRMADO | 🟡 INFERIDO | 🔴 LACUNA

---

## 1. Visão Geral

O AI Gateway opera com dois níveis de autenticação independentes:

1. **Autenticação do Cliente → Gateway** (`PROXY_API_KEY`): controla quem pode usar o gateway
2. **Autenticação do Gateway → Kiro API** (Access Token): controla o acesso à Kiro API da Amazon

```
Cliente
  │
  │  Authorization: Bearer {PROXY_API_KEY}
  │  ou x-api-key: {PROXY_API_KEY}
  ▼
┌─────────────────────────────┐
│       AI Gateway          │
│   (verify_api_key /         │
│    verify_anthropic_api_key)│
└─────────────────────────────┘
  │
  │  Authorization: Bearer {access_token}
  │  x-amzn-codewhisperer-token: {access_token}
  ▼
┌─────────────────────────────┐
│        Kiro API             │
│  (Amazon Q Developer /      │
│   AWS CodeWhisperer)        │
└─────────────────────────────┘
```

---

## 2. Autenticação Cliente → Gateway

### 2.1 Endpoint OpenAI (`routes_openai.py`)

🟢 **Header**: `Authorization: Bearer {PROXY_API_KEY}`

```python
api_key_header = APIKeyHeader(name="Authorization", auto_error=False)

async def verify_api_key(auth_header: str = Security(api_key_header)) -> bool:
    if not auth_header or auth_header != f"Bearer {PROXY_API_KEY}":
        raise HTTPException(status_code=401, detail="Invalid API Key")
    return True
```

**Endpoints protegidos**:
- `GET /v1/models`
- `POST /v1/chat/completions`

### 2.2 Endpoint Anthropic (`routes_anthropic.py`)

🟢 **Headers aceitos** (em ordem de prioridade):
1. `x-api-key: {PROXY_API_KEY}` (formato nativo Anthropic)
2. `Authorization: Bearer {PROXY_API_KEY}` (compatibilidade OpenAI)

```python
async def verify_anthropic_api_key(
    x_api_key: Optional[str] = Security(anthropic_api_key_header),
    authorization: Optional[str] = Security(authorization_header),
) -> bool:
    if x_api_key and x_api_key == PROXY_API_KEY:
        return True
    if authorization and authorization == f"Bearer {PROXY_API_KEY}":
        return True
    raise HTTPException(status_code=401, ...)
```

**Endpoints protegidos**:
- `POST /v1/messages`
- `POST /v1/messages/count_tokens`

### 2.3 Endpoints Públicos (sem autenticação)

🟢 Os seguintes endpoints não requerem autenticação:
- `GET /` — health check básico
- `GET /health` — health check detalhado

### 2.4 Configuração da Chave

🟢 `PROXY_API_KEY` é definida via variável de ambiente ou arquivo `.env`. Não tem valor padrão — se não configurada, o gateway rejeita todas as requisições autenticadas.

---

## 3. Autenticação Gateway → Kiro API

### 3.1 Métodos de Autenticação Suportados

🟢 O `KiroAuthManager` suporta 4 fontes de credenciais, detectadas automaticamente:

| Método | Fonte | Variável de Ambiente | Tipo Auth |
|--------|-------|---------------------|-----------|
| JSON File (Kiro IDE) | Arquivo JSON | `KIRO_CREDS_FILE` | KIRO_DESKTOP ou AWS_SSO_OIDC |
| SQLite (kiro-cli) | Banco SQLite | `KIRO_CLI_DB_FILE` | KIRO_DESKTOP ou AWS_SSO_OIDC |
| Env Var | Variável de ambiente | `REFRESH_TOKEN` | KIRO_DESKTOP |
| Enterprise | Arquivo JSON com `clientId` | `KIRO_CREDS_FILE` | AWS_SSO_OIDC |

### 3.2 Detecção Automática de Tipo Auth

🟢 O tipo de autenticação é detectado pela presença de campos nas credenciais:

```
credenciais têm clientId E clientSecret?
  → AWS_SSO_OIDC (Builder ID ou Enterprise)
  → Endpoint: oidc.{region}.amazonaws.com/token

credenciais NÃO têm clientId/clientSecret?
  → KIRO_DESKTOP
  → Endpoint: prod.{region}.auth.desktop.kiro.dev/refreshToken
```

### 3.3 Fluxo de Refresh de Token

🟢 **KIRO_DESKTOP**:
```
POST https://prod.{region}.auth.desktop.kiro.dev/refreshToken
Body: { "refreshToken": "{refresh_token}" }
Response: { "accessToken": "...", "expiresIn": 3600 }
```

🟢 **AWS_SSO_OIDC**:
```
POST https://oidc.{region}.amazonaws.com/token
Body: {
  "grant_type": "refresh_token",
  "client_id": "{clientId}",
  "client_secret": "{clientSecret}",
  "refresh_token": "{refreshToken}"
}
Response: { "access_token": "...", "expires_in": 3600 }
```

### 3.4 Headers Enviados à Kiro API

🟢 Construídos por `get_kiro_headers()` em `utils.py`:

```python
{
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json",
    "Accept": "application/vnd.amazon.eventstream",
    "x-amzn-codewhisperer-token": access_token,
    "User-Agent": f"aws-sdk-js/1.0.27 ... KiroIDE-0.7.45-{fingerprint}",
    # Se profile_arn configurado:
    "x-amzn-codewhisperer-optout": "false",
}
```

🟡 O `fingerprint` é derivado de um hash das credenciais para simular um cliente Kiro IDE legítimo.

### 3.5 Persistência de Credenciais

🟢 **Arquivo JSON** (`_save_credentials_to_file`):
- Lê arquivo existente
- Atualiza campos `accessToken`, `expiresAt`
- Escreve de volta atomicamente

🟢 **SQLite** (`_save_credentials_to_sqlite`) — estratégia Read-Merge-Write (Issue #131):
1. Lê estado atual do SQLite
2. Faz merge com novos valores (preserva campos não modificados)
3. Tenta salvar na chave primária
4. Se falhar, tenta chaves alternativas
5. Evita sobrescrever campos atualizados por outro processo concorrente

---

## 4. Multi-Account: Isolamento de Credenciais

🟢 Cada account tem seu próprio `KiroAuthManager` isolado. Não há compartilhamento de tokens entre accounts. O `AccountManager` gerencia o ciclo de vida de cada account independentemente.

```
AccountManager
├── Account A (credentials_a.json)
│   └── KiroAuthManager A → access_token_A
├── Account B (credentials_b.json)
│   └── KiroAuthManager B → access_token_B
└── Account C (credentials_c.json)
    └── KiroAuthManager C → access_token_C
```

---

## 5. Codex Provider: Autenticação Separada

🟢 Modelos `gpt-*` e `codex-*` usam autenticação completamente diferente:

- **Endpoint**: `chatgpt.com/backend-api/codex/responses`
- **Auth**: OAuth do ChatGPT (não credenciais Kiro)
- **Configuração**: `CODEX_AUTH_TOKEN` (variável de ambiente)
- **Isolamento**: Completamente separado do fluxo Kiro

---

## 6. Matriz de Permissões por Endpoint

| Endpoint | Auth Cliente | Auth Kiro | Notas |
|----------|-------------|-----------|-------|
| `GET /` | ❌ Não requer | ❌ Não usa | Health check público |
| `GET /health` | ❌ Não requer | ❌ Não usa | Health check público |
| `GET /v1/models` | ✅ Bearer token | ✅ Usa (lista modelos) | Agrega modelos de todas as accounts |
| `POST /v1/chat/completions` | ✅ Bearer token | ✅ Usa | Streaming ou não-streaming |
| `POST /v1/messages` | ✅ x-api-key ou Bearer | ✅ Usa | Streaming ou não-streaming |
| `POST /v1/messages/count_tokens` | ✅ x-api-key ou Bearer | ❌ Não usa | Contagem local via tiktoken |

---

## 7. Tratamento de Erros de Autenticação

| Cenário | Código HTTP | Mensagem |
|---------|-------------|---------|
| PROXY_API_KEY ausente ou inválido | 401 | "Invalid API Key" / "Invalid or missing API key" |
| Access token expirado (Kiro API retorna 403) | — | Gateway faz force_refresh automático e retry |
| Refresh token inválido (400 + token expirado) | 401 | "run kiro-cli login" |
| Sem accounts disponíveis | 503 | "No accounts available" |
| Quota excedida (402) | 402 | Mensagem de billing |
