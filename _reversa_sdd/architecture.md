# Arquitetura — AI Gateway

> Escala de confiança: 🟢 CONFIRMADO | 🟡 INFERIDO | 🔴 LACUNA
> Versão: 2.4-dev.10 | Linguagem: Python 3.10+ | Framework: FastAPI

---

## Visão Geral

AI Gateway é um **proxy transparente** que expõe APIs compatíveis com OpenAI e Anthropic, traduzindo requisições para o formato nativo da Kiro API (Amazon Q Developer / AWS CodeWhisperer). O princípio central é intervenção mínima: o gateway corrige incompatibilidades de formato e adiciona funcionalidades opcionais, mas nunca altera a intenção do usuário.

---

## Princípios Arquiteturais

| Princípio | Descrição |
|-----------|-----------|
| 🟢 Transparência | Preserva intenção e estrutura original da requisição |
| 🟢 Intervenção Mínima | Modifica apenas o necessário para compatibilidade |
| 🟢 Controle do Usuário | Todas as funcionalidades opcionais são configuráveis |
| 🟢 Gateway, não Gatekeeper | Modelos desconhecidos são passados à Kiro API sem rejeição |
| 🟢 Sistemas sobre Patches | Soluções genéricas para classes de problemas, não fixes pontuais |
| 🟢 Async-first | Todo I/O é assíncrono (asyncio + httpx) |

---

