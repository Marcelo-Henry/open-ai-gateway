# C4 — Nível 1: Contexto do Sistema

> Escala de confiança: 🟢 CONFIRMADO | 🟡 INFERIDO | 🔴 LACUNA

```mermaid
C4Context
    title AI Gateway — Diagrama de Contexto

    Person(dev, "Desenvolvedor / Agente AI", "Usa Claude Code, Cursor, ou outro cliente compatível com OpenAI/Anthropic API")

    System(gateway, "AI Gateway", "Proxy FastAPI que traduz requisições OpenAI/Anthropic para o formato nativo da Kiro API. Gerencia autenticação, streaming, failover multi-account e enriquecimentos opcionais.")

    System_Ext(kiro_api, "Kiro API (Amazon Q Developer)", "API da Amazon Q Developer / AWS CodeWhisperer. Processa requisições LLM via AWS Event Stream. Endpoint: q.{region}.amazonaws.com")

    System_Ext(kiro_auth_desktop, "Kiro Desktop Auth", "Serviço de autenticação para usuários Kiro IDE. Endpoint: prod.{region}.auth.desktop.kiro.dev/refreshToken")

    System_Ext(aws_sso_oidc, "AWS SSO OIDC", "Serviço de autenticação AWS para Builder ID e Enterprise. Endpoint: oidc.{region}.amazonaws.com/token")

    System_Ext(kiro_mcp, "Kiro MCP API", "API de ferramentas MCP da Kiro para web search nativo. Endpoint: q.{region}.amazonaws.com/mcp/...")

    System_Ext(chatgpt_codex, "ChatGPT Codex API", "Endpoint privado do ChatGPT para modelos gpt-*/codex-*. Endpoint: chatgpt.com/backend-api/codex/responses")

    System_Ext(kiro_ide, "Kiro IDE / kiro-cli", "IDE da Amazon que gera e persiste credenciais em arquivo JSON ou SQLite. Fonte de refresh tokens.")

    Rel(dev, gateway, "Envia requisições", "HTTPS / OpenAI API ou Anthropic API")
    Rel(gateway, kiro_api, "Encaminha requisições LLM", "HTTPS / AWS Event Stream")
    Rel(gateway, kiro_auth_desktop, "Renova access token (KIRO_DESKTOP)", "HTTPS / JSON")
    Rel(gateway, aws_sso_oidc, "Renova access token (AWS_SSO_OIDC)", "HTTPS / JSON")
    Rel(gateway, kiro_mcp, "Web search nativo (Path A)", "HTTPS / JSON")
    Rel(gateway, chatgpt_codex, "Requisições gpt-*/codex-* (Codex Provider)", "HTTPS / JSON")
    Rel(kiro_ide, gateway, "Fornece credenciais", "Arquivo JSON ou SQLite em disco")
```

---

## Atores e Sistemas Externos

### Usuários (Personas)

| Persona | Descrição | Interface |
|---------|-----------|-----------|
| 🟢 Desenvolvedor com Claude Code | Usa Claude Code CLI apontado para o gateway | OpenAI API (`/v1/chat/completions`) |
| 🟢 Desenvolvedor com cliente Anthropic | Usa SDK Anthropic ou Cursor apontado para o gateway | Anthropic API (`/v1/messages`) |
| 🟡 Operador do Gateway | Configura e mantém o gateway em produção | `.env`, Docker, CLI |

### Sistemas Externos

| Sistema | Protocolo | Direção | Propósito |
|---------|-----------|---------|-----------|
| 🟢 Kiro API (Amazon Q) | HTTPS + AWS Event Stream | Gateway → Kiro | Processamento LLM |
| 🟢 Kiro Desktop Auth | HTTPS/JSON | Gateway → Auth | Refresh de token (KIRO_DESKTOP) |
| 🟢 AWS SSO OIDC | HTTPS/JSON | Gateway → AWS | Refresh de token (Builder ID / Enterprise) |
| 🟢 Kiro MCP API | HTTPS/JSON | Gateway → MCP | Web search nativo (Path A) |
| 🟢 ChatGPT Codex API | HTTPS/JSON | Gateway → ChatGPT | Modelos gpt-*/codex-* |
| 🟢 Kiro IDE / kiro-cli | Arquivo em disco | IDE → Gateway | Fonte de credenciais (JSON ou SQLite) |
