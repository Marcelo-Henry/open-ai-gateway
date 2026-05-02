# Dependências — codex-gateway

> Gerado pelo Reversa Scout em 2026-05-01

---

## Gerenciador de Pacotes

**pip** (via `requirements.txt`)

---

## Dependências de Produção

| Pacote | Versão | Propósito |
|---|---|---|
| `fastapi` | latest | Framework web assíncrono — rotas, validação, middleware |
| `uvicorn[standard]` | latest | Servidor ASGI para FastAPI |
| `httpx` | latest | Cliente HTTP assíncrono — chamadas à Kiro API |
| `loguru` | latest | Logging estruturado e colorido |
| `python-dotenv` | latest | Carregamento de variáveis de ambiente do `.env` |
| `tiktoken` | latest | Contagem de tokens (tokenizador da OpenAI) |

> ⚠️ Nenhuma versão fixada em `requirements.txt` — risco de quebra por atualizações de dependências.

---

## Dependências de Desenvolvimento / Teste

| Pacote | Versão | Propósito |
|---|---|---|
| `pytest` | latest | Framework de testes |
| `pytest-asyncio` | latest | Suporte a testes assíncronos |
| `hypothesis` | latest | Property-based testing |

---

## Dependências da Biblioteca Padrão Python (principais)

| Módulo | Uso |
|---|---|
| `asyncio` | Concorrência assíncrona |
| `os`, `pathlib` | Manipulação de arquivos e variáveis de ambiente |
| `json` | Serialização/deserialização |
| `re` | Expressões regulares |
| `sqlite3` | Leitura do banco kiro-cli |
| `logging` | Interceptação de logs do uvicorn |
| `argparse` | Parsing de argumentos CLI |
| `contextlib` | Gerenciador de lifecycle (`asynccontextmanager`) |

---

## Notas

- Todas as dependências estão sem versão fixada (`requirements.txt` usa apenas nomes de pacotes).
- Para produção, recomenda-se fixar versões com `pip freeze > requirements.lock`.
- O `uvicorn[standard]` inclui extras como `websockets` e `httptools` para melhor performance.
