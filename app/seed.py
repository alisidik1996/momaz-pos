"""Initialize the multi-tenant schema without inserting sample accounts."""
from importlib import import_module
from typing import Optional

from app.database import MasterBase, TenantManager, master_engine, _get_master_unpooled_engine, is_postgres


def seed_database(tenant_slug: Optional[str] = None):
    for module in ("app.core.models", "app.modules.tenants.models", "app.modules.auth.models", "app.modules.catalog.models", "app.modules.inventory.models", "app.modules.customers.models", "app.modules.shifts.models", "app.modules.sales.models", "app.modules.returns.models"):
        import_module(module)
    MasterBase.metadata.create_all(bind=_get_master_unpooled_engine() if is_postgres else master_engine)
    if tenant_slug is not None:
        TenantManager.init_tenant_db(tenant_slug)


if __name__ == "__main__":
    seed_database()
    print("[OK] Master schema initialized. Ready for tenant registration and setup.")