## Camadas da Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│                    CAMADA DE ENTRADA                         │
│  routes_openai.py          routes_anthropic.py              │
│  GET /v1/models             POST /v1/messages               │
│  POST /v1/chat/completions  POST /v1/messages/count_tokens  │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                  CAMADA DE ORQUESTRAÇÃO                      │
│  account_manager.py — seleção de conta, Circuit Breaker     │
│  model_resolver.py  — normalização e resolução de modelos   │
│  auth.py            — ciclo de vida de tokens               │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                  CAMADA DE CONVERSÃO                         │
│  converters_core.py      — pipeline de 8 etapas             │
│  converters_openai.py    — adaptador OpenAI → Kiro          │
│  converters_anthropic.py — adaptador Anthropic → Kiro       │
│  truncation_recovery.py  — detecção de truncamento          │
│  mcp_tools.py            — web search MCP                   │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                  CAMADA DE TRANSPORTE                        │
│  http_client.py — retry exponencial, per-request streaming  │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                  CAMADA DE STREAMING                         │
│  parsers.py         — AWS Event Stream binário              │
│  thinking_parser.py — FSM extração de thinking blocks       │
│  streaming_core.py  — orquestração, first-token retry       │
│  streaming_openai.py    — formatação SSE OpenAI             │
│  streaming_anthropic.py — formatação SSE Anthropic          │
└─────────────────────────────────────────────────────────────┘
```

---

## Fluxo de Requisição (Resumo)

1. **Cliente** envia requisição OpenAI ou Anthropic com `PROXY_API_KEY`
2. **Route** autentica, detecta formato, aplica pré-processamentos (truncation recovery, web_search inject)
3. **AccountManager** seleciona a melhor account disponível (sticky + Circuit Breaker)
4. **Converter** traduz para KiroPayload (normalização de mensagens, tool processing, system prompt)
5. **HTTPClient** envia para `q.{region}.amazonaws.com/generateAssistantResponse` com access token
6. **StreamingEngine** parseia AWS Event Stream → extrai thinking blocks → formata SSE
7. **Cliente** recebe resposta no formato original solicitado

---

## Integrações Externas

| Sistema | Protocolo | Endpoint | Propósito |
|---------|-----------|----------|-----------|
| 🟢 Kiro API | HTTPS + AWS Event Stream | `q.{region}.amazonaws.com/generateAssistantResponse` | LLM principal |
| 🟢 Kiro API (modelos) | HTTPS/JSON | `q.{region}.amazonaws.com/ListAvailableModels` | Cache de modelos |
| 🟢 Kiro Desktop Auth | HTTPS/JSON | `prod.{region}.auth.desktop.kiro.dev/refreshToken` | Refresh token KIRO_DESKTOP |
| 🟢 AWS SSO OIDC | HTTPS/JSON | `oidc.{region}.amazonaws.com/token` | Refresh token AWS_SSO_OIDC |
| 🟢 Kiro MCP API | HTTPS/JSON | `q.{region}.amazonaws.com/mcp/...` | Web search nativo (Path A) |
| 🟢 ChatGPT Codex | HTTPS/JSON | `chatgpt.com/backend-api/codex/responses` | Modelos gpt-*/codex-* |
| 🟡 GitHub (raw) | HTTPS | `raw.githubusercontent.com/...` | System prompt do Codex Provider (startup) |

---

## Decisões Arquiteturais (ADRs)

| ADR | Decisão | Motivação |
|-----|---------|-----------|
| 🟢 ADR-001 | Per-request HTTP client para streaming | Evitar CLOSE_WAIT em desconexões VPN (Issues #38, #54) |
| 🟢 ADR-002 | Truncation Recovery | Notificar modelo sobre truncamento silencioso da Kiro API (Issue #56) |
| 🟢 ADR-003 | Normalização de roles de mensagem | Kiro API exige alternância estrita user/assistant (Issues #60, #64) |
| 🟢 ADR-004 | SQLite Read-Merge-Write | Evitar race condition com kiro-cli (Issue #131) |
| 🟢 ADR-005 | Detecção dinâmica de região | Endpoints de auth variam por região AWS (Issues #58, #132, #133) |
| 🟢 ADR-006 | Passthrough de modelos desconhecidos | Gateway não é gatekeeper — Kiro API é o árbitro final |
| 🟢 ADR-007 | Fake Reasoning via injeção de tags | Kiro API não suporta parâmetro `thinking` nativamente |

---

## Configuração e Deployment

- **Entry point**: `python main.py` ou `uvicorn main:app`
- **Porta padrão**: 8000 (configurável via `--port` ou `SERVER_PORT`)
- **Docker**: Dockerfile single-stage, usuário não-root (`kiro`), health check em `/health`
- **CI/CD**: GitHub Actions (`.github/workflows/docker.yml`) — testes + build + push para ghcr.io
- **Configuração**: `.env` file com variáveis de ambiente (ver `.env.example`)

---

## Artefatos de Documentação Gerados

| Artefato | Localização | Descrição |
|----------|-------------|-----------|
| Inventário | `_reversa_sdd/inventory.md` | Estrutura de arquivos, módulos, entry points |
| Dependências | `_reversa_sdd/dependencies.md` | Dependências pip e suas versões |
| Análise de Código | `_reversa_sdd/code-analysis.md` | Análise profunda de todos os 18 módulos |
| Dicionário de Dados | `_reversa_sdd/data-dictionary.md` | Todas as estruturas de dados e schemas |
| Flowchart Auth | `_reversa_sdd/flowcharts/auth.md` | Fluxo de autenticação e refresh de token |
| Flowchart Request | `_reversa_sdd/flowcharts/request-flow.md` | Fluxo completo de requisição |
| Flowchart Converters | `_reversa_sdd/flowcharts/converters.md` | Pipeline de conversão de payload |
| Glossário de Domínio | `_reversa_sdd/domain.md` | Entidades, termos e regras de negócio |
| Máquinas de Estado | `_reversa_sdd/state-machines.md` | FSMs de token, Circuit Breaker, ThinkingParser |
| Permissões | `_reversa_sdd/permissions.md` | Modelo de autenticação e autorização |
| ADRs | `_reversa_sdd/adrs/` | 7 decisões arquiteturais retroativas |
| C4 Contexto | `_reversa_sdd/c4-context.md` | Diagrama C4 Nível 1 |
| C4 Containers | `_reversa_sdd/c4-containers.md` | Diagrama C4 Nível 2 |
| C4 Componentes | `_reversa_sdd/c4-components.md` | Diagrama C4 Nível 3 |
| ERD Completo | `_reversa_sdd/erd-complete.md` | Entidades e relacionamentos |
| Spec Impact Matrix | `_reversa_sdd/traceability/spec-impact-matrix.md` | Matriz de impacto entre componentes |
