# ADR-005: Detecção Dinâmica de Região para Endpoints de Auth

**Status**: Aceito  
**Data**: 2025 (Issues #58, #132, #133)  
**Contexto**: kiro/config.py:146, 181, kiro/auth.py:225, 346

---

## Contexto

A Kiro API e seus endpoints de autenticação variam por região AWS. O problema original (Issue #58) era que o endpoint `codewhisperer.{region}.amazonaws.com` não existe para regiões fora de `us-east-1` — apenas `q.{region}.amazonaws.com` é válido universalmente.

Issues subsequentes (#132, #133) revelaram que os endpoints de autenticação OIDC também variam: algumas regiões usam endpoints específicos que só existem naquela região, e tentar usar o endpoint de `us-east-1` para autenticar em outra região falha silenciosamente ou retorna erros confusos.

## Decisão

1. **Endpoint da API**: Usar sempre `q.{region}.amazonaws.com/generateAssistantResponse` (nunca `codewhisperer.*`)

2. **Detecção de região**: Extrair a região das credenciais em ordem de prioridade:
   - Campo `region` explícito nas credenciais
   - Extraído do `startUrl` (ex: `https://d-xxx.awsapps.com/start` → `us-east-1`)
   - Variável de ambiente `KIRO_REGION`
   - Fallback: `us-east-1`

3. **Endpoints de auth por região**: Construir URLs dinamicamente com a região detectada:
   - KIRO_DESKTOP: `prod.{region}.auth.desktop.kiro.dev/refreshToken`
   - AWS_SSO_OIDC: `oidc.{region}.amazonaws.com/token`

4. **Logging de diagnóstico**: Logar os endpoints inicializados para facilitar debugging de problemas de DNS/região (Issue #58).

## Consequências

**Positivas**:
- Suporte correto a múltiplas regiões AWS
- Elimina erros de DNS para regiões não-us-east-1
- Diagnóstico facilitado via logging de endpoints

**Negativas**:
- Lógica de detecção de região é heurística (pode falhar com formatos de credenciais não antecipados)
- Fallback para `us-east-1` pode mascarar problemas de configuração

**Neutras**:
- Configuração explícita via `KIRO_REGION` sempre tem precedência sobre detecção automática
