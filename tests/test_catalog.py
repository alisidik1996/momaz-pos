import pytest
from app.modules.catalog import service
from app.modules.catalog.schemas import ProductCreate, MatrixGenerateRequest

def test_create_product_and_matrix_variants(db_session):
    # 1. Create Product with discount price, custom SKU, barcode, and image
    prod_in = ProductCreate(
        name="Kemeja Flanel Casual",
        sku="KMT-FLN-MAIN",
        barcode="8991234567890",
        base_price=175000,
        discount_price=149000,
        image_url="/static/uploads/products/flanel.jpg",
        description="Bahan katun flanel tebal dan adem"
    )
    product = service.create_product(db_session, prod_in)
    assert product.id is not None
    assert product.name == "Kemeja Flanel Casual"
    assert product.sku == "KMT-FLN-MAIN"
    assert product.barcode == "8991234567890"
    assert product.base_price == 175000
    assert product.discount_price == 149000
    assert product.image_url == "/static/uploads/products/flanel.jpg"

    # 2. Generate Matrix Variants (3 colors x 4 sizes = 12 variants)
    matrix_req = MatrixGenerateRequest(
        product_id=product.id,
        colors=["Navy", "Hitam", "Maroon"],
        sizes=["S", "M", "L", "XL"],
        cost_price=95000,
        sell_price=175000,
        initial_stock=10,
        min_stock=3,
        sku_prefix="FLN"
    )
    variants = service.generate_product_matrix(db_session, matrix_req)
    assert len(variants) == 12

    # Verify attributes of generated variants
    for v in variants:
        assert v.product_id == product.id
        assert v.sell_price == 175000
        assert v.cost_price == 95000
        assert v.stock == 10
        assert v.barcode is not None
        assert v.sku.startswith("FLN-")

    # 3. Barcode scan lookup
    first_var = variants[0]
    scan_result = service.scan_barcode_lookup(db_session, first_var.barcode)
    assert scan_result.variant_id == first_var.id
    assert scan_result.product_name == "Kemeja Flanel Casual"
    assert scan_result.color == first_var.color
    assert scan_result.size == first_var.size

def test_bulk_import_and_export_csv(db_session):
    # 1. Test Template Generation
    template_str = service.generate_csv_template()
    assert "nama_produk" in template_str
    assert "harga_modal" in template_str
    assert "harga_jual" in template_str
    assert "Kemeja Flanel Slim Fit" in template_str

    # 2. Test Import CSV
    csv_content = """nama_produk,kategori,brand,deskripsi,sku,barcode,harga_modal,harga_jual,harga_diskon,stok,min_stok,foto_url
Jaket Bomber Pilot,Outerwear Pria,Alpha ID,Jaket pilot parasut anti angin,JKT-BMB-01,8993344556677,140000,285000,249000,25,2,
Celana Jeans Raw Denim,Bawahan & Celana,NBDN,Selvedge denim 14oz kaku,JNS-RAW-01,8994455667788,180000,350000,0,15,3,
"""
    result = service.import_products_from_csv(db_session, csv_content.encode("utf-8"))
    assert result["status"] == "success"
    assert result["rows_processed"] == 2
    assert result["products_created"] == 2
    assert len(result["errors"]) == 0

    # 3. Verify products and categories in DB
    prods = service.get_products(db_session)
    prod_names = [p.name for p in prods]
    assert "Jaket Bomber Pilot" in prod_names
    assert "Celana Jeans Raw Denim" in prod_names

    bomber = next(p for p in prods if p.name == "Jaket Bomber Pilot")
    assert bomber.discount_price == 249000
    assert bomber.category.name == "Outerwear Pria"
    assert bomber.brand.name == "Alpha ID"
    assert bomber.stock == 25
    assert bomber.cost_price == 140000
    assert bomber.total_stock == 25

    # 4. Test Export CSV
    exported_csv = service.export_products_to_csv(db_session)
    assert "Jaket Bomber Pilot" in exported_csv
    assert "Celana Jeans Raw Denim" in exported_csv
    assert "JKT-BMB-01" in exported_csv

def test_import_csv_with_semicolon_and_bom(db_session):
    # 1. Downloaded template with UTF-8 BOM re-imported
    template_str = service.generate_csv_template()
    encoded = template_str.encode("utf-8-sig")
    res1 = service.import_products_from_csv(db_session, encoded)
    assert res1["status"] == "success"
    assert res1["rows_processed"] == 2
    assert res1["products_created"] == 2

    # 2. Semicolon-delimited CSV (common in Indonesian Excel)
    semi_csv = b"""nama_produk;kategori;brand;harga_modal;harga_jual;stok;min_stok
Gamis Syari Momaz;Gamis;Momaz;120.000;225000;15;3
Mukena Silk Premium;Mukena;Momaz;150000;275.000,00;10;2
"""
    res2 = service.import_products_from_csv(db_session, semi_csv)
    assert res2["status"] == "success"
    assert res2["rows_processed"] == 2
    assert res2["products_created"] == 2

    gamis = db_session.query(service.Product).filter(service.Product.name == "Gamis Syari Momaz").first()
    assert gamis is not None
    assert gamis.cost_price == 120000.0
    assert gamis.base_price == 225000.0
    assert gamis.stock == 15

    # 3. Re-import updates existing product
    res3 = service.import_products_from_csv(db_session, semi_csv)
    assert res3["products_updated"] == 2
