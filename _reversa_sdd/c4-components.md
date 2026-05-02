# C4 — Nível 3: Componentes

> Escala de confiança: 🟢 CONFIRMADO | 🟡 INFERIDO | 🔴 LACUNA

---

## Container: FastAPI Application

```mermaid
C4Component
    title FastAPI Application — Componentes Internos

    Container_Boundary(fastapi, "FastAPI Application") {
        Component(routes_openai, "routes_openai.py", "FastAPI Router", "Endpoints OpenAI: GET /v1/models, POST /v1/chat/completions. Autenticação via Authorization: Bearer.")
        Component(routes_anthropic, "routes_anthropic.py", "FastAPI Router", "Endpoints Anthropic: POST /v1/messages, POST /v1/messages/count_tokens. Autenticação via x-api-key ou Bearer.")
        Component(main, "main.py", "FastAPI App", "Entry point. Registra routers, configura CORS, inicia AccountManager e background tasks.")
        Component(exceptions, "exceptions.py", "Exception Handlers", "Handlers globais para HTTPException e erros não tratados. Formata respostas de erro.")
        Component(debug_middleware, "debug_middleware.py", "ASGI Middleware", "Intercepta req/resp para debug logging. Ativado apenas quando DEBUG_MODE != off.")
        Component(tokenizer, "tokenizer.py", "Token Counter", "Contagem de tokens via tiktoken (cl100k_base). Usado em /count_tokens e estimativas de payload.")
        Component(config, "config.py", "Configuration", "Todas as constantes e variáveis de ambiente. Single source of truth para configuração.")
    }

    Container_Ext(account_mgr, "Account Manager", "Seleção de conta")
    Container_Ext(converter, "Converters", "Tradução de payload")
    Container_Ext(streaming, "Streaming Engine", "Processamento de stream")
    Container_Ext(http_client, "HTTP Client", "Requisições HTTP")

    Rel(main, routes_openai, "Registra router")
    Rel(main, routes_anthropic, "Registra router")
    Rel(main, debug_middleware, "Adiciona middleware")
    Rel(routes_openai, account_mgr, "get_next_account()")
    Rel(routes_openai, converter, "build_kiro_payload()")
    Rel(routes_openai, streaming, "stream_kiro_to_openai()")
    Rel(routes_openai, http_client, "request_with_retry()")
    Rel(routes_anthropic, account_mgr, "get_next_account()")
    Rel(routes_anthropic, converter, "build_kiro_payload_anthropic()")
    Rel(routes_anthropic, streaming, "stream_kiro_to_anthropic()")
    Rel(routes_anthropic, http_client, "request_with_retry()")
    Rel(routes_anthropic, tokenizer, "count_tokens()")
```

---

## Container: Converters

```mermaid
C4Component
    title Converters — Componentes Internos

    Container_Boundary(conv, "Converters") {
        Component(conv_core, "converters_core.py", "Core Logic", "Pipeline central de conversão: normalização de mensagens, construção de KiroPayload, tool processing, payload guards.")
        Component(conv_openai, "converters_openai.py", "OpenAI Adapter", "Traduz ChatCompletionRequest (OpenAI) para UnifiedMessage. Chama converters_core.")
        Component(conv_anthropic, "converters_anthropic.py", "Anthropic Adapter", "Traduz AnthropicMessagesRequest para UnifiedMessage. Chama converters_core.")
        Component(trunc_recovery, "truncation_recovery.py", "Truncation Recovery", "Detecta e modifica tool_results truncados pela Kiro API (Issue #56).")
        Component(mcp_tools, "mcp_tools.py", "MCP Tools Handler", "Gerencia web_search nativo (Path A) e auto-injeção (Path B). Double JSON parse.")
        Component(codex_provider, "codex_provider.py", "Codex Provider", "Roteamento alternativo para gpt-*/codex-* via ChatGPT OAuth.")
    }

    Component_Ext(models_openai, "models_openai.py", "Pydantic Models OpenAI")
    Component_Ext(models_anthropic, "models_anthropic.py", "Pydantic Models Anthropic")

    Rel(conv_openai, models_openai, "Valida request")
    Rel(conv_openai, conv_core, "build_kiro_payload()")
    Rel(conv_anthropic, models_anthropic, "Valida request")
    Rel(conv_anthropic, conv_core, "build_kiro_payload()")
    Rel(conv_core, trunc_recovery, "Modifica tool_results truncados")
```

