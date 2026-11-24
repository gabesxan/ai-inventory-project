# Entrega local do EstoqueFácil IA

## Verificação integrada

| Área | Evidência |
| --- | --- |
| Migrações | PostgreSQL 16 descartável. O staging e as tabelas de recomendações convergem em `0003_integrated_reports`. |
| Worker e Relatórios | O DQN em CPU treinou 180 episódios sintéticos com a semente 42 e publicou 3 UN para `DEMO-MOUSE-01`. O navegador exibiu a sugestão automaticamente, com a origem `Simulação acadêmica`. Execução integrada `da32c837-89c4-4b4f-a6c8-32681856a694`. |
| Permissões | Sessões reais de administrador e operador em contextos de navegador separados. Os cinco endpoints de Relatórios e Qualidade responderam 401 sem autenticação e 403 para o operador. |
| Comparação | 54 resultados para 18 episódios pareados, com 6 sementes em cada um dos três cenários. Custos simulados totais de 16.564,00 para DQN, 12.525,00 para base-stock e 12.498,00 para (s, S). A exportação preservou o filtro, a ordenação, os valores e a origem. |
| Importação | `run-a` produziu o lote `fb-cf6383848e73fdde76569d0b` com 650.376 eventos aceitos, 690 rejeições explicadas, 409.640 intervalos de cobertura e 6.997 produtos. `run-b`, uma segunda extração da mesma origem, retornou `already_imported` com o mesmo lote. A conferência ocorreu antes de semear a demonstração. Houve zero movimentos operacionais criados pela importação. Um teste concorrente em PostgreSQL confirmou a preservação dos totais quando duas aplicações do mesmo lote começam simultaneamente. |
| Histórico e exceções | O navegador exibiu o histórico e a qualidade do lote integrado. O CSV de um recorte real coincidiu com as linhas filtradas em JSON. A base contém 4.653.680 dias-produto com disponibilidade desconhecida e nenhuma ruptura historicamente confirmada. |
| Suítes | 118 testes Python, build de produção do Vite e navegador em 1440 × 900 e 390 × 844. |

O período da origem importada vai de 28/02/2024 a 18/11/2026. O saldo de abertura físico está indisponível. O relatório preserva essa lacuna e a data de snapshot desconhecida.

## Calibração legada

O modo calibrado usa dados com disponibilidade comprovada em partições cronológicas de 28, 14 e 14 dias. A recomendação usa estoque operacional rastreável e uma fila de recebimento conhecida. O prazo deve ter medição ou configuração explícita identificada. Uma fixture PostgreSQL verificou que o worker publica quando esses pré-requisitos estão presentes.

A base Firebird real não apresentou uma série elegível. O worker registrou `insufficient_data`, com zero execuções calibradas e contagem de movimentos operacionais preservada. A publicação calibrada real está condicionada à entrega de histórico adequado de disponibilidade, prazo e fila de recebimento. A comparação sintética permanece disponível.

## Reprodução local

Use um banco descartável de demonstração em `DATABASE_URL` e um banco descartável separado em `TEST_DATABASE_URL`. Os testes escrevem no banco configurado para testes. A suíte Firebird usa `LEGACY_PG_SOCKET`, `LEGACY_PG_PORT` e um papel `legacy` com permissão para criar bancos temporários no cluster descartável.

Execute a preparação e o worker a partir de `backend/`. Defina `ESTOQUEFACIL_DEMO_PASSWORD` localmente antes da criação do administrador.

```sh
python -m pip install -r requirements-dqn.txt
python -m alembic upgrade 0002_legacy_staging
python -m alembic upgrade head
python -m app.cli create-admin --name "EstoqueFácil Demo" --email estoque.demo@empresa.local --password "$ESTOQUEFACIL_DEMO_PASSWORD"
python -m app.cli seed-demo
python -m app.ai.replenishment_worker --sku DEMO-MOUSE-01 --warehouse 1 \
  --checkpoints ../.local/checkpoints --revision "$(git rev-parse HEAD)" --seed 42
```

Em outro terminal, com a mesma configuração do banco e `SECRET_KEY`, sirva a API a partir de `backend/`.

```sh
python -m uvicorn app.main:app --host 127.0.0.1 --port 8106
```

A partir de `frontend/`, sirva o aplicativo com uma origem presente em `CORS_ORIGINS` da API. Faça login e abra Relatórios, na aba Reposição.

```sh
npm ci
VITE_API_URL=http://127.0.0.1:8106/api npm run dev -- --host 127.0.0.1 --port 5180
```

A importação Firebird e as verificações de reextração estão documentadas em [DB-02](data/DB-02-apply-import.md) e [DB-15](data/DB-15-second-extract-and-repeat-import.md). O [contrato de relatórios](contracts/report-v1/README.md) descreve filtros, status e formatos. Checkpoints, credenciais, dados brutos e capturas ficam em áreas locais ignoradas pelo Git.
