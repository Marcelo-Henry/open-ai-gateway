# Open AI Gateway

Um proxy FastAPI que traduz requisições OpenAI, Anthropic e Gemini para o formato da API Kiro (Amazon Q Developer / AWS CodeWhisperer). Qualquer cliente de IA — Cursor, Claude Code, Cline, Continue — pode apontar para este gateway e usar uma assinatura Kiro.

## Por que usar?

Se você tem uma assinatura Kiro (Amazon Q Developer), este gateway permite usar modelos Claude de alta capacidade em qualquer ferramenta que aceite a API OpenAI ou Anthropic — sem pagar por tokens separadamente.

**Casos de uso principais:**

- **Claude Code**: use modelos Claude via sua assinatura Kiro, sem precisar de uma chave Anthropic
- **Cursor / Cline / Continue**: aponte o `baseURL` para o gateway e use qualquer modelo Kiro
- **Extended thinking**: o gateway injeta automaticamente `<thinking_mode>` e extrai os blocos de raciocínio como `thinking` content blocks nativos
- **Modelos Codex (OpenAI)**: roteamento transparente para `gpt-*` e `codex-*` via autenticação OAuth do Codex CLI
- **Multi-conta**: failover automático entre múltiplas contas Kiro com Circuit Breaker

---

## Setup rápido

### Pré-requisitos

- Python 3.10+
- Kiro IDE instalado **ou** kiro-cli com sessão ativa

### 1. Clone e instale dependências

```bash
git clone https://github.com/Marcelo-Henry/open-ai-gateway
cd open-ai-gateway
pip install -r requirements.txt
```

### 2. Configure

Execute o script de setup interativo:

```bash
bash setup.sh
```

O script vai pedir:
- Uma senha para proteger o gateway (`PROXY_API_KEY`)
- O host onde o servidor vai escutar (`127.0.0.1` para local, `0.0.0.0` para rede)
- O caminho do banco SQLite do kiro-cli

Ao final, oferece configurar o Claude Code automaticamente.

**Ou configure manualmente** criando um arquivo `.env`:

```env
PROXY_API_KEY="minha-senha-secreta"
SERVER_HOST="127.0.0.1"
KIRO_CLI_DB_FILE="~/.local/share/kiro-cli/data.sqlite3"
```

### 3. Inicie o gateway

```bash
python main.py
```

O servidor sobe em `http://localhost:8000` por padrão.

---

## Configurando o Claude Code

Após o gateway estar rodando, configure o Claude Code para usá-lo:

```bash
claude config set -g apiBaseUrl "http://localhost:8000"
claude config set -g apiKey "minha-senha-secreta"
```

Ou deixe o `setup.sh` fazer isso por você — ele pergunta ao final do setup.

A partir daí, o Claude Code usa sua assinatura Kiro em vez da API Anthropic diretamente.

---

## Métodos de autenticação

O gateway detecta automaticamente o tipo de credencial. Configure **um** dos métodos abaixo no `.env`:

| Método | Variável | Quando usar |
|--------|----------|-------------|
| SQLite do kiro-cli | `KIRO_CLI_DB_FILE` | Você usa o kiro-cli (recomendado) |
| JSON do Kiro IDE | `KIRO_CREDS_FILE` | Você tem o Kiro IDE instalado |
| Refresh token | `REFRESH_TOKEN` | Capturado do tráfego do Kiro IDE |
| Enterprise (SSO) | `KIRO_CREDS_FILE` com `clientId` | Conta corporativa AWS SSO |

**Onde fica o SQLite do kiro-cli?**

```bash
# Linux / macOS
find ~ -name data.sqlite3 -path "*kiro*" -o -name data.sqlite3 -path "*amazon-q*" 2>/dev/null
```

Caminhos comuns:
- `~/.local/share/kiro-cli/data.sqlite3`
- `~/.local/share/amazon-q/data.sqlite3`

---

## Docker

```bash
# Copie e edite o .env
cp .env.example .env

# Suba o container
docker compose up -d
```

Para montar o SQLite do kiro-cli, descomente a linha de volume no `docker-compose.yml`:

```yaml
volumes:
  - ~/.local/share/kiro-cli:/home/kiro/.local/share/kiro-cli:ro
```

