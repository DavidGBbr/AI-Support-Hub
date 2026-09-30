# Documentação

| Documento | Conteúdo |
| --- | --- |
| [Arquitetura e contratos iniciais](adr/0001-architecture-contracts.md) | Entidades, relações, dependências e decisões do contrato v1 |
| [Guia da API e mocks](contracts/README.md) | Endpoints, desenvolvimento local e estados do frontend |
| [Onboarding](onboarding.md) | Preparação do ambiente e diagnóstico |
| [Produção](production.md) | Deploy, backup e rollback |

## Artefatos gerados

- [openapi.json](contracts/openapi.json): captura da especificação exposta pela aplicação.
- [examples.json](contracts/examples.json): exemplos validados pelos modelos da API.

Não edite esses arquivos manualmente. Para regenerar e conferir, execute em `apps/api`:

```sh
uv run python -m scripts.export_openapi
uv run python -m scripts.export_openapi --check
```
