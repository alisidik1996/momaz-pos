import csv
import io

import pytest
from fastapi import HTTPException

from app.modules.catalog.models import Brand, Category, Product
from app.modules.catalog.schemas import MatrixGenerateRequest, ProductCreate
from app.modules.catalog.service import create_product, export_products_to_csv, generate_product_matrix, import_products_from_csv


def test_duplicate_product_sku_is_rejected(db_session):
    create_product(db_session, ProductCreate(name="First product", sku="DUPLICATE-SKU"))
    with pytest.raises(HTTPException) as error:
        create_product(db_session, ProductCreate(name="Other product", sku="DUPLICATE-SKU"))
    assert error.value.status_code == 400


def test_matrix_generation_deduplicates_repeated_sizes(db_session):
    product = create_product(db_session, ProductCreate(name="Repeated matrix"))
    variants = generate_product_matrix(db_session, MatrixGenerateRequest(product_id=product.id, sizes=["M", "M"], colors=["Blue"]))
    assert len(variants) == 1


def test_csv_bad_row_does_not_pollute_caches_or_success_counters(db_session):
    content = b"nama_produk,kategori,brand,harga_jual,stok\nBad product,New Category,New Brand,NaN,-1\nGood product,New Category,New Brand,10,2\n"
    result = import_products_from_csv(db_session, content)
    assert result["products_created"] == 1
    assert len(result["errors"]) == 1
    assert db_session.query(Product).one().name == "Good product"
    assert db_session.query(Category).count() == 1
    assert db_session.query(Brand).count() == 1


def test_csv_requires_a_product_name_header(db_session):
    with pytest.raises(HTTPException) as error:
        import_products_from_csv(db_session, b"unknown,stock\nnot-a-product,1\n")
    assert error.value.status_code == 400


def test_csv_export_neutralizes_spreadsheet_formulas(db_session):
    create_product(db_session, ProductCreate(name="=HYPERLINK(\"https://attacker.example\")", sku="FORMULA"))
    row = next(csv.DictReader(io.StringIO(export_products_to_csv(db_session))))
    assert row["nama_produk"].startswith("'=")


def test_product_creation_persists_member_and_affiliate_rules(db_session):
    product = create_product(db_session, ProductCreate(name="Member product", member_discount_value=10, affiliate_commission_value=5))
    assert product.member_discount_value == 10
    assert product.affiliate_commission_value == 5
