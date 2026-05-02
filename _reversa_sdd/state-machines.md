# Máquinas de Estado — Kiro Gateway

> Escala de confiança: 🟢 CONFIRMADO | 🟡 INFERIDO | 🔴 LACUNA

---

## 1. Ciclo de Vida do Access Token (`KiroAuthManager`)

```mermaid
stateDiagram-v2
    [*] --> UNINITIALIZED : instância criada

    UNINITIALIZED --> VALID : get_access_token() chamado\ncredenciais carregadas\ntoken não expirado

    UNINITIALIZED --> REFRESHING : get_access_token() chamado\ntoken ausente ou expirado

    VALID --> EXPIRING_SOON : is_token_expiring_soon()\n(< 5 min para expirar)

    EXPIRING_SOON --> REFRESHING : get_access_token() chamado

    VALID --> REFRESHING : force_refresh() chamado\nou 403 recebido da Kiro API

    REFRESHING --> VALID : refresh bem-sucedido\ntoken salvo (arquivo ou SQLite)

    REFRESHING --> DEGRADED : refresh falhou com 400\nmas token atual ainda válido\n(graceful degradation)

    REFRESHING --> ERROR : refresh falhou\ntoken inválido ou ausente\nRaise ValueError

    DEGRADED --> REFRESHING : próxima chamada get_access_token()

    ERROR --> [*] : exceção propagada ao caller

    note right of REFRESHING
        KIRO_DESKTOP: POST prod.region.auth.desktop.kiro.dev/refreshToken
        AWS_SSO_OIDC: POST oidc.region.amazonaws.com/token
        Protegido por asyncio.Lock (sem refresh paralelo)
    end note

    note right of DEGRADED
        Issue #131: SQLite Read-Merge-Write
        Evita sobrescrever campos de outro processo
    end note
```

### Transições de Estado do Token

| Estado | Condição de Entrada | Ação | Próximo Estado |
|--------|--------------------|----|----------------|
| UNINITIALIZED | Instância criada | Carrega credenciais do source configurado | VALID ou REFRESHING |
| VALID | Token presente e `expires_at > now + 5min` | Retorna token | VALID |
| EXPIRING_SOON | `expires_at - now < 5min` | Inicia refresh proativo | REFRESHING |
| REFRESHING | Token ausente, expirado ou force_refresh | POST ao endpoint de auth | VALID / DEGRADED / ERROR |
| DEGRADED | Refresh 400 + token ainda válido | Usa token existente, loga warning | VALID (próxima chamada) |
| ERROR | Refresh falhou + token inválido | Raise ValueError com instrução de login | — |

---

## 2. Circuit Breaker de Account (`AccountManager`)

```mermaid
stateDiagram-v2
    [*] --> CLOSED : account inicializada\nfailures = 0

    CLOSED --> CLOSED : request bem-sucedido\nfailures mantido em 0\nsticky index atualizado

    CLOSED --> OPEN : request falhou\nfailures += 1\nlast_failure_time = now\ncooldown = 60s * 2^(failures-1)

    OPEN --> OPEN : time_since_failure < effective_timeout\nE random() > 0.10\n(account pulada no get_next_account)

    OPEN --> HALF_OPEN : time_since_failure >= effective_timeout\nOU random() <= 0.10 (retry probabilístico 10%)

    HALF_OPEN --> CLOSED : request bem-sucedido\nfailures = 0

    HALF_OPEN --> OPEN : request falhou novamente\nfailures += 1\nnovo cooldown maior

    note right of OPEN
        Backoff exponencial:
        1 falha  → 60s
        2 falhas → 120s
        3 falhas → 240s
        ...
        12+ falhas → 86400s (1 dia, cap)
        ACCOUNT_MAX_BACKOFF_MULTIPLIER = 1440
    end note

    note right of HALF_OPEN
        Retry probabilístico: 10% de chance
        mesmo durante cooldown ativo
        ACCOUNT_PROBABILISTIC_RETRY_CHANCE = 0.1
    end note
```

### Regra Especial: Single Account

🟢 Com apenas uma account configurada, o Circuit Breaker é **completamente ignorado**. A account é sempre retornada independente do número de falhas. Razão: o usuário deve ver os erros reais da Kiro API, não mensagens de "sem contas disponíveis".

### Parâmetros Configuráveis

| Parâmetro | Env Var | Default | Descrição |
|-----------|---------|---------|-----------|
| Base timeout | `ACCOUNT_RECOVERY_TIMEOUT` | 60s | Cooldown base para 1 falha |
| Cap multiplicador | `ACCOUNT_MAX_BACKOFF_MULTIPLIER` | 1440 | Cap = 60s × 1440 = 1 dia |
| Retry probabilístico | `ACCOUNT_PROBABILISTIC_RETRY_CHANCE` | 0.10 | 10% de chance de retry em OPEN |
| TTL cache modelos | `ACCOUNT_CACHE_TTL` | 43200s (12h) | Refresca lista de modelos |
| Intervalo save state | `STATE_SAVE_INTERVAL_SECONDS` | 10s | Persistência periódica em state.json |

