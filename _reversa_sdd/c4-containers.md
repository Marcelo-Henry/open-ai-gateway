# C4 — Nível 2: Containers

> Escala de confiança: 🟢 CONFIRMADO | 🟡 INFERIDO | 🔴 LACUNA

```mermaid
C4Container
    title AI Gateway — Diagrama de Containers

    Person(dev, "Cliente API", "Desenvolvedor ou agente AI usando OpenAI/Anthropic SDK")

    System_Boundary(gateway, "AI Gateway") {
        Container(fastapi, "FastAPI Application", "Python 3.10+ / FastAPI / Uvicorn", "Servidor HTTP principal. Expõe endpoints OpenAI e Anthropic. Gerencia autenticação de clientes, roteamento e orquestração.")

        Container(account_mgr, "Account Manager", "Python / asyncio", "Gerencia múltiplas contas Kiro com Circuit Breaker, sticky behavior e failover. Persiste estado em state.json.")

        Container(auth_mgr, "Auth Manager", "Python / httpx", "Gerencia ciclo de vida de access tokens por conta. Suporta 4 fontes de credenciais e 2 tipos de auth. Thread-safe via asyncio.Lock.")

        Container(model_resolver, "Model Resolver", "Python / regex", "Pipeline de 4 camadas para resolução de nomes de modelos. Cache dinâmico com TTL de 12h.")

        Container(converter, "Converters", "Python", "Traduz formatos OpenAI/Anthropic para KiroPayload. Pipeline de 8 etapas de normalização de mensagens.")

        Container(streaming, "Streaming Engine", "Python / asyncio", "Parseia AWS Event Stream binário. Converte para SSE OpenAI ou Anthropic. Gerencia ThinkingParser FSM e first-token retry.")

        Container(http_client, "HTTP Client", "Python / httpx", "Cliente HTTP com retry exponencial. Per-request para streaming, compartilhado para non-streaming.")

        Container(debug_logger, "Debug Logger", "Python / loguru", "Logging de requisições/respostas em disco. Modos: off, errors, all.")

        ContainerDb(state_json, "state.json", "JSON em disco", "Estado persistido do AccountManager: índice atual, failures, timestamps de cache por conta.")

        ContainerDb(creds_file, "Credenciais", "JSON ou SQLite em disco", "Access token, refresh token, region, profile ARN. Lido e atualizado pelo Auth Manager.")
    }

    System_Ext(kiro_api, "Kiro API", "Amazon Q Developer")
    System_Ext(kiro_auth, "Kiro Auth / AWS SSO OIDC", "Serviços de autenticação AWS")
    System_Ext(chatgpt, "ChatGPT Codex API", "Endpoint privado ChatGPT")

    Rel(dev, fastapi, "Requisições HTTP", "HTTPS / OpenAI ou Anthropic format")
    Rel(fastapi, account_mgr, "Obtém próxima conta disponível", "in-process")
    Rel(fastapi, converter, "Converte payload", "in-process")
    Rel(fastapi, streaming, "Processa stream de resposta", "in-process")
    Rel(account_mgr, auth_mgr, "Obtém access token", "in-process")
    Rel(account_mgr, model_resolver, "Resolve modelo", "in-process")
    Rel(account_mgr, state_json, "Lê/escreve estado", "I/O disco")
    Rel(auth_mgr, creds_file, "Lê/atualiza credenciais", "I/O disco")
    Rel(auth_mgr, kiro_auth, "Renova token", "HTTPS/JSON")
    Rel(http_client, kiro_api, "Envia KiroPayload", "HTTPS / AWS Event Stream")
    Rel(fastapi, http_client, "Delega requisição HTTP", "in-process")
    Rel(fastapi, debug_logger, "Loga req/resp", "in-process")
    Rel(fastapi, chatgpt, "Modelos gpt-*/codex-* (Codex Provider)", "HTTPS/JSON")
```

---

## Descrição dos Containers

| Container | Tecnologia | Responsabilidade Principal |
|-----------|-----------|---------------------------|
| 🟢 FastAPI Application | Python / FastAPI / Uvicorn | Entry point HTTP, autenticação de clientes, roteamento por formato de API |
| 🟢 Account Manager | Python / asyncio | Seleção de conta com Circuit Breaker, sticky, failover, persistência de estado |
| 🟢 Auth Manager | Python / httpx | Ciclo de vida de tokens por conta, refresh automático, graceful degradation |
| 🟢 Model Resolver | Python / regex | Normalização e resolução de nomes de modelos, cache com TTL |
| 🟢 Converters | Python | Tradução OpenAI/Anthropic → KiroPayload, normalização de mensagens |
| 🟢 Streaming Engine | Python / asyncio | Parse AWS Event Stream, conversão SSE, ThinkingParser FSM |
| 🟢 HTTP Client | Python / httpx | Retry exponencial, per-request para streaming, force_refresh em 403 |
| 🟢 Debug Logger | Python / loguru | Logging opcional de req/resp completos em disco |
| 🟢 state.json | JSON em disco | Estado persistido do AccountManager entre reinicializações |
| 🟢 Credenciais | JSON ou SQLite | Tokens de autenticação Kiro, lidos e atualizados pelo Auth Manager |
