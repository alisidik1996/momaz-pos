import io
import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import TenantManager, MasterBase, master_engine

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c

@pytest.fixture(scope="module")
def test_setup_admin(client):
    # Unique suffix to avoid clashes across test runs
    uid = uuid.uuid4().hex[:6]
    username = f"admin_{uid}"
    password = "password123"
    store_name = f"Test Store {uid}"

    # 1. Register Admin
    reg_res = client.post("/api/tenants/register-admin", json={
        "username": username,
        "password": password,
        "full_name": f"Admin User {uid}"
    })
    assert reg_res.status_code == 200

    # 2. Login (has_tenant should be False)
    login_res = client.post("/api/auth/login", json={
        "username": username,
        "password": password
    })
    assert login_res.status_code == 200
    login_data = login_res.json()
    assert login_data["has_tenant"] is False
    token_pre = login_data["access_token"]

    # 3. Complete Setup Wizard
    setup_payload = {
        "store_name": store_name,
        "tagline": "Toko Pakaian Terlengkap",
        "address": "Jl. Merdeka No. 45",
        "phone": "08123456789",
        "return_policy_days": 7,
        "tax_rate": 11,
        "is_tax_enabled": False,
        "categories": ["Kaos Pria", "Kemeja", "Celana Chino"],
        "brands": ["Erigo", "Roughneck"]
    }
    setup_res = client.post(
        "/api/tenants/setup",
        json=setup_payload,
        headers={"Authorization": f"Bearer {token_pre}"}
    )
    assert setup_res.status_code == 200
    setup_data = setup_res.json()
    assert setup_data["status"] == "success"
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

def test_page_redirects_unauthenticated(client):
    # Unauthenticated user visiting /pos is redirected to /login
    pos_res = client.get("/pos", follow_redirects=False)
    assert pos_res.status_code in [302, 307]
    assert "/login" in pos_res.headers["location"]

    # Unauthenticated user visiting /setup is redirected to /login
    setup_res = client.get("/setup", follow_redirects=False)
    assert setup_res.status_code in [302, 307]
    assert "/login" in setup_res.headers["location"]

    # Login page loads successfully
    login_res = client.get("/login")
    assert login_res.status_code == 200
    assert "MOMAZ POS" in login_res.text

def test_catalog_category_and_brand_endpoints(client, test_setup_admin):
    headers = {"Authorization": f"Bearer {test_setup_admin['token']}"}

    # 1. Categories created during setup exist
    cats_res = client.get("/api/catalog/categories", headers=headers)
    assert cats_res.status_code == 200
    cat_names = [c["name"] for c in cats_res.json()]
    assert "Kaos Pria" in cat_names
    assert "Celana Chino" in cat_names

    # 2. Add a new category
    add_cat_res = client.post("/api/catalog/categories", json={"name": "Jaket Bomber"}, headers=headers)
    assert add_cat_res.status_code == 200
    new_cat = add_cat_res.json()
    assert new_cat["name"] == "Jaket Bomber"

    # 3. Brands created during setup exist
    brands_res = client.get("/api/catalog/brands", headers=headers)
    assert brands_res.status_code == 200
    brand_names = [b["name"] for b in brands_res.json()]
    assert "Erigo" in brand_names

    # 4. Add a new brand
    add_brand_res = client.post("/api/catalog/brands", json={"name": "Hammerstout"}, headers=headers)
    assert add_brand_res.status_code == 200
    new_brand = add_brand_res.json()
    assert new_brand["name"] == "Hammerstout"

    # 5. Delete newly created brand and category
    del_brand = client.delete(f"/api/catalog/brands/{new_brand['id']}", headers=headers)
    assert del_brand.status_code == 200
    del_cat = client.delete(f"/api/catalog/categories/{new_cat['id']}", headers=headers)
    assert del_cat.status_code == 200

