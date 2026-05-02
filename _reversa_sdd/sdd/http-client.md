# KiroHttpClient — Cliente HTTP com Retry

## Visão Geral
Cliente HTTP assíncrono com lógica de retry exponencial para comunicação com a Kiro API. Gerencia dois modos de operação: cliente compartilhado (connection pooling para non-streaming) e cliente por requisição (para streaming, evitando CLOSE_WAIT).

## Responsabilidades
- Enviar requisições HTTP para a Kiro API com retry automático
- Gerenciar refresh de token em respostas 403
- Aplicar backoff exponencial em 429 e 5xx
- Usar cliente per-request para streaming (evitar CLOSE_WAIT)
- Classificar erros de rede em categorias user-friendly
- Montar headers Kiro com access token e fingerprint

## Interface

**Classe principal:**
```python
class KiroHttpClient:
    def __init__(
        self,
        auth_manager: KiroAuthManager,
        timeout: float = 30.0,
        max_retries: int = 3,
    )

    async def request_with_retry(
        self,
        method: str,
        url: str,
        json: Dict[str, Any],
        stream: bool = False,
    ) -> Union[httpx.Response, AsyncIterator[bytes]]
        # Non-streaming: retorna Response completo.
        # Streaming: retorna async iterator de chunks.

    async def force_refresh(self) -> str
        # Força refresh do access token (chamado após 403).
```

## Regras de Negócio

- 🟢 **RN-HC-01**: HTTP 403 → `force_refresh()` + retry uma vez; se falhar novamente, propaga erro
- 🟢 **RN-HC-02**: HTTP 429 ou 5xx → backoff exponencial `base_delay * 2^attempt` + jitter aleatório
- 🟢 **RN-HC-03**: Timeout (connect ou read) → backoff exponencial + retry até `max_retries`
- 🟢 **RN-HC-04**: 4xx (exceto 403/429) → não faz retry, propaga erro imediatamente
- 🟢 **RN-HC-05**: Streaming usa `async with httpx.AsyncClient()` por requisição (ADR-001, Issues #38, #54)
- 🟢 **RN-HC-06**: Non-streaming usa cliente compartilhado (`self._shared_client`) para connection pooling
- 🟡 **RN-HC-07**: Headers incluem `User-Agent` simulando Kiro IDE com fingerprint derivado das credenciais

## Fluxo Principal

1. Obtém access token via `auth_manager.get_access_token()`
2. Monta headers via `get_kiro_headers(token, fingerprint)`
3. Se streaming → cria `httpx.AsyncClient` por requisição
4. Se non-streaming → usa `self._shared_client`
5. Envia requisição HTTP
6. Se 200 → retorna resposta
7. Se 403 → `force_refresh()`, atualiza headers, retry uma vez
8. Se 429/5xx → aguarda backoff, retry até `max_retries`
9. Se timeout → aguarda backoff, retry até `max_retries`
10. Se `max_retries` esgotado → propaga última exceção

## Fluxos Alternativos

- **403 após force_refresh**: propaga `HTTPException(401)` com mensagem de auth
- **Esgotamento de retries em 429**: propaga `HTTPException(429)` com mensagem de rate limit
- **Esgotamento de retries em timeout**: propaga `TimeoutError` classificado
- **Erro de DNS/rede**: classificado via `network_errors.py`, propaga com mensagem user-friendly

## Dependências

- `httpx` — cliente HTTP assíncrono
- `kiro/auth.py` — `KiroAuthManager.get_access_token()`, `force_refresh()`
- `kiro/utils.py` — `get_kiro_headers()`
- `kiro/network_errors.py` — classificação de erros de rede
- `kiro/config.py` — `MAX_RETRIES`, `BASE_RETRY_DELAY`, timeouts

## Requisitos Não Funcionais

| Tipo | Requisito inferido | Evidência no código | Confiança |
|------|--------------------|---------------------|-----------|
| Disponibilidade | Retry exponencial em 429/5xx/timeout | `kiro/http_client.py:227` | 🟢 |
| Disponibilidade | Force refresh automático em 403 | `kiro/http_client.py:227` | 🟢 |
| Resiliência | Per-request client evita CLOSE_WAIT em streaming | `kiro/http_client.py:227` | 🟢 |
| Performance | Connection pooling para non-streaming | `kiro/http_client.py` — `_shared_client` | 🟢 |

## Critérios de Aceitação

```gherkin
Dado que a Kiro API retorna 200
Quando request_with_retry() é chamado
Então retorna a resposta sem retry

Dado que a Kiro API retorna 403 (token expirado)
Quando request_with_retry() é chamado
Então faz force_refresh() e tenta novamente uma vez

Dado que a Kiro API retorna 429 repetidamente
Quando request_with_retry() é chamado
Então tenta até max_retries vezes com backoff exponencial, depois propaga erro

Dado uma requisição de streaming
Quando request_with_retry() é chamado com stream=True
Então usa cliente httpx por requisição (não o compartilhado)
```

## Prioridade

| Requisito | MoSCoW | Justificativa |
|-----------|--------|---------------|
| request_with_retry() | Must | Toda comunicação com Kiro API passa por aqui |
| Retry em 429/5xx | Must | Kiro API tem rate limits e instabilidades ocasionais |
| Force refresh em 403 | Must | Tokens expiram — sem isso, serviço para após 1h |
| Per-request client para streaming | Must | Evita vazamento de conexões (ADR-001) |
| Backoff com jitter | Should | Evita thundering herd em múltiplas instâncias |

## Rastreabilidade de Código

| Arquivo | Função / Classe | Cobertura |
|---------|-----------------|-----------|
| `kiro/http_client.py` | `KiroHttpClient` | 🟢 |
| `kiro/http_client.py:227` | `request_with_retry` — CLOSE_WAIT prevention | 🟢 |
| `kiro/utils.py:82` | `get_kiro_headers` — User-Agent com fingerprint | 🟢 |
