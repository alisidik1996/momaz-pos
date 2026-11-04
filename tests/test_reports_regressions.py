import pytest

from app.core.cache import clear_cache


@pytest.mark.parametrize("query", ["start_date=invalid", "end_date=2026-99-01"])
def test_invalid_report_dates_return_validation_errors(api_client, tenant_factory, query):
    tenant = tenant_factory()
    response = api_client.get(f"/api/reports/sales?{query}", headers={"Authorization": f"Bearer {tenant['token']}"})
    assert response.status_code == 422


@pytest.mark.parametrize("payload", [{"id": 99}, {"tax_rate": -1}, {"return_policy_days": -1}, {"tax_rate": 101}])
def test_settings_only_accept_valid_public_fields(api_client, tenant_factory, payload):
    tenant = tenant_factory()
    response = api_client.put("/api/settings", json=payload, headers={"Authorization": f"Bearer {tenant['token']}"})
    assert response.status_code == 422


def test_store_name_change_invalidates_page_context_cache(api_client, tenant_factory):
    tenant = tenant_factory()
    headers = {"Authorization": f"Bearer {tenant['token']}"}
    clear_cache()
    assert api_client.get("/backoffice/dashboard", headers=headers).status_code == 200
    update = api_client.put("/api/settings", json={"store_name": "Renamed Review Store"}, headers=headers)
    assert update.status_code == 200
    page = api_client.get("/backoffice/dashboard", headers=headers)
    assert "Renamed Review Store" in page.text
