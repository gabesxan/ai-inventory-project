# Especificação Funcional, Arquitetura e Premissas do Sistema

## 1. Visão Geral e Escopo

Este projeto implementa um sistema completo de gestão de estoque para uma pequena empresa operando em um **único depósito**, com interface inteiramente em **português do Brasil (pt-BR)**, valores monetários em **Reais (BRL)** e datas no padrão brasileiro (`dd/MM/aaaa` e `dd/MM/aaaa HH:mm`).

Esta primeira versão contempla:

- Autenticação com perfis **Administrador** e **Operador** (controle de acesso validado no backend).
- Cadastros de **Categorias**, **Fornecedores** e **Produtos** (com SKU único, código de barras opcional e único, estoque mínimo, estoque de segurança, localização física, fornecedor preferencial e prazo de reposição).
- Controle transacional de **Movimentações de Estoque** (`ENTRADA`, `SAIDA`, `AJUSTE`, `ESTORNO`), impedindo saldo negativo e tratando concorrência com bloqueio de linha no PostgreSQL (`SELECT ... FOR UPDATE`).
- **Painel (Dashboard)** com indicadores reais, lista de reposição e gráfico por período sem somar unidades incompatíveis.
- **Relatórios** filtráveis com exportação em **CSV** (UTF-8 com BOM).
- **Preparação para Projeto Final de IA**: histórico padronizado de demanda (`VENDA`/`CONSUMO`) separado de perdas/avarias/ajustes/estornos, custo unitário nas entradas, rastreamento de períodos de ruptura (`stockout_periods`), importação de histórico por CSV para estudo (sem alterar o saldo atual), exportação analítica para Python (`pandas`), contrato de integração de previsão e tela de **Sugestões de Compra**.

Fora do escopo desta v1 (por definição): vendas/PDV, emissão fiscal (NF-e/NFC-e), pagamentos, múltiplos depósitos, recuperação de senha por e-mail e treinamento de modelos de ML.

---

## 2. Arquitetura e Separação de Responsabilidades

```text
frontend/ (React + TypeScript + CSS responsivo)
   └── Camada de apresentação, validação de formulário, estado de sessão e chamadas HTTP (/api)

backend/app/
   ├── api/          -> Camada HTTP (FastAPI routers, schemas Pydantic, RBAC)
   ├── services/     -> Regras de negócio (catálogo, unidades/arredondamento, transações de estoque, relatórios)
   ├── models/       -> Camada de acesso ao banco (SQLAlchemy 2.0 + PostgreSQL)
   └── ai/           -> Módulo isolado de preparação de dados e contrato de previsão/reposição
```

A separação garante que o módulo `backend/app/ai/` consuma os dados históricos por interfaces limpas sem acoplar modelos estatísticos/ML às regras transacionais de saldo.

---

## 3. Premissas Adotadas e Políticas Numéricas

1. **Saldo inicial**: Todo produto é cadastrado com `current_stock = 0`. Um saldo inicial existente na empresa deve ser lançado como uma movimentação explícita de `ENTRADA` com motivo `SALDO_INICIAL`.
2. **Unidades de medida e precisão**:
   - **Unidades discretas** (`UN`, `CX`, `PCT`, `PAR`, `FD`, `RL`): exigem quantidades inteiras (`quantidade % 1 == 0`). Frações retornam erro HTTP `422`.
   - **Unidades contínuas/fracionáveis** (`KG`, `G`, `L`, `ML`, `M`, `M2`): aceitam até **3 casas decimais** (`NUMERIC(14, 3)`).
   - **Política de arredondamento**:
     - Valores monetários (`unit_cost`, totais estimados) usam `NUMERIC(14, 2)` com arredondamento padrão `ROUND_HALF_UP` para `0.01`.
     - Quantidades fracionárias usam `NUMERIC(14, 3)` com `ROUND_HALF_UP` para `0.001`.
     - Recomendações futuras de compra arredondam para cima no inteiro mais próximo em unidades discretas (`ceil`) ou para `0.001` em unidades contínuas.
