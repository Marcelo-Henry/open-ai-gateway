# Gaps — Lacunas Sem Resolução

> Gerado pelo Revisor em 2026-05-01
> Lacunas que permaneceram sem confirmação após revisão automática.

---

## Lacunas por Severidade

### Moderado

| # | Spec | Afirmação | Motivo |
|---|------|-----------|--------|
| G-01 | `sdd/mcp-codex.md` | Endpoint exato da Kiro MCP API para web search | Não encontrado no código analisado — requer validação |
| G-02 | `sdd/mcp-codex.md` | Formato exato da Responses API do ChatGPT Codex | Endpoint privado não documentado |
| G-03 | `sdd/auth.md` | Tokens nunca logados em nível INFO ou superior | Ausência de evidência não é confirmação — requer auditoria |

### Cosmético

| # | Spec | Afirmação | Motivo |
|---|------|-----------|--------|
| G-04 | `sdd/converters-core.md` | `KIRO_MAX_PAYLOAD_BYTES` default é ~615KB | Valor empírico inferido, não constante explícita no código |
| G-05 | `sdd/account-manager.md` | Conta sem modelo solicitado é pulada sem incrementar failures | Comportamento inferido da lógica de `continue` no loop |
| G-06 | `sdd/http-client.md` | User-Agent simula Kiro IDE com fingerprint | Propósito exato do fingerprint (autenticação vs. telemetria) não confirmado |
