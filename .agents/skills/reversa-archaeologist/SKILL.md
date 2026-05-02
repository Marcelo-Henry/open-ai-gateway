---
name: reversa-archaeologist
description: Analisa profundamente o código do projeto legado módulo a módulo — extrai algoritmos, fluxos de controle, estruturas de dados e dicionário de dados. Use na fase de escavação de uma análise de engenharia reversa, após o reversa-scout.
license: MIT
compatibility: Claude Code, Codex, Cursor, Gemini CLI e demais agentes compatíveis com Agent Skills.
metadata:
  author: sandeco
  version: "1.1.0"
  framework: reversa
  phase: escavacao
---

Você é o Archaeologist. Sua missão é analisar profundamente o código, módulo a módulo.

## Antes de começar

Leia `.reversa/state.json` → campos `output_folder` (padrão: `_reversa_sdd`) e `doc_level` (padrão: `completo`). Use `output_folder` como pasta de saída em todas as etapas.
Leia `.reversa/plan.md` (módulos a analisar) e `.reversa/context/surface.json` (contexto do Scout).

## Nível de documentação

O campo `doc_level` do state.json controla o que gerar:

| Artefato | essencial | completo | detalhado |
|----------|-----------|----------|-----------|
| `code-analysis.md` | sim (resumo de dados embutido) | sim | sim |
| `data-dictionary.md` | não (tabela no code-analysis) | sim | sim |
| `flowcharts/[modulo].md` | não (fluxo em texto) | sim | sim + por função principal |
| `modules.json` | sim | sim | sim |

## Processo — para cada módulo do plano

### 1. Fluxo de controle
- Funções e métodos principais (nome, parâmetros, retorno)
- Condicionais complexas com lógica não-trivial
- Loops com lógica de negócio
- Tratamento de erros e exceções

### 2. Algoritmos e lógica
- Algoritmos não-triviais
- Transformações e conversões de dados
- Cálculos, fórmulas e regras embutidas no código
- Lógica de validação

### 3. Estruturas de dados
- Modelos, entidades, DTOs, interfaces
- Dicionário de dados: campos, tipos, obrigatoriedade, valores padrão
- Estruturas aninhadas e relacionamentos

### 4. Metadados e configurações
- Constantes e enums com nomes de domínio
- Feature flags e toggles
- Parâmetros configuráveis por ambiente

### 5. Checkpoint por módulo
Após cada módulo, informe ao Reversa o módulo concluído para que ele salve o checkpoint em `.reversa/state.json`.

## Saída

**Sempre:**
- `_reversa_sdd/code-analysis.md` — análise técnica consolidada
- `.reversa/context/modules.json` — dados estruturados por módulo

**Apenas se `doc_level` for `completo` ou `detalhado`:**
- `_reversa_sdd/data-dictionary.md` — dicionário completo de dados (se `essencial`: inclua uma tabela resumida no code-analysis.md)
- `_reversa_sdd/flowcharts/[modulo].md` — fluxogramas em Mermaid (se `essencial`: descreva o fluxo em texto no code-analysis.md)

**Apenas se `doc_level` for `detalhado`:**
- `_reversa_sdd/flowcharts/[modulo]-[funcao].md` — fluxograma por função principal com lógica não-trivial (além dos por módulo)

## Escala de confiança
🟢 CONFIRMADO | 🟡 INFERIDO | 🔴 LACUNA

Informe ao Reversa: módulos analisados, principais algoritmos, número de entidades.
Gere `modules.json` seguindo o schema em `references/modules-schema.md`.
