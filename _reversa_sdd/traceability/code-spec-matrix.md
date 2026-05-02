# Code/Spec Matrix — AI Gateway

> Escala de confiança: 🟢 Cobertura completa | 🟡 Cobertura parcial | — Sem spec correspondente

---

## Matriz de Rastreabilidade

| Arquivo | Spec correspondente | Cobertura |
|---------|---------------------|-----------|
| `main.py` | `sdd/routes.md` | 🟡 |
| `kiro/__init__.py` | — | — |
| `kiro/config.py` | Referenciado em todas as specs | 🟡 |
| `kiro/auth.py` | `sdd/auth.md` | 🟢 |
| `kiro/account_manager.py` | `sdd/account-manager.md` | 🟢 |
| `kiro/cache.py` | `sdd/account-manager.md` (dependência) | 🟡 |
| `kiro/model_resolver.py` | `sdd/model-resolver.md` | 🟢 |
| `kiro/http_client.py` | `sdd/http-client.md` | 🟢 |
| `kiro/routes_openai.py` | `sdd/routes.md` | 🟢 |
| `kiro/routes_anthropic.py` | `sdd/routes.md` | 🟢 |
| `kiro/converters_core.py` | `sdd/converters-core.md` | 🟢 |
| `kiro/converters_openai.py` | `sdd/converters-core.md` (adaptador) | 🟡 |
| `kiro/converters_anthropic.py` | `sdd/converters-core.md` (adaptador) | 🟡 |
| `kiro/streaming_core.py` | `sdd/streaming-core.md` | 🟢 |
| `kiro/streaming_openai.py` | `sdd/streaming-core.md` (formatador) | 🟡 |
| `kiro/streaming_anthropic.py` | `sdd/streaming-core.md` (formatador) | 🟡 |
| `kiro/parsers.py` | `sdd/parsers.md` | 🟢 |
| `kiro/thinking_parser.py` | `sdd/thinking-parser.md` | 🟢 |
| `kiro/models_openai.py` | `openapi/kiro-gateway-api.yaml` | 🟡 |
| `kiro/models_anthropic.py` | `openapi/kiro-gateway-api.yaml` | 🟡 |
| `kiro/network_errors.py` | `sdd/http-client.md` (dependência) | 🟡 |
| `kiro/exceptions.py` | `sdd/routes.md` (tratamento de erros) | 🟡 |
| `kiro/debug_logger.py` | `user-stories/fluxos-principais.md` (US-009) | 🟡 |
| `kiro/debug_middleware.py` | `user-stories/fluxos-principais.md` (US-009) | 🟡 |
| `kiro/tokenizer.py` | `user-stories/fluxos-principais.md` (US-010) | 🟡 |
| `kiro/utils.py` | `sdd/http-client.md` (dependência) | 🟡 |
| `kiro/mcp_tools.py` | `sdd/mcp-codex.md` | 🟢 |
| `kiro/codex_provider.py` | `sdd/mcp-codex.md` | 🟢 |
| `kiro/truncation_recovery.py` | `adrs/002-truncation-recovery.md` | 🟡 |
| `kiro/account_errors.py` | `sdd/account-manager.md` (dependência) | 🟡 |
| `kiro/kiro_errors.py` | `sdd/routes.md` (tratamento de erros) | 🟡 |
| `tests/conftest.py` | — | — |
| `tests/unit/test_auth_manager.py` | `sdd/auth.md` | 🟡 |
| `tests/unit/test_converters.py` | `sdd/converters-core.md` | 🟡 |
| `tests/unit/test_streaming.py` | `sdd/streaming-core.md` | 🟡 |
| `tests/integration/` | — | — |
| `main.py` | `sdd/routes.md` | 🟡 |
| `.env.example` | `openapi/kiro-gateway-api.yaml` | 🟡 |
| `Dockerfile` | `architecture.md` | 🟡 |
| `docker-compose.yml` | `architecture.md` | 🟡 |
| `.github/workflows/docker.yml` | `architecture.md` | 🟡 |

---

## Arquivos sem Spec Dedicada (candidatos a análise adicional)

| Arquivo | Motivo | Recomendação |
|---------|--------|--------------|
| `kiro/cache.py` | ModelInfoCache — lógica de cache com TTL | Adicionar seção em `sdd/account-manager.md` ou spec dedicada |
| `kiro/config.py` | 500+ linhas de configuração — todas as constantes | Spec de configuração dedicada (`sdd/config.md`) |
| `kiro/network_errors.py` | Classificação de erros com troubleshooting steps | Adicionar seção em `sdd/http-client.md` |
| `kiro/account_errors.py` | Classificação de erros por tipo (RECOVERABLE, etc.) | Adicionar seção em `sdd/account-manager.md` |
| `kiro/kiro_errors.py` | Formatação de erros da Kiro API para o cliente | Adicionar seção em `sdd/routes.md` |
| `kiro/truncation_recovery.py` | Lógica de detecção e modificação de truncamento | Spec dedicada (`sdd/truncation-recovery.md`) |
| `kiro/debug_logger.py` | Sistema de logging em disco | Spec dedicada (`sdd/debug-logger.md`) |
| `kiro/tokenizer.py` | Contagem de tokens via tiktoken | Seção em `sdd/routes.md` |
| `kiro/converters_openai.py` | Adaptador OpenAI específico | Seção dedicada em `sdd/converters-core.md` |
| `kiro/converters_anthropic.py` | Adaptador Anthropic específico | Seção dedicada em `sdd/converters-core.md` |
| `kiro/streaming_openai.py` | Formatador SSE OpenAI | Seção dedicada em `sdd/streaming-core.md` |
| `kiro/streaming_anthropic.py` | Formatador SSE Anthropic | Seção dedicada em `sdd/streaming-core.md` |

---

## Resumo de Cobertura

| Métrica | Valor |
|---------|-------|
| Total de arquivos `.py` | 28 |
| Arquivos com spec 🟢 completa | 10 (36%) |
| Arquivos com spec 🟡 parcial | 16 (57%) |
| Arquivos sem spec — | 2 (7%) |
| **Cobertura estimada** | **~75%** |

### Specs geradas

| Tipo | Quantidade |
|------|-----------|
| SDDs de componente | 9 |
| ADRs retroativos | 7 |
| Diagramas C4 | 3 (Contexto, Containers, Componentes) |
| Flowcharts | 3 (Auth, Request Flow, Converters) |
| Máquinas de estado | 6 |
| OpenAPI spec | 1 |
| User Stories | 10 (em 4 épicos) |
| ERD | 1 (11 entidades) |
| Spec Impact Matrix | 1 (19 componentes) |
| **Total de artefatos** | **41** |
