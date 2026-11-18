# Preparação para o Projeto Final de IA: Dados, Contrato e Avaliação Acadêmica

Este documento detalha como os dados operacionais e históricos do sistema são estruturados, exportados e preparados para o módulo futuro de **previsão de demanda e recomendação de compras** em Python (`pandas` e `scikit-learn`), mantendo separação estrita das regras transacionais de estoque.

---

## 1. Dicionário de Dados das Exportações Analíticas

Todos os arquivos exportados pela tela **Dados para IA** (`/api/ai/exports/...`) usam codificação `UTF-8 com BOM`, delimitador vírgula (`,`) e identificadores estáveis (`product_id` e `sku`) para leitura direta via `pandas.read_csv()`.

### 1.1. Visão Diária por Produto (`serie_diaria_ia_produtos.csv`)

Cada linha representa o par `(date, product_id)` em horário comercial brasileiro (`America/Sao_Paulo`):

| Campo                       | Tipo / Unidade                 | Descrição e Regras                                                                                                       |
| :-------------------------- | :----------------------------- | :----------------------------------------------------------------------------------------------------------------------- |
| `date`                      | Data ISO (`AAAA-MM-DD`)        | Dia calendário local da observação.                                                                                      |
| `product_id`                | Inteiro estável                | Chave primária imutável do produto no PostgreSQL.                                                                        |
| `sku`                       | Texto                          | Código único padronizado em maiúsculas.                                                                                  |
| `product_name`              | Texto                          | Nome descritivo do item.                                                                                                 |
| `category_name`             | Texto                          | Categoria do produto (útil para agrupamento hierárquico em _cold start_).                                                |
| `unit`                      | Código (`UN`, `KG`, etc.)      | Unidade de medida do produto. **Nunca misturar quantidades entre unidades diferentes.**                                  |
| `is_active`                 | Booleano                       | Indica se o produto está ativo; produtos inativos preservam toda a série histórica.                                      |
| `has_information`           | Booleano                       | `True` a partir da primeira data conhecida (cadastro ou primeira movimentação). `False` antes disso.                     |
| `had_stockout`              | Booleano / Nulo                | `True` se houve ruptura (saldo zero registrado em `stockout_periods`, fechamento `0` ou `ruptura_dia` no CSV histórico). |
| `availability_status`       | Categórico                     | Classificação explícita do dia: `DISPONIVEL_COM_DEMANDA`, `DISPONIVEL_SEM_DEMANDA`, `EM_RUPTURA` ou `SEM_INFORMACAO`.    |
| `observed_demand_qty`       | Decimal (na `unit` do produto) | Demanda operacional observada (`VENDA` + `CONSUMO`, abatendo estornos vinculados a saídas de demanda).                   |
| `sales_qty`                 | Decimal (`unit`)               | Parcela de saídas por `VENDA`.                                                                                           |
| `internal_consumption_qty`  | Decimal (`unit`)               | Parcela de saídas por `CONSUMO`.                                                                                         |
| `losses_damages_qty`        | Decimal (`unit`)               | Soma de `PERDA` e `AVARIA`. **Separada da demanda** para não distorcer a previsão.                                       |
| `other_exits_qty`           | Decimal (`unit`)               | Outras saídas (`OUTRO`).                                                                                                 |
| `entries_qty`               | Decimal (`unit`)               | Total de entradas no dia (`RECEBIMENTO` e `SALDO_INICIAL`).                                                              |
| `adjustments_net_qty`       | Decimal (`unit`)               | Saldo líquido de ajustes de inventário (`AJUSTE_POSITIVO - AJUSTE_NEGATIVO`).                                            |
| `reversals_net_qty`         | Decimal (`unit`)               | Saldo líquido dos lançamentos de `ESTORNO` do dia.                                                                       |
| `closing_stock`             | Decimal (`unit`) / Nulo        | Saldo reconstruído ao final do dia (ou saldo informado em importação histórica).                                         |
| `avg_entry_unit_cost`       | Decimal (`BRL`) / Nulo         | Custo unitário médio das entradas ocorridas naquele dia (preservado no tempo).                                           |
| `reference_unit_cost`       | Decimal (`BRL`)                | Custo unitário de referência atual do cadastro.                                                                          |
| `lead_time_days_config`     | Inteiro (`dias`) / Nulo        | Prazo estimado de reposição cadastrado no produto.                                                                       |
| `actual_lead_time_days_avg` | Decimal (`dias`) / Nulo        | Média de `(data_recebimento - data_pedido)` das entradas do dia com datas preenchidas.                                   |
| `data_origin`               | Texto                          | Origem dos registros (`OPERACIONAL`, `IMPORTACAO_HISTORICA`, `SEM_MOVIMENTO` ou `SEM_INFORMACAO`).                       |
| `is_synthetic_data`         | Booleano                       | `True` quando houver registros marcados como sintéticos (`seed-demo` ou CSV marcado como sintético).                     |

