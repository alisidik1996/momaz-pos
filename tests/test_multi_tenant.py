import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import TenantManager

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c

def test_admin_registration_and_validation(client):
    uid = uuid.uuid4().hex[:6]
    username = f"admin_reg_{uid}"
    
    # 1. Successful Admin Registration
    reg_res = client.post("/api/tenants/register-admin", json={
        "username": username,
        "password": "secretpassword",
        "full_name": "Test Administrator"
    })
    assert reg_res.status_code == 200
    reg_data = reg_res.json()
    assert reg_data["username"] == username
    assert reg_data["role"] == "admin"
    assert reg_data["tenant_id"] is None

    # 2. Duplicate Username Rejection
    dup_res = client.post("/api/tenants/register-admin", json={
        "username": username,
        "password": "secretpassword",
        "full_name": "Another Admin"
    })
    assert dup_res.status_code == 400
    assert "sudah terdaftar" in dup_res.json()["detail"]

def test_multi_tenant_setup_lifecycle(client):
    uid = uuid.uuid4().hex[:6]
    username = f"admin_life_{uid}"
    password = "secretpassword"

    # 1. Register admin
    client.post("/api/tenants/register-admin", json={
        "username": username,
        "password": password,
        "full_name": "Admin Lifecycle"
    })

    # 2. Login - should return has_tenant = False
    login_res = client.post("/api/auth/login", json={
        "username": username,
        "password": password
    })
    assert login_res.status_code == 200
    login_data = login_res.json()
    assert login_data["has_tenant"] is False
    assert login_data["tenant_slug"] is None
    pre_token = login_data["access_token"]

    # 3. Setup Wizard initializes tenant database
    setup_res = client.post(
        "/api/tenants/setup",
        json={
            "store_name": f"Distro Apparel {uid}",
            "slug": f"distro-{uid}",
            "tagline": "Premium Cotton Only",
            "address": "Jl. Riau No. 12, Bandung",
            "phone": "0812-9988-7766",
            "return_policy_days": 14,
            "categories": ["Kaos Oversize", "Celana Cargo"],
            "brands": ["Distro ID"]
        },
        headers={"Authorization": f"Bearer {pre_token}"}
    )
    assert setup_res.status_code == 200
    setup_data = setup_res.json()
    assert setup_data["status"] == "success"
    tenant_slug = setup_data["tenant"]["slug"]
    post_token = setup_data["access_token"]

    # Tenant DB file must physically exist
    tenant_db_path = TenantManager.get_db_path(tenant_slug)
    assert tenant_db_path.exists()

    # 4. Cannot setup again for the same admin
    re_setup = client.post(
        "/api/tenants/setup",
        json={"store_name": "Attempt Two Store"},
        headers={"Authorization": f"Bearer {post_token}"}
    )
    assert re_setup.status_code == 400
    assert "sudah memiliki toko aktif" in re_setup.json()["detail"]

    # 5. Subsequent Login - now has_tenant = True and tenant_slug is populated
    login_again = client.post("/api/auth/login", json={
        "username": username,
        "password": password
    })
    assert login_again.status_code == 200
    again_data = login_again.json()
    assert again_data["has_tenant"] is True
    assert again_data["tenant_slug"] == tenant_slug

    # Cleanup
    TenantManager.close_tenant(tenant_slug)
    if tenant_db_path.exists():
        try:
            tenant_db_path.unlink()
        except Exception:
            pass

def test_tenant_data_isolation(client):
    # Setup Tenant A
    uid_a = uuid.uuid4().hex[:6]
    admin_a = f"admin_a_{uid_a}"
    client.post("/api/tenants/register-admin", json={"username": admin_a, "password": "pass", "full_name": "Admin A"})
    login_a = client.post("/api/auth/login", json={"username": admin_a, "password": "pass"}).json()
    setup_a = client.post("/api/tenants/setup", json={
        "store_name": f"Boutique A {uid_a}",
        "categories": ["Dress Wanita", "Rok"],
        "brands": ["ZARA Test"]
    }, headers={"Authorization": f"Bearer {login_a['access_token']}"}).json()
    token_a = setup_a["access_token"]
    slug_a = setup_a["tenant"]["slug"]

    # Setup Tenant B
    uid_b = uuid.uuid4().hex[:6]
    admin_b = f"admin_b_{uid_b}"
    client.post("/api/tenants/register-admin", json={"username": admin_b, "password": "pass", "full_name": "Admin B"})
    login_b = client.post("/api/auth/login", json={"username": admin_b, "password": "pass"}).json()
    setup_b = client.post("/api/tenants/setup", json={
        "store_name": f"Sneaker Store B {uid_b}",
        "categories": ["Sepatu Pria", "Kaos Kaki"],
        "brands": ["NIKE Test"]
    }, headers={"Authorization": f"Bearer {login_b['access_token']}"}).json()
    token_b = setup_b["access_token"]
    slug_b = setup_b["tenant"]["slug"]

    # 1. Verify separate database files exist
    assert TenantManager.get_db_path(slug_a).exists()
    assert TenantManager.get_db_path(slug_b).exists()

    # 2. Add product into Tenant A
    prod_a_res = client.post("/api/catalog/products", json={
        "name": "Floral Summer Dress",
        "sku": "DRS-FLR-01",
        "base_price": 275000,
        "discount_price": 249000
    }, headers={"Authorization": f"Bearer {token_a}"})
    assert prod_a_res.status_code == 200

    # 3. Add product into Tenant B
    prod_b_res = client.post("/api/catalog/products", json={
        "name": "Running Air Sneakers",
        "sku": "SNK-AIR-99",
        "base_price": 650000
    }, headers={"Authorization": f"Bearer {token_b}"})
    assert prod_b_res.status_code == 200

    # 4. Verify Tenant A only sees Dress and Categories of Tenant A
    list_a = client.get("/api/catalog/products", headers={"Authorization": f"Bearer {token_a}"}).json()
    cats_a = client.get("/api/catalog/categories", headers={"Authorization": f"Bearer {token_a}"}).json()
    prod_names_a = [p["name"] for p in list_a]
    cat_names_a = [c["name"] for c in cats_a]

    assert "Floral Summer Dress" in prod_names_a
    assert "Running Air Sneakers" not in prod_names_a
    assert "Dress Wanita" in cat_names_a
    assert "Sepatu Pria" not in cat_names_a

    # 5. Verify Tenant B only sees Sneakers and Categories of Tenant B
    list_b = client.get("/api/catalog/products", headers={"Authorization": f"Bearer {token_b}"}).json()
    cats_b = client.get("/api/catalog/categories", headers={"Authorization": f"Bearer {token_b}"}).json()
    prod_names_b = [p["name"] for p in list_b]
    cat_names_b = [c["name"] for c in cats_b]

    assert "Running Air Sneakers" in prod_names_b
    assert "Floral Summer Dress" not in prod_names_b
    assert "Sepatu Pria" in cat_names_b
    assert "Dress Wanita" not in cat_names_b

    # Cleanup
    TenantManager.close_tenant(slug_a)
    TenantManager.close_tenant(slug_b)
    for slug in [slug_a, slug_b]:
        p = TenantManager.get_db_path(slug)
        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass
