# Inventário do Projeto — codex-gateway

> Gerado pelo Reversa Scout em 2026-05-01
> Escala de confiança: 🟢 CONFIRMADO | 🟡 INFERIDO | 🔴 LACUNA

---

## Visão Geral

| Campo | Valor |
|---|---|
| Nome do projeto | codex-gateway |
| Versão | 2.4-dev.10 |
| Linguagem principal | Python 3.10+ |
| Framework principal | FastAPI + Uvicorn |
| Licença | AGPL-3.0 |
| Total de arquivos Python | 40 |

---

## Estrutura de Diretórios 🟢

```
codex-gateway/
├── main.py                        # Entry point da aplicação
├── requirements.txt               # Dependências Python
├── pytest.ini                     # Configuração de testes
├── Dockerfile                     # Imagem Docker
├── docker-compose.yml             # Orquestração Docker
├── .env.example                   # Template de configuração
├── credentials.json               # Credenciais de contas (runtime)
├── state.json                     # Estado persistido do AccountManager
├── start.sh                       # Script de inicialização
├── manual_api_test.py             # Script de teste manual (não é unit test)
├── gateway.log                    # Log da aplicação
├── kiro/                          # Pacote principal
│   ├── config.py                  # Configurações e constantes centralizadas
│   ├── auth.py                    # Gerenciador de autenticação Kiro
│   ├── account_manager.py         # Sistema de múltiplas contas com failover
│   ├── account_errors.py          # Erros do sistema de contas
│   ├── cache.py                   # Cache de metadados de modelos
│   ├── model_resolver.py          # Resolução dinâmica de modelos
│   ├── http_client.py             # Cliente HTTP com retry automático
│   ├── routes_openai.py           # Endpoints compatíveis com OpenAI
│   ├── routes_anthropic.py        # Endpoints compatíveis com Anthropic
│   ├── converters_core.py         # Lógica de conversão compartilhada
│   ├── converters_openai.py       # Conversor OpenAI → Kiro
│   ├── converters_anthropic.py    # Conversor Anthropic → Kiro
│   ├── streaming_core.py          # Lógica de streaming compartilhada
│   ├── streaming_openai.py        # Streaming Kiro → OpenAI SSE
│   ├── streaming_anthropic.py     # Streaming Kiro → Anthropic SSE
│   ├── parsers.py                 # Parser de AWS event stream
│   ├── thinking_parser.py         # Parser de blocos de thinking (FSM)
│   ├── models_openai.py           # Modelos Pydantic (OpenAI)
│   ├── models_anthropic.py        # Modelos Pydantic (Anthropic)
│   ├── network_errors.py          # Classificação de erros de rede
│   ├── kiro_errors.py             # Erros específicos da Kiro API
│   ├── exceptions.py              # Handlers de exceção FastAPI
│   ├── debug_logger.py            # Sistema de debug logging
│   ├── debug_middleware.py        # Middleware de debug
│   ├── tokenizer.py               # Contagem de tokens (tiktoken)
│   ├── utils.py                   # Utilitários gerais
│   ├── payload_guards.py          # Validação e guarda de payload
│   ├── mcp_tools.py               # Emulação de ferramentas MCP
│   ├── truncation_recovery.py     # Recuperação de truncamento
│   ├── truncation_state.py        # Estado de truncamento
│   ├── codex_auth.py              # Autenticação OAuth Codex CLI
│   └── codex_provider.py          # Provider Codex CLI (ChatGPT)
├── tests/
│   ├── __init__.py
│   └── unit/
│       ├── __init__.py
│       ├── test_codex_tools.py
│       ├── test_parsers_tool_stream.py
│       └── test_streaming_anthropic.py
├── debug_logs/                    # Logs de debug (gerados em runtime)
└── docs/                          # Documentação adicional
```

---

## Módulos Identificados 🟢

