# ruff: noqa: E402
# Engine configuration must precede imports that register application models.
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
import secrets

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings

# Configure the application before importing its engines. Endpoint tests must
# never connect to a configured cloud database or the developer's local data.
_test_data = TemporaryDirectory(prefix="momaz-pos-tests-")
_test_root = Path(_test_data.name)
settings.DATABASE_URL = ""
settings.DATABASE_URL_UNPOOLED = ""
settings.IS_PRODUCTION = False
settings.IS_VERCEL = False
settings.SECRET_KEY = secrets.token_urlsafe(48)
settings.MASTER_DATABASE_PATH = _test_root / "master.db"
settings.MASTER_DATABASE_URL = f"sqlite:///{settings.MASTER_DATABASE_PATH}"
settings.MASTER_DATABASE_URL_UNPOOLED = settings.MASTER_DATABASE_URL
settings.TENANTS_DIR = _test_root / "tenants"
settings.TENANTS_DIR.mkdir()

from app.database import Base, TenantManager, master_engine
from app.core.security import hash_password
from app.core.models import StoreSettings
from app.modules.auth.models import User
from app.main import app

TEST_DATABASE_URL = "sqlite:///:memory:"

@pytest.fixture(scope="session", autouse=True)
def isolated_application_data():
    yield
    for slug in list(TenantManager._engines):
        TenantManager.close_tenant(slug)
    master_engine.dispose()
    _test_data.cleanup()


@pytest.fixture(autouse=True)
def isolated_uploads(monkeypatch):
    from app.core import storage

    monkeypatch.delenv("BLOB_READ_WRITE_TOKEN", raising=False)
    monkeypatch.delenv("BLOB_STORE_ID", raising=False)
    monkeypatch.setattr(storage, "LOCAL_UPLOAD_DIR", _test_root / "uploads" / "products")


@pytest.fixture
def api_client():
    from fastapi.testclient import TestClient

    with TestClient(app, base_url="https://testserver", raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def tenant_factory(api_client):
    def create_tenant(**setup):
        username = f"review_admin_{uuid4().hex[:12]}"
        registration = api_client.post("/api/tenants/register-admin", json={
            "username": username,
            "password": "review-password",
            "full_name": "Review Admin",
        })
        assert registration.status_code == 200, registration.text
        data = registration.json()
        response = api_client.post(
            "/api/tenants/setup",
            json={"store_name": f"Review Store {uuid4().hex[:12]}", **setup},
            headers={"Authorization": f"Bearer {data['access_token']}"},
        )
        assert response.status_code == 200, response.text
        result = response.json()
        api_client.cookies.clear()
        return {
            "username": username,
            "master_user_id": data["user"]["id"],
            "token": result["access_token"],
            "slug": result["tenant"]["slug"],
            "tenant_id": result["tenant"]["id"],
        }

    return create_tenant


@pytest.fixture(scope="function")
def db_session():
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    
    session = TestingSessionLocal()
    
    # Seed default user and store settings for testing
    admin = User(
        username="admin_test",
        password_hash=hash_password("admin123"),
        full_name="Admin Test",
        role="admin"
    )
    cashier = User(
        username="cashier_test",
        password_hash=hash_password("cashier123"),
        full_name="Cashier Test",
        role="cashier"
    )
    settings = StoreSettings(store_name="Test Fashion Store", return_policy_days=7)
    session.add_all([admin, cashier, settings])
    session.commit()
    
    yield session
    
    session.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