---

## Variáveis de configuração

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `PROXY_API_KEY` | `my-super-secret-password-123` | Senha do gateway — **troque em produção** |
| `SERVER_HOST` | `0.0.0.0` | Host do servidor |
| `SERVER_PORT` | `8000` | Porta do servidor |
| `KIRO_REGION` | `us-east-1` | Região AWS |
| `FAKE_REASONING_ENABLED` | `true` | Injeta `<thinking_mode>` para extended thinking |
| `WEB_SEARCH_ENABLED` | `true` | Injeta ferramenta `web_search` automaticamente |
| `ACCOUNT_SYSTEM` | `false` | Habilita multi-conta com failover |
| `TRUNCATION_RECOVERY` | `true` | Recuperação automática de tool calls truncados |
| `AUTO_TRIM_PAYLOAD` | `false` | Trim automático quando payload > ~615KB |
| `FIRST_TOKEN_TIMEOUT` | `15s` | Timeout para primeiro token (retry automático) |
| `DEBUG_MODE` | `off` | `errors` ou `all` para salvar req/resp em `debug_logs/` |
| `VPN_PROXY_URL` | — | Proxy HTTP/HTTPS para redes restritas |

---

## Endpoints disponíveis

| Endpoint | Formato |
|----------|---------|
| `GET /v1/models` | OpenAI |
| `POST /v1/chat/completions` | OpenAI |
| `POST /v1/messages` | Anthropic |
| `POST /v1beta/models/{model}:generateContent` | Gemini |
| `GET /health` | Health check |
| `GET /docs` | Swagger UI |

---

## Multi-conta

Para usar múltiplas contas Kiro com failover automático, crie um `credentials.json` na raiz do projeto:

```json
[
  {
    "type": "sqlite",
    "path": "~/.local/share/kiro-cli/data.sqlite3"
  },
  {
    "type": "refresh_token",
    "refresh_token": "seu-refresh-token-da-segunda-conta"
  }
]
```

Ative no `.env`:

```env
ACCOUNT_SYSTEM=true
```

O Circuit Breaker gerencia falhas com backoff exponencial (`60s × 2^n`, máximo 1 dia) e 10% de chance de retry probabilístico durante cooldown.

---

## Modelos Codex (OpenAI)

Requisições para modelos `gpt-*` e `codex-*` são roteadas automaticamente para o endpoint privado do Codex CLI (`chatgpt.com/backend-api/codex/responses`), sem passar pela API Kiro.

**Modelos disponíveis:**

| Modelo | Nome |
|--------|------|
| `gpt-5.5` | GPT-5.5 (Codex) |
| `gpt-5.4` | GPT-5.4 (Codex) |
| `gpt-5.4-mini` | GPT-5.4 Mini (Codex) |
| `gpt-5.3-codex-spark` | GPT-5.3 Codex Spark (Codex) |

**Pré-requisito:** ter o Codex CLI instalado e autenticado. O gateway lê as credenciais de `~/.codex/auth.json` (criado automaticamente pelo `codex login`) e renova o token automaticamente antes do vencimento.

Ative no `.env`:

```env
CODEX_ENABLED=true
```

---

## Desenvolvimento e testes

```bash
# Rodar todos os testes
pytest

# Rodar um arquivo específico
pytest tests/unit/test_converters.py

# Verbose
pytest -v

# Teste de integração manual (requer gateway rodando)
python manual_api_test.py
```

Os testes unitários em `tests/unit/` são isolados de rede — nenhuma chamada real à API.

---

## Solução de problemas

**Gateway não inicia — "No Kiro credentials configured"**
Verifique se o caminho do SQLite está correto e o arquivo existe:
```bash
ls -la ~/.local/share/kiro-cli/data.sqlite3
```

**Erro 403 nas requisições**
O token expirou. O gateway tenta refresh automático. Se persistir, reinicie o kiro-cli para renovar a sessão.

**Payload muito grande / "Improperly formed request"**
Ative o trim automático no `.env`:
```env
AUTO_TRIM_PAYLOAD=true
```

**Debug de requisições**
```env
DEBUG_MODE=all
```
Os logs completos ficam em `debug_logs/`.

---

## Licença

Veja [LICENSE](LICENSE).