| Módulo | Arquivos | Responsabilidade |
|---|---|---|
| **auth** | `auth.py`, `codex_auth.py` | Gerenciamento de tokens e autenticação |
| **account_manager** | `account_manager.py`, `account_errors.py` | Multi-conta com failover e Circuit Breaker |
| **routes** | `routes_openai.py`, `routes_anthropic.py` | Endpoints FastAPI (OpenAI e Anthropic) |
| **converters** | `converters_core.py`, `converters_openai.py`, `converters_anthropic.py` | Tradução de formatos de API |
| **streaming** | `streaming_core.py`, `streaming_openai.py`, `streaming_anthropic.py` | Processamento de SSE streams |
| **parsers** | `parsers.py`, `thinking_parser.py` | Parsing de AWS event stream e thinking blocks |
| **models** | `models_openai.py`, `models_anthropic.py` | Modelos Pydantic de validação |
| **model_resolver** | `model_resolver.py`, `cache.py` | Resolução e cache de modelos |
| **http_client** | `http_client.py` | Cliente HTTP com retry e connection pooling |
| **config** | `config.py` | Configurações centralizadas |
| **errors** | `network_errors.py`, `kiro_errors.py`, `exceptions.py`, `account_errors.py` | Tratamento de erros |
| **debug** | `debug_logger.py`, `debug_middleware.py` | Logging de debug |
| **codex_provider** | `codex_auth.py`, `codex_provider.py` | Integração com Codex CLI (ChatGPT OAuth) |
| **payload_guards** | `payload_guards.py` | Validação de tamanho de payload |
| **mcp_tools** | `mcp_tools.py` | Emulação de ferramentas MCP (web_search) |
| **truncation** | `truncation_recovery.py`, `truncation_state.py` | Recuperação de respostas truncadas |
| **tokenizer** | `tokenizer.py` | Contagem de tokens via tiktoken |
| **utils** | `utils.py` | Utilitários gerais |

---

## Entry Points 🟢

| Arquivo | Tipo | Descrição |
|---|---|---|
| `main.py` | `app_entry` | Entry point principal — cria FastAPI app, registra rotas, gerencia lifecycle |
| `kiro/routes_openai.py` | `route_module` | Rotas OpenAI-compatíveis (`/v1/models`, `/v1/chat/completions`) |
| `kiro/routes_anthropic.py` | `route_module` | Rotas Anthropic-compatíveis (`/v1/messages`) |

---

## Arquivos de Configuração 🟢

| Arquivo | Propósito |
|---|---|
| `.env` / `.env.example` | Variáveis de ambiente (credenciais, portas, features) |
| `credentials.json` | Configuração de contas Kiro (gerado/migrado do .env) |
| `state.json` | Estado persistido do AccountManager (índice de conta atual) |
| `pytest.ini` | Configuração do pytest |
| `Dockerfile` | Build da imagem Docker |
| `docker-compose.yml` | Orquestração Docker com health check |

---

## CI/CD 🟡

Nenhum arquivo de CI/CD encontrado (`.github/workflows/`, `Jenkinsfile`, `.gitlab-ci.yml`).
O CLAUDE.md menciona um workflow `.github/workflows/docker.yml` — pode ter sido removido ou estar em branch diferente.

---

## Docker 🟢

| Arquivo | Presente |
|---|---|
| `Dockerfile` | ✅ |
| `docker-compose.yml` | ✅ |

- Base image: `python:3.10-slim`
- Usuário não-root: `kiro`
- Health check: `GET /health`
- Porta exposta: `8000`

---

## Banco de Dados 🟢

Nenhum banco de dados próprio. O projeto **lê** bancos SQLite externos:
- `~/.local/share/kiro-cli/data.sqlite3` — banco do kiro-cli (AWS SSO)
- `~/.aws/sso/cache/*.json` — cache SSO da AWS

Não há migrations, DDL ou ORM models no projeto.

---

## Cobertura de Testes 🟡

| Framework | Presente |
|---|---|
| pytest | ✅ |
| pytest-asyncio | ✅ |
| hypothesis | ✅ |

| Métrica | Valor |
|---|---|
| Arquivos de teste | 3 |
| Localização | `tests/unit/` |
| Integração | Não encontrada |

Cobertura estimada: **baixa** — apenas 3 arquivos de teste para 30+ módulos.

---

## Integrações Externas 🟢

| Serviço | Protocolo | Propósito |
|---|---|---|
| Kiro API (Amazon Q Developer) | HTTPS / AWS event stream | Backend principal de LLM |
| AWS SSO OIDC | HTTPS | Autenticação via kiro-cli |
| Kiro Desktop Auth | HTTPS | Autenticação via Kiro IDE |
| OpenAI API (Codex CLI) | HTTPS | Provider alternativo via OAuth |
| VPN/Proxy (opcional) | HTTP/SOCKS5 | Acesso em redes restritas |
