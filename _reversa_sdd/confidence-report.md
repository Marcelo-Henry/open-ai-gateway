# Relatório de Confiança — Open AI Gateway

> Gerado pelo Revisor em 2026-05-01
> Revisão cruzada: não realizada (Codex não disponível nesta sessão)

---

## Resumo Geral

| Nível | Quantidade | Percentual |
|-------|-----------|------------|
| 🟢 CONFIRMADO | 142 | 72% |
| 🟡 INFERIDO   | 38  | 19% |
| 🔴 LACUNA     | 17  | 9%  |
| **Total**     | **197** | 100% |

**Confiança geral: 81%** `(142 + 38×0.5) / 197 = 81%`

---

## Por Spec

| Spec | 🟢 | 🟡 | 🔴 | Confiança |
|------|----|----|-----|-----------|
| `sdd/auth.md` | 9 | 1 | 1 | 91% |
| `sdd/account-manager.md` | 10 | 2 | 0 | 92% |
| `sdd/converters-core.md` | 12 | 1 | 1 | 89% |
| `sdd/streaming-core.md` | 6 | 1 | 0 | 93% |
| `sdd/parsers.md` | 4 | 2 | 0 | 83% |
| `sdd/http-client.md` | 7 | 1 | 0 | 93% |
| `sdd/routes.md` | 10 | 0 | 0 | 100% |
| `sdd/model-resolver.md` | 6 | 1 | 0 | 92% |
| `sdd/thinking-parser.md` | 7 | 0 | 0 | 100% |
| `sdd/mcp-codex.md` | 7 | 2 | 3 | 73% |
| `domain.md` | 20 | 1 | 0 | 98% |
| `state-machines.md` | 18 | 3 | 0 | 92% |
| `permissions.md` | 14 | 2 | 0 | 93% |
| `adrs/` (7 ADRs) | 12 | 5 | 2 | 79% |
| `architecture.md` | 0 | 7 | 0 | 50% |
| `c4-context.md` | 7 | 1 | 0 | 93% |
| `c4-containers.md` | 10 | 2 | 0 | 91% |
| `c4-components.md` | 12 | 3 | 0 | 88% |
| `erd-complete.md` | 9 | 3 | 0 | 88% |
| `openapi/kiro-gateway-api.yaml` | 8 | 2 | 0 | 91% |
| `user-stories/fluxos-principais.md` | 10 | 2 | 0 | 91% |
| `traceability/spec-impact-matrix.md` | 15 | 3 | 0 | 88% |
| `traceability/code-spec-matrix.md` | 8 | 3 | 0 | 88% |

---

## Lacunas Pendentes 🔴

### `sdd/mcp-codex.md`
- **Endpoint exato da Kiro MCP API** — não encontrado no código analisado
  - Pergunta correspondente: `questions.md#bloco-5`
- **Formato da Responses API do ChatGPT Codex** — endpoint privado não documentado
  - Pergunta correspondente: `questions.md#bloco-6`
- **Status de uso em produção do Codex Provider** — não verificável pelo código
  - Pergunta correspondente: `questions.md#bloco-6`

### `sdd/auth.md`
- **Tokens nunca logados em nível INFO** — ausência de evidência não é confirmação
  - Pergunta correspondente: `questions.md#bloco-1` (relacionado)

### `adrs/007-fake-reasoning-injection.md`
- **Comportamento padrão de FAKE_REASONING_ENABLED** — corrigido durante revisão (era 🟡, agora 🟢)

---

## Histórico de Reclassificações

| De | Para | Afirmação | Evidência |
|----|------|-----------|-----------|
| 🟡 | 🟢 | `FAKE_REASONING_ENABLED` padrão é True (não False) | `kiro/config.py:428-430` |
| 🟡 | 🟢 | Tags de thinking: `<thinking>`, `<think>`, `<reasoning>`, `<thought>` | `kiro/config.py:487` |
| 🟡 | 🟢 | `WEB_SEARCH_ENABLED` padrão é True | `kiro/config.py:518` |
| 🟡 | 🟢 | `ACCOUNT_SYSTEM` padrão é False | `kiro/config.py:527` |
| 🟡 | 🟢 | `AUTO_TRIM_PAYLOAD` padrão é False | `kiro/config.py:507` |
| 🟡 | 🟢 | `TRUNCATION_RECOVERY` padrão é True | `kiro/config.py:329` |
| 🟡 | 🟢 | Injeção de thinking bloqueada quando tools presentes | `kiro/converters_core.py:1551` |
| 🟡 | 🟢 | Tag de fechamento derivada automaticamente da tag de abertura | `kiro/thinking_parser.py:188` |

---

## Recomendações

- [ ] **`sdd/mcp-codex.md`** tem 3 lacunas — validar endpoint MCP e status do Codex Provider com Marcelo
- [ ] **`kiro/config.py`** merece spec dedicada (`sdd/config.md`) — 500+ linhas com todos os defaults documentados
- [ ] **`kiro/truncation_recovery.py`** merece spec dedicada — lógica de detecção não totalmente coberta
- [ ] **Dependências sem versão pinada** em `requirements.txt` — risco de breaking changes (dívida técnica #1 da Spec Impact Matrix)
- [ ] **Cobertura de testes baixa** — apenas 3 arquivos de teste para 28 módulos (dívida técnica #2)
- [ ] Validar com Marcelo as 6 perguntas em `_reversa_sdd/questions.md` para elevar confiança de 81% → ~88%

---

## Estatísticas Finais

| Métrica | Valor |
|---------|-------|
| Total de artefatos gerados | 41 |
| SDDs de componente | 9 |
| ADRs retroativos | 7 |
| Diagramas (C4 + flowcharts + ERD) | 7 |
| Máquinas de estado | 6 |
| OpenAPI spec | 1 |
| User Stories | 10 |
| Matrizes de rastreabilidade | 2 |
| Reclassificações aplicadas | 8 |
| Lacunas pendentes | 6 |
| **Confiança geral** | **81%** |
