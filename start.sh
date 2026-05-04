#!/bin/bash
cd "$(dirname "$0")"

# Colors
BOLD='\033[1m'
DIM='\033[2m'
CYAN='\033[36m'
GREEN='\033[32m'
YELLOW='\033[33m'
RESET='\033[0m'

# Load existing .env values (if file exists)
if [ -f .env ]; then
    source .env 2>/dev/null
fi

needs_setup=false

# Check which required vars are missing or empty
if [ -z "$PROXY_API_KEY" ] || [ "$PROXY_API_KEY" = "my-super-secret-password-123" ]; then
    needs_proxy_key=true
    needs_setup=true
else
    needs_proxy_key=false
fi

if [ -z "$SERVER_HOST" ]; then
    needs_host=true
    needs_setup=true
else
    needs_host=false
fi

if [ -z "$KIRO_CLI_DB_FILE" ]; then
    needs_sqlite=true
    needs_setup=true
else
    needs_sqlite=false
fi

# Interactive setup for missing values only
if [ "$needs_setup" = true ]; then
    echo ""
    echo -e "${BOLD}╔══════════════════════════════════════════╗${RESET}"
    echo -e "${BOLD}║     Open AI Gateway - Setup Inicial      ║${RESET}"
    echo -e "${BOLD}╚══════════════════════════════════════════╝${RESET}"
    echo ""

    if [ -f .env ]; then
        echo -e "${DIM}Arquivo .env encontrado, mas faltam algumas configurações.${RESET}"
        echo ""
    fi

    # 1. Proxy password
    if [ "$needs_proxy_key" = true ]; then
        echo -e "${CYAN}→${RESET} ${BOLD}Senha do proxy${RESET}"
        echo -e "${DIM}Essa senha protege seu gateway. Você vai usá-la como api_key nos clientes.${RESET}"
        echo -e "${DIM}Pode ser qualquer coisa que você inventar (ex: minha-senha-secreta-123)${RESET}"
        echo ""
        read -rp "   Senha: " PROXY_API_KEY
        echo ""

        if [ -z "$PROXY_API_KEY" ]; then
            echo "Erro: senha não pode ser vazia."
            exit 1
        fi
    fi

    # 2. Host
    if [ "$needs_host" = true ]; then
        echo -e "${CYAN}→${RESET} ${BOLD}Onde o proxy vai escutar?${RESET}"
        echo -e "${DIM}127.0.0.1 = só conexões locais (mais seguro)${RESET}"
        echo -e "${DIM}0.0.0.0   = aceita conexões de qualquer lugar (rede local, VPN, etc)${RESET}"
        echo ""
        read -rp "   Host [127.0.0.1]: " SERVER_HOST
        SERVER_HOST="${SERVER_HOST:-127.0.0.1}"
        echo ""
    fi

    # 3. SQLite path
    if [ "$needs_sqlite" = true ]; then
        echo -e "${CYAN}→${RESET} ${BOLD}Caminho do banco SQLite3 do kiro-cli${RESET}"
        echo -e "${DIM}Locais comuns:${RESET}"
        echo -e "${DIM}  Linux/macOS: ~/.local/share/kiro-cli/data.sqlite3${RESET}"
        echo -e "${DIM}  Alternativo: ~/.local/share/amazon-q/data.sqlite3${RESET}"
        echo ""
        echo -e "${YELLOW}Não sabe onde fica? Mande o seguinte prompt para uma IA:${RESET}"
        echo ""
        echo -e "  ${DIM}\"Preciso encontrar o arquivo data.sqlite3 do kiro-cli ou amazon-q"
        echo -e "  no meu sistema. Rode 'find ~ -name data.sqlite3 -path \"*kiro*\" -o"
        echo -e "  -name data.sqlite3 -path \"*amazon-q*\" 2>/dev/null' e me diga o caminho.\"${RESET}"
        echo ""
        read -rp "   Caminho do SQLite3: " KIRO_CLI_DB_FILE
        echo ""

        if [ -z "$KIRO_CLI_DB_FILE" ]; then
            echo "Erro: caminho do SQLite3 não pode ser vazio."
            exit 1
        fi

        # Expand ~ for validation
        expanded_path="${KIRO_CLI_DB_FILE/#\~/$HOME}"
        if [ ! -f "$expanded_path" ]; then
            echo -e "${YELLOW}Aviso: arquivo não encontrado em '$expanded_path'${RESET}"
            read -rp "   Continuar mesmo assim? [s/N]: " confirm
            if [[ ! "$confirm" =~ ^[sS]$ ]]; then
                exit 1
            fi
            echo ""
        fi
    fi

    # Write .env preserving any extra vars the user may have added manually
    if [ -f .env ]; then
        # Update existing .env: replace or append each var
        _update_env_var() {
            local key="$1" value="$2"
            if grep -q "^${key}=" .env 2>/dev/null; then
                sed -i "s|^${key}=.*|${key}=\"${value}\"|" .env
            elif grep -q "^# *${key}=" .env 2>/dev/null; then
                sed -i "s|^# *${key}=.*|${key}=\"${value}\"|" .env
            else
                echo "${key}=\"${value}\"" >> .env
            fi
        }

        [ "$needs_proxy_key" = true ] && _update_env_var "PROXY_API_KEY" "$PROXY_API_KEY"
        [ "$needs_host" = true ] && _update_env_var "SERVER_HOST" "$SERVER_HOST"
        [ "$needs_sqlite" = true ] && _update_env_var "KIRO_CLI_DB_FILE" "$KIRO_CLI_DB_FILE"
    else
        # Create fresh .env
        cat > .env << EOF
# Gerado por start.sh em $(date '+%Y-%m-%d %H:%M:%S')

PROXY_API_KEY="$PROXY_API_KEY"
SERVER_HOST="$SERVER_HOST"
KIRO_CLI_DB_FILE="$KIRO_CLI_DB_FILE"
EOF
    fi

    echo -e "${GREEN}✓ Configuração salva no .env!${RESET}"
    echo ""
fi

