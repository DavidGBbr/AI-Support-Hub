# Guia da API v1

[Arquitetura e convenções](../adr/0001-architecture-contracts.md) ·
[OpenAPI gerado](openapi.json) · [Exemplos gerados](examples.json)

## Endpoints

Prefixo: `/v1/workspaces/{workspace_id}`. Todas as operações exigem Bearer e
membership no workspace. IDs relacionados também são validados contra o workspace.
Swagger: `/docs`. Especificação: `/openapi.json`. Na produção atual, o base URL
inclui `/api` antes de `/v1`.

| Método | Caminho | Request | Resposta |
| --- | --- | --- | --- |
| GET | `/knowledge-bases` | Query `limit`, `cursor`; sem corpo | 200 `KnowledgeBasePage` |
| POST | `/knowledge-bases` | `KnowledgeBaseCreate` | 201 `KnowledgeBase` |
| POST | `/knowledge-bases/{knowledge_base_id}/uploads` | `UploadCreate` | 202 `UploadRegistered` |
| GET | `/documents/{document_id}` | Sem corpo | 200 `Document` |
| POST | `/chat` | `ChatRequest` | 200 `ChatResponse` |

Todas documentam `401`, `404`, `422`, `500` e `503` com o envelope `ErrorEnvelope`.
Listagem também retorna `400` para cursor inválido; chat retorna `409` quando a KB
não possui documentos prontos. Conversa de outra KB ou workspace retorna `404`.

### Criar Knowledge Base

`name`: 1–120 caracteres após remover espaços periféricos.
`description`: opcional, até 1000 caracteres. Nomes repetidos são permitidos.

```json
{
  "name": "Atendimento",
  "description": "Manuais de suporte"
}
```

### Registrar upload

```json
{
  "filename": "manual.pdf",
  "content_type": "application/pdf",
  "size_bytes": 1024
}
```

Formatos: `.pdf`/`application/pdf`, `.txt`/`text/plain` ou `.md`/`text/markdown`.
Limite: 1 byte a 20 MiB. Extensões minúsculas; nomes sem separadores de caminho ou
caracteres de controle. Incompatibilidade entre extensão e MIME retorna `422`.

A resposta `{document, upload}` fornece destino PUT, headers e expiração de 15 minutos.
O registro recebe metadados; os bytes são enviados ao destino retornado.

Fluxo planejado: `awaiting_upload → queued → processing → ready`, com falha terminal
`failed` e código `INVALID_FILE` ou `PROCESSING_FAILED`. A ingestão implementará a
confirmação do armazenamento, validação dos bytes e enfileiramento. O frontend consulta
o documento com backoff até `ready` ou `failed`.

### Conversar

```json
{
  "knowledge_base_id": "bc23a136-b564-4877-9d61-8dd012ba8ef8",
  "conversation_id": null,
  "message": "Como pedir suporte?"
}
```

`message`: 1–8000 caracteres após remover espaços periféricos.
`conversation_id` ausente ou nulo cria uma conversa; para continuar, reutilize
`conversation.id` retornado. A KB da conversa não pode mudar.

Resposta sem streaming: `{conversation, user_message, assistant_message, outcome}`.
As fontes ficam em `assistant_message.citations`; consulte cada documento pelo
`document_id`. Download de arquivos ainda não está contratado.

## Desenvolvimento com mocks

Configure no `.env` local e reinicie a API:

```dotenv
APP_ENVIRONMENT=development
CONTRACT_MOCKS_ENABLED=true
# Defina um token local de pelo menos 16 caracteres.
CONTRACT_MOCK_TOKEN=
```

Informe o token no **Authorize** do Swagger ou no header
`Authorization: Bearer <token-local>`. Não versione o token nem o inclua em builds
públicos do frontend.

| Fixture | UUID |
| --- | --- |
| Workspace permitido | `569396dd-dc68-41f7-bd24-63d4269f0a77` |
| Knowledge Base pronta | `bc23a136-b564-4877-9d61-8dd012ba8ef8` |
| Documento pronto | `f27cf9e2-c0db-4a76-8e4c-ec8848a41715` |

Base local: `http://localhost:8000/v1/workspaces/{workspace_id}`.
O token representa um membro do workspace de demonstração.

- Mocks são desabilitados por padrão; as operações retornam `503` antes da autenticação.
- Ativá-los em produção impede a inicialização; Compose de produção os força desligados.
- Dados ficam em memória por processo e são perdidos ao reiniciar; use uma instância.
- Uploads registrados ficam em `awaiting_upload`. A URL `.invalid` é ilustrativa.
- O chat usa texto e fonte fictícios; sucessos incluem `X-Contract-Mode: mock`.

## Estados do frontend

Use [examples.json](examples.json) para estados que o mock HTTP não executa.
As fixtures são validadas pelos mesmos modelos Pydantic da API.

| Estado | Sinal |
| --- | --- |
| Carregando | Requisição pendente; desabilitar submissão duplicada |
| Lista vazia | `items=[]`, `next_cursor=null` |
| Mais resultados | `next_cursor` não nulo; reenviar sem modificá-lo |
| Upload pendente | Documento `awaiting_upload` |
| Processando | Documento `queued` ou `processing` |
| Pronto | Documento `ready` |
| Falha de ingestão | HTTP 200, documento `failed` e `failure_code` |
| Resposta com fontes | `outcome=answered`, com citações |
| Sem evidências | `outcome=insufficient_context`, citações vazias |
| Base não pronta | 409 `DOCUMENTS_NOT_READY` |
| Formulário inválido | 422 `VALIDATION_ERROR`; preservar valores |
| Sessão inválida | 401 `UNAUTHENTICATED` |
| Recurso indisponível | 404 `NOT_FOUND` |
| Serviço indisponível | 503 `SERVICE_UNAVAILABLE` |
| Falha inesperada | 500 `INTERNAL_ERROR`; exibir request_id para suporte |

Sucessos não usam envelope `data`. Erros usam `{error:{code,message,request_id}}`.
Trate falhas de rede separadamente e evite reenvio automático de POST.

## Atualizar e verificar

Em `apps/api`:

```sh
uv run python -m scripts.export_openapi
uv run python -m scripts.export_openapi --check
uv run pytest
```

O exportador captura `/openapi.json` via TestClient e gera `examples.json` pelos modelos.
Não edite os JSONs manualmente. No PR, revise o diff e inclua links para o ADR e a captura,
com versão e consumidores afetados. A CI reprova artefatos divergentes.
