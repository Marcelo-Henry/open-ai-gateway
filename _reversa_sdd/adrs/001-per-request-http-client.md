# ADR-001: Per-Request HTTP Client para Streaming

**Status**: Aceito  
**Data**: 2025 (Issues #38, #54)  
**Contexto**: kiro/routes_openai.py:598, kiro/routes_anthropic.py:808, kiro/http_client.py:227

---

## Contexto

O gateway usa `httpx.AsyncClient` para comunicação com a Kiro API. Inicialmente, um cliente compartilhado (connection pool) era reutilizado para todas as requisições, incluindo streaming.

Quando um cliente VPN se desconecta durante uma requisição de streaming, a conexão TCP fica no estado `CLOSE_WAIT` — o lado remoto fechou a conexão, mas o gateway não liberou o socket. Com um cliente compartilhado, essas conexões acumulam no pool e nunca são liberadas, causando vazamento de file descriptors e eventual falha do processo.

## Decisão

Requisições de **streaming** usam um `httpx.AsyncClient` criado por requisição (via `async with httpx.AsyncClient(...) as client`), descartado ao final de cada stream.

Requisições **não-streaming** continuam usando o cliente compartilhado para aproveitar connection pooling.

```python
# Streaming: per-request client
# For streaming: use per-request client to avoid CLOSE_WAIT leak on VPN disconnect (issue #54)
async with httpx.AsyncClient(timeout=timeout) as client:
    async with client.stream("POST", url, ...) as response:
        ...

# Non-streaming: shared client (connection pooling)
response = await self._shared_client.post(url, ...)
```

## Consequências

**Positivas**:
- Elimina vazamento de conexões CLOSE_WAIT em desconexões de VPN
- Cada stream tem ciclo de vida isolado e determinístico

**Negativas**:
- Overhead de criação de cliente TCP por requisição de streaming
- Sem reutilização de conexão para streaming (sem keep-alive entre streams)

**Neutras**:
- Non-streaming mantém comportamento anterior com pool compartilhado
