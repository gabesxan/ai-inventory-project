<div align="center">

# EstoqueFácil IA

**Estoque rastreável hoje. Dados preparados para estudar a demanda amanhã.**

Sistema de gestão de estoque com movimentações transacionais e uma camada analítica separada.

![Versão 1.0.0](https://img.shields.io/badge/vers%C3%A3o-1.0.0-2563EB?style=flat-square)
![React e TypeScript](https://img.shields.io/badge/frontend-React%20%2B%20TypeScript-111827?style=flat-square)
![FastAPI e PostgreSQL](https://img.shields.io/badge/backend-FastAPI%20%2B%20PostgreSQL-111827?style=flat-square)
![Preparação para IA](https://img.shields.io/badge/IA-dados%20%2B%20contrato-DBEAFE?style=flat-square&labelColor=111827)

[O projeto](#o-projeto) · [Fluxograma](#como-o-estoque-é-atualizado) · [Executar](#executar-localmente) · [Regras](#regras-que-protegem-o-estoque) · [Dados para IA](#o-que-ia-significa-nesta-v1) · [Verificações](#verificações) · [Limitações](#limitações-e-próximos-passos)

</div>

## O projeto

O **EstoqueFácil IA** organiza produtos, fornecedores e movimentações de uma pequena empresa com um único depósito. Mantém o saldo e o histórico de estoque e usa uma Deep Q-Network (DQN) para sugerir quantidades de reposição.

O projeto combina **React + TypeScript** no frontend com **FastAPI + PostgreSQL** no backend. A interface usa português brasileiro, valores em reais e datas no formato brasileiro.

O DQN foi treinado e avaliado em simulação. O worker grava suas recomendações no PostgreSQL, e a interface as exibe em **Relatórios → Reposição** com a origem do modelo. A avaliação com dados operacionais reais ainda está pendente. [Documentação técnica da IA e do banco](docs/AI_TECHNICAL_ARCHITECTURE.md)

## O que está implementado

| Módulo              | Entrega                                                                                                                 |
| ------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| Acesso              | Login, logout com revogação de JWT e perfis de administrador e operador.                                                |
| Catálogo            | Categorias, fornecedores, produtos, SKU único, código de barras opcional, unidade, localização e parâmetros de estoque. |
| Movimentação        | Entradas, saídas, ajustes e estornos vinculados, com regras e histórico.                                                |
| Consistência        | Bloqueio transacional por produto e restrições no PostgreSQL para impedir saldo negativo.                               |
| Painel              | Indicadores reais, itens abaixo do mínimo e evolução de movimentações com unidades separadas.                           |
| Relatórios          | Estoque, movimentações, histórico importado, exceções, sugestões de reposição e comparação de políticas.                |
| Histórico de estudo | Importação CSV com prévia, erros por linha e deduplicação, sem alterar o estoque operacional.                           |
| Camada analítica    | Séries diárias, períodos de ruptura, demanda separada de perdas e cobertura do histórico importado do Firebird.         |
| Reposição com IA    | DQN em CPU, execução em worker separado, resultados persistidos e comparação com base-stock e (s, S).                  |

## Como o estoque é atualizado

![Fluxograma das movimentações e da preparação analítica](docs/diagrams/estoque.svg)

[Abrir fluxograma em tamanho integral](docs/diagrams/estoque.svg) · [Fonte editável em Mermaid](docs/diagrams/estoque.mmd)

Uma movimentação aceita grava o evento e atualiza o saldo dentro da mesma transação. O histórico CSV de estudo segue uma trilha separada e não altera o saldo atual do produto.

## Regras que protegem o estoque

| Regra                   | Comportamento                                                                                               |
| ----------------------- | ----------------------------------------------------------------------------------------------------------- |
| Saldo inicial explícito | Produtos começam em zero; saldo inicial é uma entrada identificada.                                         |
| Saldo não negativo      | Saída e estorno que deixariam saldo negativo são rejeitados.                                                |
| Concorrência            | A movimentação bloqueia a linha do produto com `SELECT ... FOR UPDATE` antes de calcular o novo saldo.      |
| Unidades discretas      | `UN`, `CX`, `PCT`, `PAR`, `FD` e `RL` exigem quantidades inteiras.                                          |
| Unidades contínuas      | `KG`, `G`, `L`, `ML`, `M` e `M2` aceitam quantidades com até três casas decimais.                           |
| Dinheiro                | Custos usam decimal com duas casas; os cálculos evitam ponto flutuante binário.                             |
| Preservação             | Produtos são inativados; unidade não pode ser trocada depois de haver movimentações.                        |
| Correção de histórico   | Ajustes e estornos exigem administrador e justificativa; estorno duplo e estorno de estorno são bloqueados. |
| Indicadores             | Quantidades de unidades incompatíveis não são somadas como se fossem equivalentes.                          |
| Importação analítica    | Dados históricos importados permanecem separados do saldo operacional.                                      |

**Exemplo coberto por teste:** duas requisições tentam retirar 6 unidades de um produto com saldo 10. Somente uma pode concluir; o saldo final é 4, sem uma segunda retirada indevida.

## Arquitetura

```mermaid
flowchart LR
    UI["React + TypeScript<br/>Catálogo · movimentos · relatórios"]
    API["FastAPI + Pydantic<br/>JWT · perfis · validação"]
    SVC["Serviços de domínio<br/>Unidades · saldo · transações"]
    DB[("PostgreSQL 16<br/>SQLAlchemy + Alembic")]
    FB[("Firebird legado")]
    IMPORT["Importação reconciliada<br/>Eventos · cobertura · lotes"]
    WORKER["Worker de reposição<br/>Simulador · DQN em CPU"]
    UI --> API --> SVC --> DB
    FB --> IMPORT --> DB
    DB -->|"Saldo e histórico elegível"| WORKER
    WORKER -->|"Execuções, sugestões e estados"| DB
    DB -->|"Resultados persistidos"| API
    classDef app fill:#EFF6FF,stroke:#2563EB,color:#172554,stroke-width:2px;
    classDef core fill:#111827,stroke:#111827,color:#FFFFFF,stroke-width:2px;
    classDef data fill:#F0FDFA,stroke:#0D9488,color:#134E4A;
    class UI,API app;
    class SVC,WORKER core;
    class FB,IMPORT,DB data;
```

| Camada       | Tecnologias                                                     |
| ------------ | --------------------------------------------------------------- |
| Interface    | React 18, TypeScript, Vite, React Router e Lucide; CSS próprio. |
| API          | Python, FastAPI, Pydantic e Uvicorn.                            |
| Dados        | PostgreSQL 16, SQLAlchemy 2, psycopg 3 e Alembic.               |
| Autenticação | bcrypt, PyJWT e tabela de revogação de tokens.                  |
| IA e análise | PyTorch em CPU, NumPy, pandas e um simulador diário de estoque. |
| Testes       | pytest, HTTPX/TestClient e PostgreSQL real.                     |

```text
.
├── backend/
│   ├── app/
│   │   ├── api/          # Rotas HTTP e dependências de autorização
│   │   ├── services/     # Catálogo, estoque, relatórios e unidades
│   │   ├── models/       # Modelos SQLAlchemy
│   │   ├── schemas/      # Contratos Pydantic
│   │   ├── ai/           # Importação, séries, provedores e reposição
│   │   └── cli.py        # Criação de administrador e demonstração
│   ├── alembic/          # Migrações PostgreSQL
│   └── tests/            # Integração, permissões e concorrência
├── frontend/
│   └── src/              # Páginas, componentes, API e estilos
├── docs/
│   ├── diagrams/         # Fluxograma SVG e fonte Mermaid
│   ├── SPECIFICATION.md
│   ├── AI_INTEGRATION_AND_EVALUATION.md
│   └── VALIDACAO_V1.md
└── docker-compose.yml    # PostgreSQL para desenvolvimento
```

## Executar localmente

### 1. Pré-requisitos e configuração

- Python **3.14**, versão usada nesta verificação; outras versões não foram testadas nesta publicação.
- Node.js e npm compatíveis com o Vite instalado. Build verificado com Node **26.13.0**.
- PostgreSQL 16 ou Docker Compose.

```bash
git clone https://github.com/gabesxan/ai-inventory-project.git
cd ai-inventory-project
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

A aplicação Python lê `backend/.env`; o frontend lê `frontend/.env`. O exemplo na raiz é uma referência consolidada, não substitui esses arquivos.

No `backend/.env`, configure:

```dotenv
DATABASE_URL=postgresql+psycopg://inventory:inventory_dev_pwd@localhost:5432/ai_inventory
TEST_DATABASE_URL=postgresql+psycopg://inventory:inventory_dev_pwd@localhost:5432/ai_inventory_test
ACCESS_TOKEN_EXPIRE_MINUTES=480
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

Gere um segredo local e use o resultado em `SECRET_KEY`:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
```

A senha do PostgreSQL acima é exclusiva da configuração de desenvolvimento fornecida. Não reutilize os exemplos como credenciais de hospedagem.

### 2. Iniciar o PostgreSQL

```bash
docker compose up -d postgres
```

O Compose cria o banco `ai_inventory` na porta `5432`. Crie também o banco de testes:

```bash
docker compose exec postgres createdb -U inventory -O inventory ai_inventory_test
```

Se o banco já existir, não é necessário recriá-lo. Se usar PostgreSQL instalado diretamente, crie o usuário e os dois bancos equivalentes e ajuste as URLs.

### 3. Instalar o backend e aplicar a migration

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
alembic upgrade head
```

### 4. Criar o administrador e a demonstração

Com o ambiente virtual ativo, dentro de `backend/`:

```bash
python -m app.cli create-admin \
  --name "Administrador Principal" \
  --email "admin@empresa.local" \
  --password "EscolhaUmaSenhaLocalForte!"

python -m app.cli seed-demo
```

O `seed-demo` não limpa tabelas: adiciona dados fictícios marcados como sintéticos e ignora produtos de demonstração já existentes. Exige um administrador previamente criado.

Ele também cria o operador fictício `operador.demo@empresa.local`, com senha `DemoOp123!`. Execute o seed somente no ambiente de demonstração que deseja popular.

### 5. Iniciar API e interface

Terminal da API, em `backend/`, com o ambiente virtual ativo:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Outro terminal, a partir da raiz:

```bash
cd frontend
npm ci
npm run dev -- --host 127.0.0.1
```

| Serviço                 | Endereço                                                                 |
| ----------------------- | ------------------------------------------------------------------------ |
| Interface               | [http://localhost:5173](http://localhost:5173)                           |
| API                     | [http://127.0.0.1:8000](http://127.0.0.1:8000)                           |
| Documentação interativa | [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)                 |
| Contrato OpenAPI        | [http://127.0.0.1:8000/openapi.json](http://127.0.0.1:8000/openapi.json) |
| Saúde básica da API     | [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)     |

O proxy `/api` do Vite encaminha o desenvolvimento para `127.0.0.1:8000`. No build de produção, configure esse encaminhamento no servidor web ou ajuste `VITE_API_URL` antes do build. A rota de saúde atual não verifica disponibilidade do banco.

## Roteiro de demonstração

1. Entre como administrador e consulte o painel.
2. Abra produtos e confira unidade, mínimo, segurança e localização.
3. Em um produto de teste, registre entrada de 10 e saída de 3: saldo esperado 7.
4. Tente retirar 8: a operação deve ser recusada.
5. Registre um ajuste justificado e consulte o histórico; use estorno para observar as regras de reversão.
6. Entre como operador e confira as restrições administrativas.
7. Exporte um relatório filtrado.
8. Em **Dados para IA**, baixe o modelo CSV, envie um histórico, revise a prévia e confirme. Confira que o saldo operacional não mudou.
9. Execute o [roteiro do worker](docs/LOCAL_DELIVERY.md#reprodução-local) na base de demonstração e abra **Relatórios → Reposição**. Confira a quantidade, a origem **Simulação acadêmica** e a comparação entre políticas.

## IA de reposição e banco de dados

O DQN recebe o saldo atual e a fila de recebimentos e escolhe uma quantidade inteira de compra. O worker grava a execução, a recomendação e o estado do SKU no PostgreSQL. A decisão de compra permanece com o usuário.

- [Arquitetura técnica, treinamento, avaliação e diagrama do banco](docs/AI_TECHNICAL_ARCHITECTURE.md)
- [Roteiro local e evidências de integração](docs/LOCAL_DELIVERY.md)
- [Dicionário das exportações analíticas e contrato de previsão da v1](docs/AI_INTEGRATION_AND_EVALUATION.md)

## Acesso e segurança

| Operação                                   | Operador | Administrador |
| ------------------------------------------ | -------- | ------------- |
| Consultar catálogo, painel e relatórios    | Sim      | Sim           |
| Registrar entradas e saídas                | Sim      | Sim           |
| Criar, editar e inativar cadastros         | Não      | Sim           |
| Ajustar e estornar estoque                 | Não      | Sim           |
| Gerenciar usuários                         | Não      | Sim           |
| Importar histórico e acessar dados para IA | Não      | Sim           |

As restrições são aplicadas no backend. Consulte [as dependências de autorização](backend/app/api/deps.py) e [a especificação](docs/SPECIFICATION.md) para detalhes.

A implementação usa hash de senhas com bcrypt, JWT assinado e revogação do `jti` persistida no logout. **O frontend armazena o token no `localStorage` nesta v1**; a publicação não deve ser interpretada como hardening concluído. A configuração possui valores de desenvolvimento e precisa de segredo próprio, HTTPS e revisão antes de hospedagem.

## Verificações

Na preparação desta publicação:

- **10 testes de backend passaram** com PostgreSQL real, incluindo disputa concorrente por saldo.
- **Build do frontend passou**, incluindo compilação TypeScript.
- O pytest emitiu um aviso de depreciação na integração TestClient/HTTPX; os testes concluíram sem falhas.

```bash
# Backend: dentro de backend/, ambiente virtual ativo.
pytest -v

# Frontend: dentro de frontend/.
npm run build
```

> Os testes truncam tabelas no banco indicado por `TEST_DATABASE_URL`. Confira que aponta para `ai_inventory_test` local e descartável. Não use o banco operacional.

Cobertura existente:

| Área      | Cenários                                                                    |
| --------- | --------------------------------------------------------------------------- |
| Acesso    | Login, usuário inativo, logout revogável e restrições por perfil.           |
| Catálogo  | SKU duplicado, código de barras opcional/único e regras de unidade.         |
| Estoque   | Entrada/saída, saldo insuficiente, produto inativo e retiradas simultâneas. |
| Correções | Ajustes, estornos e bloqueios de reversão inválida.                         |
| Dados     | Ruptura, relatórios, importação isolada, exportação e reposição.            |

Não há scripts de lint, suíte de testes frontend ou E2E configurados nesta v1. Navegação completa em navegador e auditoria de segurança independente não foram executadas nesta publicação.

[Registro de validação da v1](docs/VALIDACAO_V1.md)

## API: mapa de entrada

| Grupo                              | Prefixo                             |
| ---------------------------------- | ----------------------------------- |
| Autenticação                       | `/api/auth`                         |
| Usuários                           | `/api/users`                        |
| Categorias e fornecedores          | `/api/categories`, `/api/suppliers` |
| Produtos                           | `/api/products`                     |
| Movimentações                      | `/api/movements`                    |
| Painel                             | `/api/dashboard`                    |
| Relatórios                         | `/api/reports`                      |
| Importação, exportação e sugestões | `/api/ai`                           |

As rotas protegidas recebem `Authorization: Bearer <token>`. Os schemas e os parâmetros podem ser consultados na documentação OpenAPI gerada pela API.

## Limitações e próximos passos

- Uma empresa e um depósito; sem PDV, emissão fiscal, pagamentos ou gestão de pedidos de compra.
- O DQN atende SKUs em unidades inteiras (`UN`). As métricas publicadas medem reposição no simulador. O recorte real legado ainda carece de evidência suficiente para calibração.
- Valor estimado do estoque é uma referência gerencial, sem método contábil de avaliação.
- O frontend mantém JWT no armazenamento acessível a JavaScript; migrar e endurecer a gestão da sessão é uma evolução de segurança.
- Rate limiting, política de produção, backups e observabilidade ainda precisam de implementação ou validação.
- Os requisitos Python usam intervalos abertos, sem lockfile de ambiente. Builds futuros podem resolver versões diferentes das verificadas aqui.
- A auditoria npm e suas pendências estão registradas em [VALIDACAO_V1.md](docs/VALIDACAO_V1.md).
- O Compose disponibiliza o PostgreSQL. API, interface, proxy e HTTPS de produção precisam de configuração própria.
- Esta publicação contém código para execução local; não representa um serviço de produção hospedado.

Próximas etapas incluem endurecer a autenticação, fixar as dependências Python, configurar CI e avaliar a reposição calibrada com histórico real elegível.

---

Desenvolvido por [Gabriel Bizerra](https://github.com/gabesxan). Demonstração com dados fictícios e marcação de origem sintética.
