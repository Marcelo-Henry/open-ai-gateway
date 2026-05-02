# ADR-006: Passthrough de Modelos Desconhecidos

**Status**: Aceito  
**Data**: 2025  
**Contexto**: kiro/model_resolver.py

---

## Contexto

O gateway precisa resolver nomes de modelos enviados pelos clientes para o formato aceito pela Kiro API. A questão é: o que fazer com modelos que não estão no cache dinâmico nem na lista de modelos ocultos?

Duas abordagens possíveis:
1. **Rejeitar**: Retornar 400 "Model not found" para modelos desconhecidos
2. **Passthrough**: Enviar o modelo diretamente à Kiro API e deixar ela decidir

## Decisão

Implementar **passthrough** como comportamento padrão: modelos desconhecidos são enviados à Kiro API sem modificação após normalização de nome.

> "We are a gateway, not a gatekeeper. Kiro API is the final arbiter."

O pipeline de resolução tem 4 camadas:
1. Normalizar nome (dash→dot, strip data, etc.)
2. Verificar cache dinâmico (modelos da API `/ListAvailableModels`)
3. Verificar modelos ocultos (`HIDDEN_MODELS` em config.py)
4. **Passthrough**: retornar o nome normalizado sem validação

## Consequências

**Positivas**:
- Suporte automático a novos modelos sem atualização do gateway
- Clientes podem usar modelos beta/preview que ainda não estão no cache
- Erros de modelo inválido vêm da Kiro API com mensagem original (mais informativa)

**Negativas**:
- O gateway não pode validar antecipadamente se um modelo existe
- Erros de typo em nomes de modelos chegam à Kiro API (latência extra antes do erro)

**Neutras**:
- Modelos em `HIDDEN_FROM_LIST` são excluídos de `/v1/models` mas ainda funcionam via passthrough
