from uuid import uuid4

from app.database import MasterSessionLocal, TenantManager
from app.modules.tenants.models import MasterUser, Tenant


def register(api_client):
    response = api_client.post("/api/tenants/register-admin", json={
        "username": f"setup_{uuid4().hex[:12]}", "password": "review-password", "full_name": "Setup Admin",
    })
    assert response.status_code == 200
    return response.json()


def test_failed_tenant_initialization_can_be_retried(api_client, monkeypatch):
    registration = register(api_client)
    headers = {"Authorization": f"Bearer {registration['access_token']}"}
    payload = {"store_name": f"Retry Store {uuid4().hex[:12]}"}

    def fail_initialization(*args, **kwargs):
        raise RuntimeError("Simulated schema initialization failure")

    with monkeypatch.context() as patch:
        patch.setattr(TenantManager, "init_tenant_db", fail_initialization)
        response = api_client.post("/api/tenants/setup", json=payload, headers=headers)
    assert response.status_code == 503
    with MasterSessionLocal() as db:
        user = db.get(MasterUser, registration["user"]["id"])
        assert user.tenant_id is None
        assert db.query(Tenant).filter_by(owner_id=user.id).count() == 0
    retry = api_client.post("/api/tenants/setup", json=payload, headers=headers)
    assert retry.status_code == 200


def test_duplicate_setup_categories_and_brands_are_deduplicated(api_client):
    registration = register(api_client)
    headers = {"Authorization": f"Bearer {registration['access_token']}"}
    response = api_client.post("/api/tenants/setup", json={
        "store_name": f"Duplicate Setup {uuid4().hex[:12]}",
        "categories": ["Kaos", "Kaos"], "brands": ["Brand", "Brand"],
    }, headers=headers)
    assert response.status_code == 200
    token = response.json()["access_token"]
    categories = api_client.get("/api/catalog/categories", headers={"Authorization": f"Bearer {token}"}).json()
    assert len(categories) == 1


def test_non_admin_account_cannot_initialize_a_store(api_client):
    registration = register(api_client)
    with MasterSessionLocal() as db:
        db.get(MasterUser, registration["user"]["id"]).role = "cashier"
        db.commit()
    response = api_client.post("/api/tenants/setup", json={"store_name": "Unauthorized Store"}, headers={
        "Authorization": f"Bearer {registration['access_token']}",
    })
    assert response.status_code == 403
