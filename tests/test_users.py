import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import TenantManager

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c

@pytest.fixture(scope="module")
def test_setup_admin(client):
    uid = uuid.uuid4().hex[:6]
    username = f"admin_usr_{uid}"
    password = "password123"
    store_name = f"User Store {uid}"

    # 1. Register Admin
    reg_res = client.post("/api/tenants/register-admin", json={
        "username": username,
        "password": password,
        "full_name": f"Admin User {uid}"
    })
    assert reg_res.status_code == 200

    # 2. Login
    login_res = client.post("/api/auth/login", json={
        "username": username,
        "password": password
    })
    assert login_res.status_code == 200
    token_pre = login_res.json()["access_token"]

    # 3. Setup Tenant
    setup_payload = {
        "store_name": store_name,
        "tagline": "Toko Pakaian",
        "address": "Jl. Pengguna No. 1",
        "phone": "0811223344",
        "return_policy_days": 7,
        "tax_rate": 11,
        "is_tax_enabled": False,
        "categories": ["Kaos"],
        "brands": ["BrandA"]
    }
    setup_res = client.post(
        "/api/tenants/setup",
        json=setup_payload,
        headers={"Authorization": f"Bearer {token_pre}"}
    )
    assert setup_res.status_code == 200
    setup_data = setup_res.json()
    token = setup_data["access_token"]
    tenant_slug = setup_data["tenant"]["slug"]

    yield {
        "username": username,
        "password": password,
        "token": token,
        "tenant_slug": tenant_slug
    }

    # Teardown
    TenantManager.close_tenant(tenant_slug)
    db_path = TenantManager.get_db_path(tenant_slug)
    if db_path.exists():
        try:
            db_path.unlink()
        except Exception:
            pass

def test_user_management_lifecycle(client, test_setup_admin):
    admin_token = test_setup_admin["token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    cookies_admin = {"access_token": admin_token}

    # 1. List users (should have initial admin)
    res = client.get("/api/auth/users", headers=admin_headers, cookies=cookies_admin)
    assert res.status_code == 200
    users = res.json()
    assert len(users) >= 1
    admin_user = next(u for u in users if u["username"] == test_setup_admin["username"])
    assert admin_user["role"] == "admin"
    admin_id = admin_user["id"]

    # 2. Create Cashier user
    cashier_username = f"kasir_{uuid.uuid4().hex[:5]}"
    cashier_password = "passwordkasir"
    cashier_res = client.post("/api/auth/users", json={
        "username": cashier_username,
        "full_name": "Kasir Satu",
        "role": "cashier",
        "password": cashier_password,
        "is_active": True
    }, headers=admin_headers, cookies=cookies_admin)
    assert cashier_res.status_code == 200
    cashier_data = cashier_res.json()
    assert cashier_data["username"] == cashier_username
    assert cashier_data["role"] == "cashier"
    cashier_id = cashier_data["id"]

    # 3. Create second Admin user
    admin2_username = f"admin2_{uuid.uuid4().hex[:5]}"
    admin2_res = client.post("/api/auth/users", json={
        "username": admin2_username,
        "full_name": "Admin Dua",
        "role": "admin",
        "password": "passwordadmin2",
        "is_active": True
    }, headers=admin_headers, cookies=cookies_admin)
    assert admin2_res.status_code == 200
    admin2_id = admin2_res.json()["id"]

    # 4. Verify Cashier can immediately login via /api/auth/login
    cashier_login_res = client.post("/api/auth/login", json={
        "username": cashier_username,
        "password": cashier_password
    })
    assert cashier_login_res.status_code == 200
    cashier_login_data = cashier_login_res.json()
    assert cashier_login_data["user"]["role"] == "cashier"
    cashier_token = cashier_login_data["access_token"]
    cashier_headers = {"Authorization": f"Bearer {cashier_token}"}
    cookies_cashier = {"access_token": cashier_token}

    # 5. Cashier cannot access user management endpoint
    forbidden_res = client.get("/api/auth/users", headers=cashier_headers, cookies=cookies_cashier)
    assert forbidden_res.status_code == 403

    # 6. Cashier accessing backoffice page is redirected to /pos
    redirect_res = client.get("/backoffice/users", cookies=cookies_cashier, follow_redirects=False)
    assert redirect_res.status_code in [302, 307]
    assert redirect_res.headers["location"] == "/pos"

    # 7. Update cashier info
    update_res = client.put(f"/api/auth/users/{cashier_id}", json={
        "full_name": "Kasir Satu Terupdate",
        "role": "cashier",
        "is_active": True
    }, headers=admin_headers, cookies=cookies_admin)
    assert update_res.status_code == 200
    assert update_res.json()["full_name"] == "Kasir Satu Terupdate"

    # 8. Prevent admin from deleting their own account
    self_delete_res = client.delete(f"/api/auth/users/{admin_id}", headers=admin_headers, cookies=cookies_admin)
    assert self_delete_res.status_code == 400
    assert "tidak dapat menghapus akun Anda sendiri" in self_delete_res.json()["detail"]

    # 9. Delete cashier user
    del_cashier_res = client.delete(f"/api/auth/users/{cashier_id}", headers=admin_headers, cookies=cookies_admin)
    assert del_cashier_res.status_code == 200
    assert "berhasil dihapus" in del_cashier_res.json()["message"]

    # 10. Delete admin2 is allowed (since main admin is still active)
    del_admin2_res = client.delete(f"/api/auth/users/{admin2_id}", headers=admin_headers, cookies=cookies_admin)
    assert del_admin2_res.status_code == 200