---

## Container: Streaming Engine

```mermaid
C4Component
    title Streaming Engine — Componentes Internos

    Container_Boundary(stream, "Streaming Engine") {
        Component(stream_core, "streaming_core.py", "Core Streaming", "parse_kiro_stream(): orquestra AwsEventStreamParser + ThinkingParser. Gerencia first-token timeout e retry.")
        Component(stream_openai, "streaming_openai.py", "OpenAI Formatter", "stream_kiro_to_openai(): converte KiroEvents para SSE formato OpenAI. format_openai_chunk().")
        Component(stream_anthropic, "streaming_anthropic.py", "Anthropic Formatter", "stream_kiro_to_anthropic(): converte KiroEvents para SSE formato Anthropic. format_anthropic_event().")
        Component(parsers, "parsers.py", "AWS Event Stream Parser", "AwsEventStreamParser: parseia frames binários AWS. Detecta cumulative snapshots de tool args. Emite KiroEvents.")
        Component(thinking_parser, "thinking_parser.py", "Thinking Parser FSM", "ThinkingParser: FSM de 3 estados (PRE_CONTENT→IN_THINKING→STREAMING). Extrai thinking blocks.")
        Component(network_errors, "network_errors.py", "Network Error Classifier", "Classifica erros httpx em categorias user-friendly com passos de troubleshooting.")
    }

    Rel(stream_core, parsers, "feed(chunk)")
    Rel(stream_core, thinking_parser, "feed(content)")
    Rel(stream_openai, stream_core, "parse_kiro_stream()")
    Rel(stream_anthropic, stream_core, "parse_kiro_stream()")
    Rel(stream_core, network_errors, "classify_error()")
```

---

## Container: Account Manager

```mermaid
C4Component
    title Account Manager — Componentes Internos

    Container_Boundary(acct, "Account Manager") {
        Component(acct_mgr, "account_manager.py / AccountManager", "Orchestrator", "Gerencia lista de accounts. Circuit Breaker, sticky, failover, lazy init, TTL cache, persistência.")
        Component(acct_errors, "account_errors.py", "Error Classifier", "Classifica erros HTTP da Kiro API por tipo (RECOVERABLE, UNRECOVERABLE, QUOTA). Determina se deve fazer failover.")
        Component(kiro_errors, "kiro_errors.py", "Kiro Error Handler", "Formata erros da Kiro API para o cliente. Inclui link para issues do GitHub.")
        Component(auth, "auth.py / KiroAuthManager", "Auth Manager", "Ciclo de vida de tokens. 4 fontes de credenciais, 2 tipos de auth, graceful degradation.")
        Component(cache, "cache.py / ModelInfoCache", "Model Cache", "Cache de metadados de modelos com TTL. Busca de /ListAvailableModels.")
        Component(model_res, "model_resolver.py / ModelResolver", "Model Resolver", "Pipeline de 4 camadas. normalize_model_name() com 5 padrões regex.")
        Component(http_client, "http_client.py / KiroHttpClient", "HTTP Client", "Retry exponencial. force_refresh em 403. Per-request para streaming.")
        Component(utils, "utils.py", "Utilities", "get_kiro_headers(): monta headers com fingerprint. Helpers de formatação.")
    }

    Rel(acct_mgr, auth, "get_access_token()")
    Rel(acct_mgr, cache, "fetch_models()")
    Rel(acct_mgr, model_res, "get_available_models()")
    Rel(acct_mgr, http_client, "request_with_retry()")
    Rel(acct_mgr, acct_errors, "classify_error()")
    Rel(acct_mgr, kiro_errors, "format_error()")
    Rel(http_client, auth, "force_refresh() em 403")
    Rel(http_client, utils, "get_kiro_headers()")
```
