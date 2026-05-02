# ERD Completo — Open AI Gateway

> Escala de confiança: 🟢 CONFIRMADO | 🟡 INFERIDO | 🔴 LACUNA

---

## Diagrama ERD

```mermaid
erDiagram
    ACCOUNT {
        string id PK "Caminho do arquivo de credenciais"
        int failures "Contador de falhas consecutivas (Circuit Breaker)"
        float last_failure_time "Timestamp da última falha"
        float models_cached_at "Timestamp do último cache de modelos"
        int total_requests "Total de requisições"
        int successful_requests "Requisições bem-sucedidas"
        int failed_requests "Requisições com falha"
    }

    CREDENTIALS_JSON {
        string accessToken PK "JWT de curta duração (~1h)"
        string refreshToken "Token de longa duração para renovação"
        string expiresAt "ISO 8601 timestamp de expiração"
        string region "Região AWS (ex: us-east-1)"
        string profileArn "ARN do perfil CodeWhisperer (opcional)"
        string clientId "Client ID para AWS SSO OIDC (opcional)"
        string clientSecret "Client Secret para AWS SSO OIDC (opcional)"
        string startUrl "URL de início SSO (opcional)"
    }

    SQLITE_DB {
        string key PK "Chave do registro (ex: kiro-auth-token)"
        string value "JSON serializado das credenciais"
    }

    STATE_JSON {
        int current_account_index "Índice global sticky da account atual"
        map model_to_accounts "Mapeamento modelo → lista de account IDs"
        map accounts "Estado runtime por account ID"
    }

    KIRO_PAYLOAD {
        string modelId "Nome do modelo normalizado"
        string origin "Origem da requisição (INLINE_CHAT)"
        object userInputMessage "Mensagem atual do usuário"
        array conversationHistory "Histórico de mensagens"
        string profileArn "ARN do perfil (se configurado)"
    }

    UNIFIED_MESSAGE {
        string role "user ou assistant"
        array content "Lista de content blocks"
        string id "ID da mensagem (opcional)"
    }

    CONTENT_BLOCK {
        string type "text, tool_use, tool_result, thinking, image"
        string text "Conteúdo textual (type=text)"
        string id "ID do tool call (type=tool_use)"
        string name "Nome da tool (type=tool_use)"
        object input "Argumentos da tool (type=tool_use)"
        string tool_use_id "Referência ao tool call (type=tool_result)"
        string thinking "Conteúdo do bloco de raciocínio (type=thinking)"
    }

    TOOL_DEFINITION {
        string name "Nome da tool (max 64 chars)"
        string description "Descrição (movida ao system prompt se muito longa)"
        object input_schema "JSON Schema dos parâmetros"
    }

    KIRO_EVENT {
        string type "content, tool_start, tool_input, tool_stop, usage, stop"
        string content "Texto do evento (type=content)"
        string tool_id "ID do tool call (type=tool_*)"
        string tool_name "Nome da tool (type=tool_start)"
        string tool_args "Argumentos JSON (type=tool_input)"
        int input_tokens "Tokens de entrada (type=usage)"
        int output_tokens "Tokens de saída (type=usage)"
        string stop_reason "Motivo de parada (type=stop)"
    }

    MODEL_INFO {
        string modelId PK "ID do modelo na Kiro API"
        string modelName "Nome display do modelo"
        bool streaming "Suporta streaming"
        string status "Status do modelo (ACTIVE, etc)"
    }

    DEBUG_LOG {
        string request_id PK "UUID da requisição"
        string timestamp "ISO 8601"
        string method "HTTP method"
        string path "Endpoint chamado"
        int status_code "Código de resposta HTTP"
        object request_headers "Headers da requisição"
        object request_body "Body da requisição"
        object response_body "Body da resposta"
        float duration_ms "Duração em milissegundos"
    }

    ACCOUNT ||--o{ CREDENTIALS_JSON : "lê/atualiza (modo arquivo)"
    ACCOUNT ||--o{ SQLITE_DB : "lê/atualiza (modo SQLite)"
    STATE_JSON ||--o{ ACCOUNT : "persiste estado de"
    KIRO_PAYLOAD ||--o{ UNIFIED_MESSAGE : "construído a partir de"
    UNIFIED_MESSAGE ||--o{ CONTENT_BLOCK : "contém"
    KIRO_PAYLOAD ||--o{ TOOL_DEFINITION : "inclui definições de"
    KIRO_EVENT }o--|| KIRO_PAYLOAD : "gerado em resposta a"
    ACCOUNT ||--o{ MODEL_INFO : "tem cache de"
    DEBUG_LOG }o--|| KIRO_PAYLOAD : "registra"
```

---

## Descrição das Entidades

### ACCOUNT
🟢 Entidade runtime gerenciada pelo `AccountManager`. Não persiste em banco — estado salvo em `state.json`. Cada account corresponde a um arquivo de credenciais Kiro.

### CREDENTIALS_JSON
🟢 Arquivo JSON em disco com credenciais Kiro. Lido pelo `KiroAuthManager`. Atualizado após cada refresh de token. Localização configurável via `KIRO_CREDS_FILE`.

### SQLITE_DB
🟢 Banco SQLite do kiro-cli (`~/.local/share/kiro-cli/data.sqlite3`). Tabela com pares chave-valor onde o valor é JSON serializado das credenciais. Estratégia Read-Merge-Write para evitar race conditions.

### STATE_JSON
🟢 Arquivo `state.json` persistido pelo `AccountManager`. Contém índice global sticky, mapeamento modelo→accounts e estado de Circuit Breaker por account. Salvo atomicamente via arquivo temporário + rename.

### KIRO_PAYLOAD
🟢 Estrutura enviada para `generateAssistantResponse`. Formato proprietário da Kiro API. Construído pelos converters a partir de UnifiedMessages.

### UNIFIED_MESSAGE
🟢 Formato interno intermediário. Normaliza diferenças entre OpenAI e Anthropic antes de construir o KiroPayload.

### CONTENT_BLOCK
🟢 Unidade atômica de conteúdo dentro de uma mensagem. Tipos suportados: `text`, `tool_use`, `tool_result`, `thinking`, `image`.

### TOOL_DEFINITION
🟢 Definição de uma ferramenta disponível para o modelo. Nomes limitados a 64 chars. Descrições longas movidas ao system prompt.

### KIRO_EVENT
🟢 Evento emitido pelo `AwsEventStreamParser` ao processar o stream binário da Kiro API. Tipos: `content`, `tool_start`, `tool_input`, `tool_stop`, `usage`, `stop`.

### MODEL_INFO
🟢 Metadados de modelo obtidos via `/ListAvailableModels`. Cacheados por account com TTL de 12h.

### DEBUG_LOG
🟢 Registro de requisição/resposta salvo em `debug_logs/` quando `DEBUG_MODE != off`. Um arquivo JSON por requisição.
