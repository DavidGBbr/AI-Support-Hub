import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api import search as search_api
from app.core.config import get_settings
from app.core.db import get_session
from app.main import app
from app.models.domain import Document, DocumentStatus, KnowledgeBase


@pytest.fixture(params=["", "/api"], ids=["direct-local", "nginx-root-api"])
def routing(request, monkeypatch, tmp_path):
    workspace_id, kb_id = uuid.uuid4(), uuid.uuid4()
    session = Mock(spec=Session)
    previous_override = app.dependency_overrides.get(get_session)
    app.dependency_overrides[get_session] = lambda: session
    monkeypatch.setattr(get_settings(), "document_storage_dir", str(tmp_path))
    try:
        # Nginx strips /api; Uvicorn --root-path /api reconstructs this ASGI
        # scope. The same public URL must reach the handler in both topologies.
        with TestClient(app, root_path=request.param) as client:
            yield SimpleNamespace(
                client=client,
                session=session,
                workspace_id=workspace_id,
                kb_id=kb_id,
                root_path=request.param,
                prefix=f"/api/v1/workspaces/{workspace_id}/knowledge-bases/{kb_id}",
            )
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_session, None)
        else:
            app.dependency_overrides[get_session] = previous_override


def test_upload_routes_through_local_and_production_prefixes(routing):
    routing.session.scalar.return_value = KnowledgeBase(
        id=routing.kb_id,
        workspace_id=routing.workspace_id,
        name="Routing KB",
    )

    def refresh(document):
        document.status = DocumentStatus.PENDING
        document.failure_reason = None

    routing.session.refresh.side_effect = refresh
    response = routing.client.post(
        routing.prefix + "/documents",
        files={"file": ("routing.txt", b"Production routing regression", "text/plain")},
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["workspace_id"] == str(routing.workspace_id)
    assert body["knowledge_base_id"] == str(routing.kb_id)
    assert body["status"] == "PENDING"
    document = next(
        item.args[0]
        for item in routing.session.add.call_args_list
        if isinstance(item.args[0], Document)
    )
    assert Path(document.storage_path).read_bytes() == b"Production routing regression"


def test_document_lookup_routes_through_local_and_production_prefixes(routing):
    document_id = uuid.uuid4()
    routing.session.scalar.return_value = Document(
        id=document_id,
        workspace_id=routing.workspace_id,
        knowledge_base_id=routing.kb_id,
        filename="routing.txt",
        size_bytes=10,
        status=DocumentStatus.READY,
        failure_reason=None,
    )
    response = routing.client.get(routing.prefix + f"/documents/{document_id}")
    assert response.status_code == 200, response.text
    assert response.json()["id"] == str(document_id)
    assert response.json()["status"] == "READY"


def test_search_routes_through_local_and_production_prefixes(routing, monkeypatch):
    document_id = uuid.uuid4()
    search = Mock(
        return_value=(
            [
                {"document_id": document_id, "content": "Routing policy", "score": 1.0},
            ],
            1.5,
        )
    )
    monkeypatch.setattr(search_api, "search_chunks", search)
    response = routing.client.post(
        routing.prefix + "/search",
        json={"query": "Routing policy", "top_k": 1},
    )
    assert response.status_code == 200, response.text
    assert response.json()["results"][0]["document_id"] == str(document_id)
    search.assert_called_once_with(
        routing.session,
        workspace_id=routing.workspace_id,
        knowledge_base_id=routing.kb_id,
        query="Routing policy",
        top_k=1,
    )


def test_openapi_uses_proxy_root_once_and_hides_local_aliases(routing, monkeypatch):
    monkeypatch.setattr(app, "openapi_schema", None)
    monkeypatch.setattr(app, "servers", [])
    response = routing.client.get(routing.root_path + "/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    prefix = "/v1/workspaces/{workspace_id}/knowledge-bases/{knowledge_base_id}"
    assert prefix + "/search" in schema["paths"]
    assert prefix + "/documents" in schema["paths"]
    assert prefix + "/documents/{document_id}" in schema["paths"]
    assert all(not path.startswith("/api/") for path in schema["paths"])
    servers = [server["url"] for server in schema.get("servers", [])]
    assert servers == (["/api"] if routing.root_path else [])
