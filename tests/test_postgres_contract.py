from contextlib import contextmanager
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app import database
from app.database import Base, MasterSessionLocal, TenantManager
from app.modules.catalog.models import Product
from app.modules.tenants.models import Tenant


def test_postgres_orm_and_ddl_use_the_same_explicit_tenant_schema(monkeypatch):
    slug = f"sql-contract-{uuid4().hex[:8]}"
    expected_schema = TenantManager.schema_name(slug)
    emitted = []

    class Connection:
        options = {"schema_translate_map": {None: "public"}}

        def execute(self, statement):
            emitted.append(str(statement))

        def execution_options(self, **options):
            self.options = options
            return self

        def get_execution_options(self):
            return self.options

    class DdlEngine:
        @contextmanager
        def begin(self):
            yield Connection()

    real_create_engine = create_engine
    monkeypatch.setattr(database, "is_postgres", True)
    monkeypatch.setattr(database, "_get_master_unpooled_engine", lambda: DdlEngine())
    monkeypatch.setattr(database, "create_engine", lambda *args, **kwargs: real_create_engine("sqlite:///:memory:"))
    monkeypatch.setattr(TenantManager, "_run_migrations", lambda bind: None)
    monkeypatch.setattr(TenantManager, "_check_schema_collision", lambda slug: None)

    def create_tables(bind):
        schema_map = bind.get_execution_options()["schema_translate_map"]
        assert schema_map[None] == expected_schema
        emitted.append(str(CreateTable(Product.__table__).compile(dialect=postgresql.dialect(), schema_translate_map=schema_map, render_schema_translate=True)))

    monkeypatch.setattr(Base.metadata, "create_all", create_tables)
    try:
        engine = TenantManager.get_engine(slug)
        schema_map = engine.get_execution_options()["schema_translate_map"]
        query = str(select(Product).compile(dialect=postgresql.dialect(), schema_translate_map=schema_map, render_schema_translate=True))
        assert f"{expected_schema}.products" in query
        assert any(f"CREATE TABLE {expected_schema}.products" in sql for sql in emitted)
        assert all("SET search_path" not in sql for sql in emitted)
    finally:
        TenantManager.close_tenant(slug)


def test_legacy_postgres_schema_aliases_cannot_share_data(api_client):
    suffix = uuid4().hex[:8]
    slug = f"alias-{suffix}"
    with MasterSessionLocal() as db:
        db.add_all([Tenant(name="First", slug=slug), Tenant(name="Second", slug=f"alias_{suffix}")])
        db.commit()
    with pytest.raises(HTTPException) as error:
        TenantManager._check_schema_collision(slug)
    assert error.value.status_code == 409
