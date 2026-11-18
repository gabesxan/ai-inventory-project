# Validação da publicação v1.0.0

Verificação realizada em 18/11/2026, preservando as regras e dependências da implementação recebida.

| Verificação                      | Resultado                                                                       |
| -------------------------------- | ------------------------------------------------------------------------------- |
| Backend                          | 10 testes pytest passaram com PostgreSQL local real.                            |
| Isolamento dos testes            | Antes de executar, foram conferidos host local e banco `ai_inventory_test`.     |
| Frontend                         | `npm run build` passou, incluindo compilação TypeScript.                        |
| Ambiente                         | Python 3.14.8, pytest 9.2.0 e Node.js 26.13.0.                                  |
| Aviso do pytest                  | Depreciação de HTTPX no TestClient da versão instalada do Starlette.            |
| `npm audit` do frontend          | 4 ocorrências altas, 0 críticas; propagação do aviso transitivo de `picomatch`. |
| Navegador / E2E                  | Não executado nesta publicação; não há suíte frontend/E2E configurada.          |
| Auditoria de dependências Python | Não executada.                                                                  |
| Pentest independente             | Não executado.                                                                  |

## Dependências

A auditoria npm aponta `picomatch` e seus dependentes `fdir`, `tinyglobby` e `vite`, conforme [GHSA-fc5q-39xc-vjpf](https://github.com/advisories/GHSA-fc5q-39xc-vjpf). As quatro ocorrências não equivalem a quatro avisos independentes. Não foram alteradas dependências durante a preparação desta v1.

Os requisitos Python usam versões mínimas abertas; não constituem lockfile reproduzível. Uma próxima etapa deve fixar e auditar o ambiente antes de hospedagem.

## Limites de segurança observados no código

- JWT é armazenado em `localStorage` no frontend.
- Há um segredo padrão de desenvolvimento na configuração Python; é necessário fornecer `SECRET_KEY` próprio.
- O Compose e os exemplos contêm credenciais locais de demonstração.
- A configuração de CORS restringe origens, mas aceita métodos e headers amplamente.
- A API não possui rate limiting configurado nesta versão.

Esses pontos foram documentados, não corrigidos ou certificados por esta publicação. Os testes aprovados não representam auditoria de segurança completa nem garantia de prontidão para produção.

## Conteúdo publicado

Código-fonte, migrations, lockfile npm, documentação e diagramas. Arquivos `.env`, ambiente virtual Python, dependências instaladas, caches e builds ficam fora do Git. A preparação dos READMEs não altera as regras de estoque ou a implementação de autenticação.