> **Por que `availability_status` é essencial para o modelo de IA?**
> Um dia em que `observed_demand_qty == 0` com `availability_status == "EM_RUPTURA"` significa que **não havia estoque para atender à procura** (demanda censurada), e não que o mercado deixou de consumir o item. Já `DISPONIVEL_SEM_DEMANDA` indica zero real com produto disponível, enquanto `SEM_INFORMACAO` evita confundir ausência de registro com zero.

### 1.2. Movimentações Analíticas Unificadas (`movimentacoes_analiticas_ia.csv`)

Reúne lançamentos operacionais (`OP-<id>`) e importações históricas para estudo (`HIST-<id>`) em formato transacional cronológico, preservando `unit_cost`, `supplier_name`, `order_date`, `received_date`, `actual_lead_time_days`, `is_demand` e `is_synthetic`.

---

## 2. Separação Arquitetural e Contrato de Integração Futura

As regras de previsão e sugestão de compras ficam isoladas em `backend/app/ai/`:

- `contracts.py`: define `ForecastInput`, `ForecastOutput` e o protocolo `DemandForecastProvider`.
- `replenishment.py`: contém a fórmula de decisão de compra desacoplada do algoritmo de previsão.
- `provider.py`: possui `NoModelProvider` (padrão quando não há modelo treinado) e `MovingAverageSimulationProvider` (simulação demonstrativa explícita).

### 2.1. Contrato de Entrada (`ForecastInput`)

- `product_id`, `sku`, `product_name`, `unit`
- `as_of_date`: data de corte causal (o modelo só pode enxergar histórico `<= as_of_date`)
- `horizon_days`: horizonte da previsão ($H$)
- `current_stock`: saldo disponível atual
- `safety_stock`: margem de segurança cadastrada
- `lead_time_days`: prazo de reposição do produto, ou prazo padrão do fornecedor preferencial ($L$)
- `open_purchase_orders_qty`: pedidos de compra em aberto (nesta v1 fixado em `0`, pronto para expansão)
- `history_df`: série diária histórica até `as_of_date`

### 2.2. Contrato de Saída (`ForecastOutput`)

- `product_id`
- `predicted_demand_horizon` e `predicted_demand_effective_window`
- `recommended_purchase_qty`
- `generated_at`, `period_start`, `period_end`
- `model_version`
- `reason_summary`: explicação legível da recomendação
- `prediction_interval_low` / `prediction_interval_high`: **preenchidos somente se o modelo fornecer intervalo validado** (permanecem `null` quando não houver validação probabilística)

### 2.3. Como Conectar o Futuro Modelo Python

1. **Em processo (scikit-learn / batch)**: crie uma classe em `backend/app/ai/` que implemente `DemandForecastProvider.predict(items: list[ForecastInput]) -> list[ForecastOutput]`, carregue o artefato treinado (ex.: `.joblib`) e substitua o provedor em `build_purchase_suggestions()`.
2. **Via API externa Python**: implemente um adaptador de `DemandForecastProvider` que envie o payload JSON serializado de `ForecastInput` para um serviço de inferência e converta a resposta em `ForecastOutput`, mantendo cadastros e movimentações intactos.