3. **Agregação de indicadores**: O sistema **nunca soma quantidades de unidades incompatíveis** (ex.: `UN + KG`) em um único número. Indicadores agregados exibem contagem de movimentações ou detalhamento separado por unidade.
4. **Avaliação de valor do estoque**: O indicador _"Valor Estimado do Estoque"_ é calculado como $\sum (\text{saldo atual} \times \text{custo unitário de referência})$ apenas como referência gerencial, sem caráter contábil/fiscal (FIFO/PEPS ou custo médio ponderado contábil).
5. **Produto abaixo do mínimo**: Definido como `is_active = true` e `current_stock < min_stock`. Produtos com `current_stock == 0` também são sinalizados como "Sem estoque" / "Crítico".
6. **Classificação de demanda para IA**:
   - Saídas com motivo `VENDA` ou `CONSUMO` marcam `is_demand = true`.
   - Saídas com motivo `PERDA`, `AVARIA` ou `OUTRO`, além de `AJUSTE` e `ESTORNO`, marcam `is_demand = false` (exceto estornos vinculados a uma movimentação que era demanda, que abatem a demanda líquida na série analítica).
7. **Estornos**:
   - Permitidos apenas a Administradores com justificativa obrigatória.
   - Não é permitido estornar um estorno, nem estornar a mesma movimentação duas vezes (garantido por índice único parcial no banco).
   - Estorno que resulte em saldo negativo é bloqueado.
8. **Preservação de histórico**: Produtos nunca são excluídos; apenas inativados (`is_active = false`). Não é permitido alterar a unidade de medida de um produto que já possua movimentações registradas.
9. **Importação histórica para estudo**: Arquivos CSV importados no módulo de IA alimentam exclusivamente a tabela `historical_movements` e **nunca alteram** `products.current_stock`.

---

## 4. Lista Ordenada de Tarefas (Etapas de Execução)

1. **Etapa 0 — Infraestrutura e Configuração**: Especificação, `.env.example`, `docker-compose.yml`, inicialização do PostgreSQL 16, criação dos bancos `ai_inventory` e `ai_inventory_test`, ambiente virtual Python 3.14.
2. **Etapa 1 — Estrutura, Banco, Migrações e Autenticação**: Modelos SQLAlchemy, Alembic (`0001_initial_schema`), autenticação JWT com revogação real no logout (`revoked_tokens`), RBAC (`ADMIN` / `OPERATOR`), CRUD de usuários e CLI (`create-admin`, `seed-demo`).
3. **Etapa 2 — Cadastros**: Validador de unidades/arredondamento, serviços e rotas de Categorias, Fornecedores e Produtos.
4. **Etapa 3 — Movimentações e Regras de Saldo**: Motor transacional com `SELECT FOR UPDATE`, entradas (com custo histórico e datas de pedido/recebimento), saídas padronizadas, ajustes, estornos vinculados e registro automático de períodos de ruptura (`stockout_periods`).
5. **Etapa 4 — Dashboard, Relatórios e Preparação para IA**: Indicadores e série diária do painel, relatórios com exportação CSV filtrada, importação histórica CSV (modelo, prévia, erros por linha, deduplicação), exportação analítica Python (`pandas`), contrato de previsão e lógica de recomendação sem dupla contagem.
6. **Etapa 5 — Interface Frontend (React + TypeScript + CSS)**: Layout responsivo (menu lateral no desktop e gaveta no mobile), fluxos de login, painel, produtos, movimentações, categorias/fornecedores, relatórios, sugestões de compra, dados para IA e usuários.
7. **Etapa 6 — Verificação e Entrega**: Testes automatizados `pytest` (incluindo concorrência real com threads/PostgreSQL), build de produção do frontend, validação ponta a ponta em navegador real (desktop e mobile) e documentação final (`README.md` e `docs/AI_INTEGRATION_AND_EVALUATION.md`).
