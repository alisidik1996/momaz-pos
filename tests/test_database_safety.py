from concurrent.futures import ThreadPoolExecutor
import time
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect, text

from app import database
from app.database import TenantManager
from app.modules.catalog.models import Product, ProductVariant


@pytest.mark.parametrize("slug", ["../master", "../../outside", "/absolute", "foo/bar", "foo\\bar", "", "a" * 101])
def test_tenant_paths_reject_unsafe_slugs(slug):
    with pytest.raises(ValueError):
        TenantManager.get_db_path(slug)


def test_failed_initialization_is_not_published_in_engine_cache(monkeypatch):
    slug = f"failed-init-{uuid4().hex[:12]}"

    def fail_migrations(*args, **kwargs):
        raise RuntimeError("Simulated migration failure")

    monkeypatch.setattr(TenantManager, "_run_migrations", fail_migrations)
    try:
        with pytest.raises(RuntimeError):
            TenantManager.get_engine(slug)
        assert slug not in TenantManager._engines
        assert slug not in TenantManager._sessionmakers
    finally:
        TenantManager.close_tenant(slug)


def test_parallel_engine_initialization_creates_one_engine(monkeypatch):
    slug = f"engine-race-{uuid4().hex[:12]}"
    real_create_engine = database.create_engine
    created = []

    def delayed_create_engine(*args, **kwargs):
        time.sleep(0.05)
        engine = real_create_engine(*args, **kwargs)
        created.append(engine)
        return engine

    monkeypatch.setattr(database, "create_engine", delayed_create_engine)
    try:
        with ThreadPoolExecutor(max_workers=2) as workers:
            engines = list(workers.map(lambda _: TenantManager.get_engine(slug), [1, 2]))
        assert len(created) == 1
        assert engines[0] is engines[1]
    finally:
        TenantManager.close_tenant(slug)
        for engine in created:
            engine.dispose()


def test_reopening_tenant_does_not_overwrite_existing_product_stock():
    slug = f"reopen-{uuid4().hex[:12]}"
    TenantManager.init_tenant_db(slug)
    try:
        with TenantManager.get_session(slug) as db:
            product = Product(name="Independent stock", stock=8, cost_price=17)
            db.add(product)
            db.flush()
            db.add(ProductVariant(product_id=product.id, sku="VAR-REOPEN", barcode="123", color="Blue", size="M", stock=5, cost_price=9))
            db.commit()
            product_id = product.id
        TenantManager.close_tenant(slug)
        with TenantManager.get_session(slug) as db:
            product = db.get(Product, product_id)
            assert product.stock == 8
            assert product.cost_price == 17
    finally:
        TenantManager.close_tenant(slug)


def test_legacy_table_rebuild_preserves_foreign_keys(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE products (id INTEGER PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE sales_orders (id INTEGER PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE product_variants (id INTEGER PRIMARY KEY, product_id INTEGER, stock INTEGER, cost_price FLOAT)"))
        conn.execute(text("""
            CREATE TABLE sales_order_items (
                id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES sales_orders(id) ON DELETE CASCADE,
                product_id INTEGER REFERENCES products(id) ON DELETE SET NULL,
                variant_id INTEGER REFERENCES product_variants(id) ON DELETE SET NULL,
                product_name VARCHAR(150) NOT NULL, variant_info VARCHAR(100) NOT NULL,
                sku VARCHAR(50) NOT NULL, barcode VARCHAR(50) NOT NULL,
                cost_price FLOAT, unit_price FLOAT, quantity INTEGER, discount_amount FLOAT, subtotal FLOAT
            )
        """))
    try:
        TenantManager._run_migrations(engine)
        foreign_keys = {tuple(key["constrained_columns"]) for key in inspect(engine).get_foreign_keys("sales_order_items")}
        assert {("order_id",), ("product_id",), ("variant_id",)} <= foreign_keys
    finally:
        engine.dispose()


@pytest.mark.parametrize("slug", ["café-store", "legacy-" + "a" * 90])
def test_existing_safe_legacy_slugs_remain_accessible(slug):
    assert TenantManager.get_db_path(slug).name == f"{slug}.db"
