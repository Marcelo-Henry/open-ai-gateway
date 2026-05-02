# ADR-004: SQLite Read-Merge-Write para Persistência de Credenciais

**Status**: Aceito  
**Data**: 2025 (Issue #131)  
**Contexto**: kiro/auth.py:525

---

## Contexto

O kiro-cli armazena credenciais em um banco SQLite (`~/.local/share/kiro-cli/data.sqlite3`). Quando o gateway salva um novo access token, ele precisa atualizar o registro existente sem sobrescrever campos que podem ter sido atualizados pelo kiro-cli ou por outra instância do gateway concorrentemente.

A abordagem ingênua de "ler, modificar, escrever" tem uma race condition: se o kiro-cli atualizar o refresh token entre a leitura e a escrita do gateway, o gateway sobrescreve o novo refresh token com o valor antigo, invalidando a sessão.

## Decisão

Implementar a estratégia **Read-Merge-Write** em `_save_credentials_to_sqlite`:

1. **Read**: Lê o estado atual do registro no SQLite
2. **Merge**: Faz merge dos novos valores (apenas `accessToken` e `expiresAt`) sobre o estado lido, preservando todos os outros campos intactos
3. **Write**: Escreve o registro merged de volta

Adicionalmente, tenta múltiplas chaves alternativas se a chave primária falhar, para lidar com variações no schema do SQLite do kiro-cli.

```python
# Strategy: Read-Merge-Write (Issue #131 fix)
current = self._load_credentials_from_sqlite(db_path)  # Read
current.update({"accessToken": new_token, "expiresAt": new_expiry})  # Merge
self._write_to_sqlite(db_path, current)  # Write
```

## Consequências

**Positivas**:
- Elimina race condition de sobrescrita de refresh token
- Compatível com uso simultâneo de kiro-cli e gateway
- Preserva campos desconhecidos (forward compatibility)

**Negativas**:
- Três operações de I/O em vez de uma (read + merge + write)
- Não é atomicamente seguro contra múltiplas instâncias do gateway (sem lock de arquivo)

**Neutras**:
- Apenas afeta o modo SQLite (`KIRO_CLI_DB_FILE`)
- Modo arquivo JSON usa estratégia diferente (sobrescrita direta)
