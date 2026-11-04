from datetime import datetime, timezone

from app.database import TenantManager
from app.modules.sales.models import SalesOrder


def test_current_user_reports_the_active_tenant_and_utc_timestamp(api_client, tenant_factory):
    tenant = tenant_factory()
    response = api_client.get("/api/auth/me", headers={"Authorization": f"Bearer {tenant['token']}"})
    assert response.status_code == 200
    user = response.json()
    assert user["has_tenant"] is True
    assert user["tenant_slug"] == tenant["slug"]
    assert datetime.fromisoformat(user["created_at"].replace("Z", "+00:00")).tzinfo is not None


def test_invoice_lookup_is_not_limited_to_the_latest_100_orders(api_client, tenant_factory):
    tenant = tenant_factory()
    with TenantManager.get_session(tenant["slug"]) as db:
        db.add_all([SalesOrder(invoice_number=f"LOOKUP-{number:04d}", created_at=datetime.now(timezone.utc)) for number in range(101)])
        db.commit()
    response = api_client.get("/api/sales/orders/by-invoice/LOOKUP-0000", headers={"Authorization": f"Bearer {tenant['token']}"})
    assert response.status_code == 200
    assert response.json()["invoice_number"] == "LOOKUP-0000"