---

## 3. Regra de Decisão de Compra (Sem Dupla Contagem)

A **previsão de demanda** estima quanto será consumido/vendido; a **decisão de compra** decide quanto pedir.

Um erro clássico é somar a demanda durante o horizonte $H$ com a demanda durante o prazo de reposição $L$, o que conta duas vezes o intervalo $[t_0, t_0 + \min(H, L))$ porque ambos começam na data atual $t_0$.

Por isso, o sistema utiliza a **janela efetiva de cobertura**:
$$W = \max(H, L)$$

E calcula a quantidade sugerida como:
$$Q_{\text{rec}} = \max\Big(0,\; \hat{D}_{[t_0,\, t_0 + W)} + \text{estoque\_segurança} - (\text{saldo\_atual} + \text{pedidos\_abertos})\Big)$$

- Para unidades discretas (`UN`, `CX`, `PCT`, `PAR`, `FD`, `RL`), $Q_{\text{rec}}$ é arredondado para cima no inteiro mais próximo.
- Para unidades contínuas (`KG`, `G`, `L`, `ML`, `M`, `M2`), $Q_{\text{rec}}$ é arredondado para cima em 3 casas decimais.
- **Governança**: nenhuma recomendação gera pedido de compra automaticamente; a decisão final é sempre humana.

---

## 4. Proposta de Avaliação Acadêmica para o Projeto de IA

Para avaliar cientificamente o modelo na próxima etapa do projeto, recomenda-se o protocolo abaixo:

1. **Linha de Base (Baseline) Simples**:
   - Comparar o modelo de ML (ex.: LightGBM / Random Forest / Ridge com defasagens temporais e sazonalidade semanal) contra uma **Média Móvel Causal** (ex.: média dos últimos 14 ou 28 dias válidos sem ruptura). O modelo só justifica adoção se superar o baseline de forma consistente.
2. **Divisão Temporal Sem Embaralhamento**:
   - Nunca usar `train_test_split(..., shuffle=True)` em séries temporais. Separar rigorosamente por data (ex.: primeiros 70% dos dias para treino, 15% seguintes para validação de hiperparâmetros e 15% finais para teste cego).
3. **Avaliação Walk-Forward Causal**:
   - Simular previsões dia a dia ou semana a semana em datas de corte $t_k$, garantindo que o pipeline receba **exclusivamente informações disponíveis até $t_k$** (incluindo reconstrução de saldo e ruptura até $t_k$, sem vazamento do futuro).
4. **Métricas de Erro por Produto e Impacto Operacional**:
   - **Erro pontual por produto e agregado**: `MAE`, `RMSE`, `WAPE` (ponderado pelo volume, evitando explosão do MAPE em dias com demanda zero) e `Viés (Bias)` para detectar subestimação/superestimação sistemática.
   - **Impacto no negócio (simulação de estoque)**: taxa de ruptura (dias ou unidades não atendidas), nível de serviço (fill rate) e estoque médio excedente / capital imobilizado simulado ao aplicar $Q_{\text{rec}}$ vs política estática de estoque mínimo.
5. **Tratamento de Produtos Novos e Pouco Histórico (_Cold Start_)**:
   - Produtos com menos de $N$ dias válidos (ex.: `< 14` dias) não devem receber previsão direta de modelo complexo: adotar taxa média normalizada da **categoria** ou fallback explícito baseado em `min_stock` e `safety_stock`, sinalizando baixa confiança ao comprador.
6. **Transparência sobre Dados Sintéticos**:
   - Registros gerados pelo comando `seed-demo` ou importados com `sintetico=sim` são marcados com `is_synthetic = true`. **Dados sintéticos servem exclusivamente para validar o fluxo técnico, engenharia de atributos e contrato de software — eles não comprovam qualidade preditiva.** Toda métrica real de desempenho exige histórico real da empresa.