def test_product_image_upload(client, test_setup_admin):
    headers = {"Authorization": f"Bearer {test_setup_admin['token']}"}

    # Upload mock image file
    file_content = b"fake-image-bytes-jpeg"
    file_obj = io.BytesIO(file_content)
    files = {"file": ("test_tshirt.jpg", file_obj, "image/jpeg")}

    res = client.post("/api/catalog/upload-image", files=files, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "image_url" in data
    assert data["image_url"].startswith("/static/uploads/products/")

def test_product_with_discount_sku_barcode_and_matrix(client, test_setup_admin):
    headers = {"Authorization": f"Bearer {test_setup_admin['token']}"}

    # 1. Create Product with discount price, SKU, barcode, and photo
    prod_payload = {
        "name": "Kemeja Oxford Striped",
        "sku": "OXF-STRP-01",
        "barcode": "8992345678901",
        "base_price": 220000,
        "discount_price": 185000,
        "image_url": "/static/uploads/products/mock_shirt.jpg",
        "description": "Kemeja katun premium bergaris casual"
    }
    prod_res = client.post("/api/catalog/products", json=prod_payload, headers=headers)
    assert prod_res.status_code == 200
    prod = prod_res.json()
    assert prod["id"] is not None
    assert prod["sku"] == "OXF-STRP-01"
    assert prod["barcode"] == "8992345678901"
    assert prod["base_price"] == 220000
    assert prod["discount_price"] == 185000
    assert prod["image_url"] == "/static/uploads/products/mock_shirt.jpg"

    # 2. Generate matrix variants (2 colors x 3 sizes = 6 variants)
    matrix_payload = {
        "product_id": prod["id"],
        "colors": ["Biru Muda", "Putih"],
        "sizes": ["M", "L", "XL"],
        "cost_price": 110000,
        "sell_price": 220000,
        "initial_stock": 15,
        "sku_prefix": "OXF"
    }
    matrix_res = client.post("/api/catalog/matrix/generate", json=matrix_payload, headers=headers)
    assert matrix_res.status_code == 200
    variants = matrix_res.json()
    assert len(variants) == 6

    # 3. Query product list and verify attributes & variants count
    list_res = client.get("/api/catalog/products", headers=headers)
    assert list_res.status_code == 200
    products = list_res.json()
    found = next((p for p in products if p["id"] == prod["id"]), None)
    assert found is not None
    assert found["discount_price"] == 185000
    assert len(found["variants"]) == 6

def test_import_and_export_csv_endpoints(client, test_setup_admin):
    headers = {"Authorization": f"Bearer {test_setup_admin['token']}"}

    # 1. Download CSV template
    tmpl_res = client.get("/api/catalog/import-template", headers=headers)
    assert tmpl_res.status_code == 200
    assert "text/csv" in tmpl_res.headers["content-type"]
    assert "nama_produk" in tmpl_res.text

    # 2. Upload CSV for bulk import
    csv_bytes = b"""nama_produk,kategori,brand,deskripsi,sku,barcode,harga_modal,harga_jual,harga_diskon,stok,min_stok,foto_url
Kaos Oversize Street,Atasan Distro,Streetwear ID,Kaos tebal street style,KOS-OVR-01,8998877665544,55000,120000,99000,30,3,
"""
    files = {"file": ("products.csv", io.BytesIO(csv_bytes), "text/csv")}
    import_res = client.post("/api/catalog/import-csv", files=files, headers=headers)
    assert import_res.status_code == 200
    data = import_res.json()
    assert data["status"] == "success"
    assert data["products_created"] >= 1

    # 3. Export CSV
    export_res = client.get("/api/catalog/export-csv", headers=headers)
    assert export_res.status_code == 200
    assert "Kaos Oversize Street" in export_res.text
    assert "Streetwear ID" in export_res.text
    assert "KOS-OVR-01" in export_res.text

def test_update_product_and_variant_and_restock(client, test_setup_admin):
    headers = {"Authorization": f"Bearer {test_setup_admin['token']}"}

    # 1. Create Product
    create_res = client.post("/api/catalog/products", json={
        "name": "Hoodie Fleece Basic",
        "sku": "HOD-FLC-00",
        "barcode": "8995566778899",
        "base_price": 250000,
        "discount_price": 220000,
        "description": "Bahan katun fleece lembut"
    }, headers=headers)
    assert create_res.status_code == 200
    prod = create_res.json()
    prod_id = prod["id"]

    # 2. Update Product (Edit Nama, Harga Promo, dsb)
    update_res = client.put(f"/api/catalog/products/{prod_id}", json={
        "name": "Hoodie Fleece Premium Reborn",
        "base_price": 275000,
        "discount_price": 235000,
        "description": "Bahan katun fleece tebal premium 330gsm"
    }, headers=headers)
    assert update_res.status_code == 200
    updated_prod = update_res.json()
    assert updated_prod["name"] == "Hoodie Fleece Premium Reborn"
    assert updated_prod["base_price"] == 275000
    assert updated_prod["discount_price"] == 235000
    assert "330gsm" in updated_prod["description"]

    # 3. Create a Variant for the product
    var_res = client.post("/api/catalog/variants", json={
        "product_id": prod_id,
        "color": "Abu Misty",
        "size": "L",
        "sell_price": 275000,
        "cost_price": 140000,
        "stock": 10,
        "min_stock": 4
    }, headers=headers)
    assert var_res.status_code == 200
    var = var_res.json()
    var_id = var["id"]
    assert var["stock"] == 10

    # 4. Update Variant (Edit Warna/Ukuran/Harga)
    update_var_res = client.put(f"/api/catalog/variants/{var_id}", json={
        "color": "Abu Misty Tua",
        "size": "XL",
        "sell_price": 285000,
        "cost_price": 145000,
        "min_stock": 5
    }, headers=headers)
    assert update_var_res.status_code == 200
    updated_var = update_var_res.json()
    assert updated_var["color"] == "Abu Misty Tua"
    assert updated_var["size"] == "XL"
    assert updated_var["sell_price"] == 285000
    assert updated_var["cost_price"] == 145000
    assert updated_var["min_stock"] == 5

    # 5. Restock / Tambah Stok (+20 pcs) via /api/inventory/stock-in
    stockin_res = client.post("/api/inventory/stock-in", json={
        "supplier_name": "Konveksi Bandung Maju",
        "invoice_ref": "INV-RESTOCK-2026-001",
        "note": "Penerimaan restock pakaian musim gugur",
        "items": [
            {
                "variant_id": var_id,
                "quantity": 20,
                "cost_price": 145000
            }
        ]
    }, headers=headers)
    assert stockin_res.status_code == 200
    assert "Berhasil menambah stok" in stockin_res.json()["message"]

    # 6. Verify variant stock increased to 10 + 20 = 30
    check_prod_res = client.get(f"/api/catalog/products/{prod_id}", headers=headers)
    assert check_prod_res.status_code == 200
    check_prod = check_prod_res.json()
    assert check_prod["total_stock"] == 30
    v_found = next(v for v in check_prod["variants"] if v["id"] == var_id)
    assert v_found["stock"] == 30

    # 7. Verify stock movements log
    mov_res = client.get(f"/api/inventory/movements?variant_id={var_id}", headers=headers)
    assert mov_res.status_code == 200
    movements = mov_res.json()
    assert len(movements) >= 1
    restock_mov = movements[0]
    assert restock_mov["movement_type"] == "restock"
    assert restock_mov["change_qty"] == 20
    assert restock_mov["current_stock"] == 30
    assert restock_mov["reference"] == "INV-RESTOCK-2026-001"