---

## 3. ThinkingParser FSM (`thinking_parser.py`)

```mermaid
stateDiagram-v2
    [*] --> PRE_CONTENT : instância criada\nbuffer vazio

    PRE_CONTENT --> PRE_CONTENT : chunk recebido\nnenhuma tag de thinking detectada\nbuffer mantém últimos max_tag_length chars

    PRE_CONTENT --> IN_THINKING : tag de abertura detectada no buffer\n(ex: <parameter name="content">)

    IN_THINKING --> IN_THINKING : chunk recebido\nconteúdo acumulado no thinking_buffer

    IN_THINKING --> STREAMING : tag de fechamento detectada\nthinking_block extraído e emitido\nbuffer limpo

    STREAMING --> STREAMING : chunk recebido\nconteúdo emitido diretamente ao cliente

    note right of PRE_CONTENT
        Buffering cauteloso: mantém apenas
        os últimos max_tag_length chars
        para detectar tags que chegam
        fragmentadas entre chunks
    end note

    note right of IN_THINKING
        4 modos de handling:
        - as_thinking_block (Anthropic)
        - as_reasoning_content (OpenAI)
        - strip (descarta)
        - passthrough (mantém como texto)
    end note
```

### Estados do ThinkingParser

| Estado | Descrição | Transição de Saída |
|--------|-----------|-------------------|
| PRE_CONTENT | Aguardando início do conteúdo ou tag de thinking | Tag abertura detectada → IN_THINKING; conteúdo normal → STREAMING |
| IN_THINKING | Acumulando conteúdo do bloco de thinking | Tag fechamento detectada → STREAMING |
| STREAMING | Emitindo conteúdo diretamente | Estado terminal (por requisição) |

---

## 4. Ciclo de Vida de Requisição HTTP (`KiroHttpClient`)

```mermaid
stateDiagram-v2
    [*] --> SENDING : request_with_retry() chamado

    SENDING --> SUCCESS : HTTP 200
    SENDING --> FORCE_REFRESH : HTTP 403
    SENDING --> BACKOFF : HTTP 429 ou 5xx
    SENDING --> BACKOFF : timeout (connect ou read)
    SENDING --> ERROR_FINAL : 4xx (não 403/429)

    FORCE_REFRESH --> SENDING : force_refresh() + retry\n(apenas 1 vez)
    FORCE_REFRESH --> ERROR_FINAL : refresh falhou

    BACKOFF --> SENDING : aguarda backoff exponencial\nattempt < MAX_RETRIES
    BACKOFF --> ERROR_FINAL : attempt >= MAX_RETRIES

    SUCCESS --> [*] : resposta retornada ao caller
    ERROR_FINAL --> [*] : exceção ou HTTPException propagada

    note right of BACKOFF
        Backoff: base_delay * 2^attempt
        Jitter aleatório adicionado
        MAX_RETRIES configurável
    end note
```

---

## 5. Ciclo de Vida de Streaming com First Token Retry

```mermaid
stateDiagram-v2
    [*] --> WAITING_FIRST_TOKEN : stream iniciado

    WAITING_FIRST_TOKEN --> STREAMING : primeiro token recebido\ndentro do timeout (15s default)

    WAITING_FIRST_TOKEN --> RETRY : timeout de primeiro token\nattempt < MAX_RETRIES

    RETRY --> WAITING_FIRST_TOKEN : nova requisição enviada

    RETRY --> ERROR : attempt >= MAX_RETRIES

    STREAMING --> COMPLETE : stream finalizado normalmente\n(stop_reason recebido)

    STREAMING --> TRUNCATED : stream interrompido sem stop_reason\n(Truncation Recovery detecta)

    COMPLETE --> [*]
    TRUNCATED --> [*] : notificação de truncamento\nenviada ao cliente
    ERROR --> [*] : erro propagado
```

---

## 6. Inicialização Lazy de Account

```mermaid
stateDiagram-v2
    [*] --> UNINITIALIZED : Account criada\napenas id definido

    UNINITIALIZED --> INITIALIZING : get_next_account() chamado\nauth_manager is None

    INITIALIZING --> READY : _initialize_account() bem-sucedido\nauth_manager, model_cache, model_resolver criados\nmodelos carregados

    INITIALIZING --> FAILED : _initialize_account() falhou\nfailures += 1

    FAILED --> INITIALIZING : próxima chamada get_next_account()\napós cooldown do Circuit Breaker

    READY --> CACHE_STALE : age > ACCOUNT_CACHE_TTL (12h)

    CACHE_STALE --> READY : _refresh_account_models() chamado\ncache atualizado

    READY --> [*] : account retornada ao caller
```
