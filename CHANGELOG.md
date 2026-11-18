# Changelog

## [1.0.0] — 2026-11-18

### Adicionado

- Catálogo de produtos, fornecedores e categorias para uma empresa e um depósito.
- Movimentações transacionais, bloqueio de saldo negativo, ajustes e estornos vinculados.
- Perfis de administrador e operador, painel, relatórios e exportação CSV.
- Importação histórica separada do estoque operacional, séries diárias e contrato para previsão futura.
- Demonstração sintética, README, fluxograma em SVG/Mermaid e documentação de validação.

### Verificação

- 10 testes backend passaram com PostgreSQL real; build TypeScript/Vite passou.
- Ausência de modelo treinado, limites de segurança e alertas de dependências documentados em [VALIDACAO_V1.md](docs/VALIDACAO_V1.md).
