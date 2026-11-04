from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.core.security import create_access_token
from app.database import MasterSessionLocal, TenantManager, get_master_db, get_db
from app.main import app
from app.modules.auth.models import User
from app.modules.tenants.models import MasterUser, Tenant


def auth_headers(tenant):
    return {"Authorization": f"Bearer {tenant['token']}"}


def test_tenant_header_without_login_cannot_read_catalog(api_client, tenant_factory):
    tenant = tenant_factory()
    response = api_client.get("/api/catalog/products", headers={"X-Tenant-Slug": tenant["slug"]})
    assert response.status_code == 401


def test_tenant_header_cannot_override_authenticated_store(api_client, tenant_factory):
    tenant_a = tenant_factory(categories=["Private A"])
    tenant_b = tenant_factory(categories=["Private B"])
    response = api_client.get("/api/catalog/categories", headers={
        **auth_headers(tenant_a), "X-Tenant-Slug": tenant_b["slug"],
    })
    assert response.status_code == 403
    assert "Private B" not in response.text


@pytest.mark.parametrize("path", ["/api/catalog/products", "/api/tenants/status"])
@pytest.mark.parametrize("expired", [False, True])
def test_bad_tokens_return_401_instead_of_500(api_client, path, expired):
    token = create_access_token({"sub": "expired"}, timedelta(seconds=-10)) if expired else "malformed.token"
    response = api_client.get(path, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_revoked_master_account_cannot_use_old_token(api_client, tenant_factory):
    tenant = tenant_factory()
    with MasterSessionLocal() as db:
        db.get(MasterUser, tenant["master_user_id"]).is_active = False
        db.commit()
    response = api_client.get("/api/catalog/products", headers=auth_headers(tenant))
    assert response.status_code == 401
    api_client.cookies.set("access_token", f"Bearer {tenant['token']}")
    page = api_client.get("/pos", follow_redirects=False)
    assert page.headers.get("location") == "/login"


def test_disabled_tenant_rejects_existing_session(api_client, tenant_factory):
    tenant = tenant_factory()
    with MasterSessionLocal() as db:
        db.get(Tenant, tenant["tenant_id"]).is_active = False
        db.commit()
    response = api_client.get("/api/catalog/products", headers=auth_headers(tenant))
    assert response.status_code == 403


def test_pages_use_current_role_instead_of_stale_token(api_client, tenant_factory):
    tenant = tenant_factory()
    with TenantManager.get_session(tenant["slug"]) as db:
        db.query(User).filter_by(username=tenant["username"]).one().role = "cashier"
        db.commit()
    api_client.cookies.set("access_token", f"Bearer {tenant['token']}")
    response = api_client.get("/backoffice/users", follow_redirects=False)
    assert response.headers.get("location") == "/pos"


def test_user_creation_cannot_take_over_another_tenants_login(api_client, tenant_factory):
    tenant_a = tenant_factory()
    tenant_b = tenant_factory()
    username = f"shared_{uuid4().hex[:12]}"
    original = {"username": username, "full_name": "Original Cashier", "password": "original-password"}
    assert api_client.post("/api/auth/users", json=original, headers=auth_headers(tenant_a)).status_code == 200
    response = api_client.post("/api/auth/users", json={
        **original, "password": "attacker-password", "role": "admin",
    }, headers=auth_headers(tenant_b))
    assert response.status_code == 400
    with MasterSessionLocal() as db:
        assert db.query(MasterUser).filter_by(username=username).one().tenant_id == tenant_a["tenant_id"]
    with TenantManager.get_session(tenant_b["slug"]) as db:
        assert db.query(User).filter_by(username=username).first() is None
    assert api_client.post("/api/auth/login", json={
        "username": username, "password": "original-password",
    }).status_code == 200


def test_failed_master_sync_does_not_leave_a_tenant_user(api_client, tenant_factory):
    tenant = tenant_factory()
    username = f"failed_sync_{uuid4().hex[:12]}"

    def failing_master_db():
        with MasterSessionLocal() as db:
            def fail_commit():
                raise SQLAlchemyError("Simulated master commit failure")
            db.commit = fail_commit
            yield db

    app.dependency_overrides[get_master_db] = failing_master_db
    response = api_client.post("/api/auth/users", json={
        "username": username, "full_name": "Failed Sync", "password": "review-password",
    }, headers=auth_headers(tenant))
    assert response.status_code == 503
    with TenantManager.get_session(tenant["slug"]) as db:
        assert db.query(User).filter_by(username=username).first() is None
    with MasterSessionLocal() as db:
        assert db.query(MasterUser).filter_by(username=username).first() is None


def test_last_active_admin_cannot_be_demoted(api_client, tenant_factory):
    tenant = tenant_factory()
    users = api_client.get("/api/auth/users", headers=auth_headers(tenant)).json()
    admin_id = next(user["id"] for user in users if user["username"] == tenant["username"])
    response = api_client.put(f"/api/auth/users/{admin_id}", json={"role": "cashier"}, headers=auth_headers(tenant))
    assert response.status_code == 400


def test_inactive_admin_can_be_deleted_when_an_active_admin_remains(api_client, tenant_factory):
    tenant = tenant_factory()
    created = api_client.post("/api/auth/users", json={
        "username": f"inactive_admin_{uuid4().hex[:8]}",
        "full_name": "Inactive Admin", "role": "admin", "is_active": False,
        "password": "review-password",
    }, headers=auth_headers(tenant))
    assert created.status_code == 200
    response = api_client.delete(f"/api/auth/users/{created.json()['id']}", headers=auth_headers(tenant))
    assert response.status_code == 200


def test_login_cookie_is_httponly_and_secure_on_https(api_client):
    username = f"cookie_{uuid4().hex[:12]}"
    payload = {"username": username, "full_name": "Cookie Admin", "password": "review-password"}
    registration = api_client.post("/api/tenants/register-admin", json=payload)
    assert registration.status_code == 200
    login = api_client.post("/api/auth/login", json={"username": username, "password": payload["password"]})
    is_httponly = "httponly" in login.headers["set-cookie"].lower()
    is_secure = "secure" in login.headers["set-cookie"].lower()
    assert is_httponly
    assert is_secure


def test_cookie_authenticated_mutation_rejects_cross_origin(api_client, tenant_factory):
    tenant = tenant_factory()
    api_client.cookies.set("access_token", f"Bearer {tenant['token']}")
    response = api_client.post("/api/catalog/categories", json={"name": "CSRF category"}, headers={"Origin": "https://attacker.example"})
    assert response.status_code == 403


def test_case_insensitive_login_works_for_legacy_mixed_case_username(api_client, tenant_factory):
    tenant = tenant_factory()
    with MasterSessionLocal() as db:
        db.get(MasterUser, tenant["master_user_id"]).username = tenant["username"].upper()
        db.commit()
    response = api_client.post("/api/auth/login", json={
        "username": tenant["username"], "password": "review-password",
    })
    assert response.status_code == 200


def test_password_change_invalidates_previously_issued_tokens(api_client, tenant_factory):
    tenant = tenant_factory()
    username = f"password_reset_{uuid4().hex[:10]}"
    created = api_client.post("/api/auth/users", json={
        "username": username, "full_name": "Password Reset", "password": "original-password",
    }, headers=auth_headers(tenant))
    assert created.status_code == 200
    login = api_client.post("/api/auth/login", json={"username": username, "password": "original-password"})
    old_token = login.json()["access_token"]
    updated = api_client.put(f"/api/auth/users/{created.json()['id']}", json={"password": "replacement-password"}, headers=auth_headers(tenant))
    assert updated.status_code == 200
    old_session = api_client.get("/api/auth/me", headers={"Authorization": f"Bearer {old_token}"})
    assert old_session.status_code == 401
    new_login = api_client.post("/api/auth/login", json={"username": username, "password": "replacement-password"})
    assert new_login.status_code == 200


def test_recreated_account_cannot_reuse_deleted_accounts_token(api_client, tenant_factory):
    tenant = tenant_factory()
    username = f"recreated_{uuid4().hex[:10]}"
    payload = {"username": username, "full_name": "Recreated Account", "password": "review-password"}
    created = api_client.post("/api/auth/users", json=payload, headers=auth_headers(tenant))
    login = api_client.post("/api/auth/login", json={"username": username, "password": payload["password"]})
    old_token = login.json()["access_token"]
    deleted = api_client.delete(f"/api/auth/users/{created.json()['id']}", headers=auth_headers(tenant))
    assert deleted.status_code == 200
    recreated = api_client.post("/api/auth/users", json=payload, headers=auth_headers(tenant))
    assert recreated.status_code == 200
    old_session = api_client.get("/api/auth/me", headers={"Authorization": f"Bearer {old_token}"})
    assert old_session.status_code == 401


@pytest.mark.parametrize("operation", ["create", "update"])
def test_tenant_commit_failure_compensates_a_committed_master_change(api_client, tenant_factory, operation):
    tenant = tenant_factory()
    username = f"compensation_{uuid4().hex[:10]}"
    payload = {"username": username, "full_name": "Original Name", "password": "review-password"}
    if operation == "update":
        initial = api_client.post("/api/auth/users", json=payload, headers=auth_headers(tenant))
        assert initial.status_code == 200
        user_id = initial.json()["id"]

    def failing_tenant_db():
        with TenantManager.get_session(tenant["slug"]) as db:
            db.info["tenant_id"] = tenant["tenant_id"]

            def fail_commit():
                raise SQLAlchemyError("Simulated tenant commit failure")

            db.commit = fail_commit
            yield db

    app.dependency_overrides[get_db] = failing_tenant_db
    if operation == "create":
        response = api_client.post("/api/auth/users", json=payload, headers=auth_headers(tenant))
    else:
        response = api_client.put(f"/api/auth/users/{user_id}", json={"full_name": "Changed Name"}, headers=auth_headers(tenant))
    assert response.status_code == 503
    with MasterSessionLocal() as db:
        user = db.query(MasterUser).filter_by(username=username).first()
        if operation == "create":
            assert user is None
        else:
            assert user.full_name == "Original Name"
    with TenantManager.get_session(tenant["slug"]) as db:
        user = db.query(User).filter_by(username=username).first()
        if operation == "create":
            assert user is None
        else:
            assert user.full_name == "Original Name"
