import pytest

from app.modules.customers.schemas import CustomerCreate
from app.modules.customers.service import create_customer


def test_multiple_customers_can_have_no_phone_number(db_session):
    first = create_customer(db_session, CustomerCreate(name="First member", phone=""))
    second = create_customer(db_session, CustomerCreate(name="Second member", phone=""))
    assert first.id != second.id
    assert first.phone is None
    assert second.phone is None


def test_customer_lifecycle_and_lookup(api_client, tenant_factory):
    tenant = tenant_factory()
    headers = {"Authorization": f"Bearer {tenant['token']}"}
    created = api_client.post("/api/customers", json={"name": "Customer Review", "phone": "081234567890"}, headers=headers)
    assert created.status_code == 200
    customer = created.json()
    lookup = api_client.get(f"/api/customers/by-code/{customer['member_id']}", headers=headers)
    assert lookup.status_code == 200
    assert lookup.json()["id"] == customer["id"]
    update = api_client.put(f"/api/customers/{customer['id']}", json={"name": "Updated Customer"}, headers=headers)
    assert update.status_code == 200
    search = api_client.get("/api/customers?q=Updated", headers=headers)
    assert len(search.json()) == 1
    delete = api_client.delete(f"/api/customers/{customer['id']}", headers=headers)
    assert delete.status_code == 200
    missing = api_client.get(f"/api/customers/by-code/{customer['member_id']}", headers=headers)
    assert missing.status_code == 404


@pytest.mark.parametrize("name", [None, "", " " * 5])
def test_customer_name_cannot_be_cleared(api_client, tenant_factory, name):
    tenant = tenant_factory()
    headers = {"Authorization": f"Bearer {tenant['token']}"}
    customer = api_client.post("/api/customers", json={"name": "Named member"}, headers=headers).json()
    response = api_client.put(f"/api/customers/{customer['id']}", json={"name": name}, headers=headers)
    assert response.status_code == 422


def test_member_portal_lookup_commission(api_client, tenant_factory):
    tenant = tenant_factory()
    headers = {"Authorization": f"Bearer {tenant['token']}"}
    created = api_client.post(
        "/api/customers",
        json={"name": "Affiliate Member", "phone": "089988776655"},
        headers=headers
    ).json()
    member_id = created["member_id"]

    res = api_client.get(f"/api/customers/portal/lookup?code={member_id}")
    assert res.status_code == 200
    data = res.json()
    assert "member" in data
    assert data["member"]["name"] == "Affiliate Member"
    assert data["member"]["total_commission"] == 0.0
    assert "points" not in data["member"]
    assert "history" in data

    res_tenant = api_client.get(f"/api/customers/portal/lookup?code={member_id}&tenant={tenant['slug']}")
    assert res_tenant.status_code == 200

    res_404 = api_client.get("/api/customers/portal/lookup?code=NONEXISTENT123")
    assert res_404.status_code == 404

