import os
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("POSTGRES_HOST", "postgres")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("REDIS_HOST", "redis")

from app.core.config import get_settings
from app.core.db import get_session
from app.main import app
from app.models import Base

ADMIN_WORKSPACE_ID = "11111111-1111-4111-8111-111111111111"
OTHER_WORKSPACE_ID = "22222222-2222-4222-8222-222222222222"
ADMIN_WORKSPACE = UUID(ADMIN_WORKSPACE_ID)
OTHER_WORKSPACE = UUID(OTHER_WORKSPACE_ID)
ADMIN_TOKEN = "billing-admin-token"
WEBHOOK_SECRET = "whsec_test_secret"
PRO_PRICE_ID = "price_test_pro"
STRIPE_SECRET_KEY = "sk_test_secret_value"
AUTH_HEADERS = {"Authorization": f"Bearer {ADMIN_TOKEN}"}


@pytest.fixture(autouse=True)
def reset_settings_cache():
    yield
    get_settings.cache_clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def db_session():
    """Isolated database for a single test."""
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = testing_session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def stripe_env(monkeypatch):
    """Stripe test mode configuration for a single test."""
    values = {
        "STRIPE_SECRET_KEY": STRIPE_SECRET_KEY,
        "STRIPE_PUBLISHABLE_KEY": "pk_test_123",
        "STRIPE_PRO_PRICE_ID": PRO_PRICE_ID,
        "STRIPE_WEBHOOK_SECRET": WEBHOOK_SECRET,
        "BILLING_ADMIN_TOKEN": ADMIN_TOKEN,
        "BILLING_ADMIN_WORKSPACE_ID": ADMIN_WORKSPACE_ID,
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    return values


@pytest.fixture
def billing_client(db_session, stripe_env):
    """Client wired to the isolated database and to the Stripe test config."""
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as billing_client:
        yield billing_client
    app.dependency_overrides.clear()


@pytest.fixture
def queued_events(monkeypatch):
    """Capture the events handed over to the worker instead of queueing them."""
    from app.services import billing

    queued: list[str] = []
    monkeypatch.setattr(billing, "enqueue_event", queued.append)
    return queued
