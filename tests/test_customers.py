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
