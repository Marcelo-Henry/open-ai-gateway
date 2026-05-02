# Spec Impact Matrix — Open AI Gateway

> Escala de confiança: 🟢 CONFIRMADO | 🟡 INFERIDO | 🔴 LACUNA
>
> **Como ler**: Linha = componente que sofre mudança. Coluna = componente impactado.
> - 🔴 **DIRETO** — mudança quase certamente quebra o componente
> - 🟡 **INDIRETO** — mudança pode afetar o componente dependendo do escopo
> - ⚪ **NENHUM** — sem impacto esperado

---

## Matriz de Impacto

| Componente Alterado | routes_openai | routes_anthropic | converters_core | converters_openai | converters_anthropic | streaming_core | streaming_openai | streaming_anthropic | parsers | thinking_parser | auth | account_manager | model_resolver | http_client | mcp_tools | codex_provider | truncation_recovery | config |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **config.py** | 🟡 | 🟡 | 🟡 | 🟡 | 🟡 | 🟡 | 🟡 | 🟡 | 🟡 | 🟡 | 🔴 | 🔴 | 🟡 | 🟡 | 🟡 | 🟡 | 🟡 | — |
| **auth.py** | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | — | 🔴 | ⚪ | 🔴 | ⚪ | ⚪ | ⚪ | ⚪ |
| **account_manager.py** | 🔴 | 🔴 | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | 🟡 | — | 🟡 | 🟡 | ⚪ | ⚪ | ⚪ | ⚪ |
| **converters_core.py** | 🟡 | 🟡 | — | 🔴 | 🔴 | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | 🟡 | ⚪ | 🟡 | ⚪ |
| **converters_openai.py** | 🔴 | ⚪ | 🟡 | — | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ |
| **converters_anthropic.py** | ⚪ | 🔴 | 🟡 | ⚪ | — | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ |
| **streaming_core.py** | 🟡 | 🟡 | ⚪ | ⚪ | ⚪ | — | 🔴 | 🔴 | 🟡 | 🟡 | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ |
| **streaming_openai.py** | 🔴 | ⚪ | ⚪ | ⚪ | ⚪ | 🟡 | — | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ |
| **streaming_anthropic.py** | ⚪ | 🔴 | ⚪ | ⚪ | ⚪ | 🟡 | ⚪ | — | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ |
| **parsers.py** | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | 🔴 | 🟡 | 🟡 | — | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ |
| **thinking_parser.py** | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | 🔴 | 🟡 | 🟡 | ⚪ | — | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ |
| **http_client.py** | 🟡 | 🟡 | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | 🔴 | ⚪ | — | ⚪ | ⚪ | ⚪ | ⚪ |
| **model_resolver.py** | 🟡 | 🟡 | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | 🔴 | — | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ |
| **models_openai.py** | 🔴 | ⚪ | 🟡 | 🔴 | ⚪ | ⚪ | 🟡 | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ |
| **models_anthropic.py** | ⚪ | 🔴 | 🟡 | ⚪ | 🔴 | ⚪ | ⚪ | 🟡 | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ |
| **mcp_tools.py** | ⚪ | 🔴 | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | — | ⚪ | ⚪ | ⚪ |
| **codex_provider.py** | ⚪ | 🔴 | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | — | ⚪ | ⚪ |
| **truncation_recovery.py** | 🟡 | ⚪ | 🔴 | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | — | ⚪ |
| **network_errors.py** | 🟡 | 🟡 | ⚪ | ⚪ | ⚪ | 🔴 | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | 🟡 | ⚪ | 🔴 | ⚪ | ⚪ | ⚪ | ⚪ |
| **utils.py** | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | ⚪ | 🟡 | ⚪ | 🔴 | ⚪ | ⚪ | ⚪ | ⚪ |

---

## Componentes de Alto Risco (muitos dependentes diretos)

| Componente | Dependentes Diretos (🔴) | Risco |
|---|---|---|
| 🟢 **config.py** | auth, account_manager | Qualquer mudança de constante pode afetar comportamento de toda a aplicação |
| 🟢 **converters_core.py** | converters_openai, converters_anthropic | Núcleo da tradução de payload — mudanças afetam ambas as APIs |
| 🟢 **streaming_core.py** | streaming_openai, streaming_anthropic | Núcleo do streaming — mudanças afetam ambos os formatos de saída |
| 🟢 **parsers.py** | streaming_core | Parser do protocolo binário AWS — mudanças quebram todo o streaming |
| 🟢 **auth.py** | account_manager, http_client | Mudanças no ciclo de vida de tokens afetam toda autenticação |
| 🟢 **account_manager.py** | routes_openai, routes_anthropic | Ponto central de seleção de conta — mudanças afetam todo roteamento |

---

## Componentes Isolados (baixo risco de propagação)

| Componente | Motivo do Isolamento |
|---|---|
| 🟢 **debug_logger.py** | Apenas logging — sem impacto funcional |
| 🟢 **debug_middleware.py** | ASGI middleware passthrough — sem impacto em lógica de negócio |
| 🟢 **tokenizer.py** | Usado apenas em `/count_tokens` — sem impacto em fluxo principal |
| 🟢 **codex_provider.py** | Roteamento alternativo isolado — ativado apenas para gpt-*/codex-* |
| 🟢 **exceptions.py** | Handlers globais — mudanças afetam apenas formato de erros |

---

## Dívidas Técnicas Identificadas

| # | Componente | Dívida | Severidade |
|---|---|---|---|
| 1 | 🟢 `requirements.txt` | Dependências sem versão pinada (fastapi, httpx, etc.) — risco de breaking changes em atualizações | Alta |
| 2 | 🟢 `tests/` | Apenas 3 arquivos de teste para 18 módulos — cobertura muito baixa | Alta |
| 3 | 🟡 `converters_core.py` | Função `build_kiro_payload` com ~200 linhas — candidata a decomposição | Média |
| 4 | 🟡 `account_manager.py` | Classe `AccountManager` com ~800 linhas — múltiplas responsabilidades | Média |
| 5 | 🟡 `codex_provider.py` | System prompt cacheado de URL externa (GitHub) — dependência de rede em startup | Média |
| 6 | 🟡 `auth.py` | Sem lock de arquivo para SQLite — race condition possível com múltiplas instâncias do gateway | Média |
| 7 | 🟡 `state.json` | Persistência via rename atômico mas sem lock — race condition com múltiplas instâncias | Baixa |
| 8 | 🟡 Geral | Ausência de métricas/observabilidade (Prometheus, OpenTelemetry) | Baixa |
