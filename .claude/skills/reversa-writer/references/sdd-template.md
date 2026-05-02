# [Nome do Componente]

## Visão Geral
[O que é, qual problema resolve — 2 a 3 linhas]

## Responsabilidades
- [Responsabilidade 1]
- [Responsabilidade 2]

## Interface
[Entradas, saídas, parâmetros, tipos de dados]

## Regras de Negócio
- [Regra 1] 🟢
- [Regra 2] 🟡
- [Comportamento desconhecido] 🔴

## Fluxo Principal
1. [Passo 1]
2. [Passo 2]
3. [Passo N]

## Fluxos Alternativos
- **[Condição especial]:** [comportamento]
- **[Caso de erro]:** [comportamento]

## Dependências
- [Componente X] — [motivo]
- [Serviço Y] — [como usa]

## Requisitos Não Funcionais

| Tipo | Requisito inferido | Evidência no código | Confiança |
|------|--------------------|---------------------|-----------|
| Performance | [ex: timeout de 30s em chamadas externas] | `caminho/arquivo.ext:linha` | 🟢 |
| Segurança | [ex: autenticação obrigatória na rota] | `caminho/arquivo.ext:linha` | 🟡 |
| Escalabilidade | [ex: uso de cache Redis] | `caminho/arquivo.ext:linha` | 🟢 |
| Disponibilidade | [ex: retry automático em falha] | `caminho/arquivo.ext:linha` | 🟡 |

> Inferido a partir do código. Validar com equipe de operações.

## Critérios de Aceitação

```gherkin
Dado [pré-condição]
Quando [ação]
Então [resultado esperado]

Dado [condição de erro]
Quando [ação inválida]
Então [comportamento de falha esperado]
```

## Prioridade

| Requisito | MoSCoW | Justificativa |
|-----------|--------|---------------|
| [Responsabilidade principal] | Must | Caminho crítico — chamado em todo fluxo |
| [Regra de negócio central] | Must | Regra de negócio sem fallback |
| [Funcionalidade secundária] | Should | Importante mas com alternativa |
| [Caso de borda] | Could | Raramente acionado |

> Prioridade inferida por frequência de chamada e posição na cadeia de dependências.

## Rastreabilidade de Código

| Arquivo | Função / Classe | Cobertura |
|---------|-----------------|-----------|
| `caminho/arquivo.ext` | `NomeDaClasse` | 🟢 |
