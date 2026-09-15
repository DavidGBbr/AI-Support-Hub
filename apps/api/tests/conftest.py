import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("POSTGRES_HOST", "postgres")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("REDIS_HOST", "redis")

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
