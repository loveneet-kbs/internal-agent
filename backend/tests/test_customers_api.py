"""Route-level tests, including the auth behaviour that was broken before."""

from __future__ import annotations

import pytest


def test_health_reports_configuration(client):
    body = client.get("/api/health").json()
    assert body["success"] is True
    assert body["authConfigured"] is True


def test_list_and_fetch(client, seeded):
    body = client.get("/api/customers").json()
    assert body["total"] == 3

    one = client.get(f"/api/customers/{seeded[0]['id']}").json()
    assert one["data"]["email"] == "rahul@example.com"


def test_unknown_customer_is_404(client):
    assert client.get("/api/customers/9999").status_code == 404


@pytest.mark.parametrize("bad_id", ["0", "-3", "abc", "1.5"])
def test_non_positive_ids_rejected(client, bad_id):
    assert client.get(f"/api/customers/{bad_id}").status_code in (400, 422)


# --------------------------------------------------------------------------- #
# Auth - the regression that matters most
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "method,path,body",
    [
        ("post", "/api/customers", {"name": "A", "email": "a@example.com"}),
        ("put", "/api/customers/1", {"phone": "123"}),
        ("delete", "/api/customers/1", None),
        ("delete", "/api/tasks/1", None),
    ],
)
def test_mutating_routes_require_auth(client, method, path, body):
    response = getattr(client, method)(path, json=body) if body else getattr(client, method)(path)
    assert response.status_code == 401, f"{method.upper()} {path} was not protected"


def test_wrong_token_rejected(client):
    response = client.post(
        "/api/customers",
        json={"name": "A", "email": "a@example.com"},
        headers={"Authorization": "Bearer wrong"},
    )
    assert response.status_code == 401


def test_auth_fails_closed_when_unconfigured(client, monkeypatch):
    """With no ADMIN_TOKEN the route must refuse, not wave the caller through."""
    from app import security
    from dataclasses import replace

    monkeypatch.setattr(security, "settings", replace(security.settings, admin_token=""))
    response = client.post("/api/customers", json={"name": "A", "email": "a@example.com"})
    assert response.status_code == 503
    assert "ADMIN_TOKEN" in response.json()["error"]


# --------------------------------------------------------------------------- #
# Validation and mutation
# --------------------------------------------------------------------------- #
def test_create_then_reject_duplicate_email(client, admin):
    payload = {"name": "Ada", "email": "ada@example.com", "phone": "555"}
    assert client.post("/api/customers", json=payload, headers=admin).status_code == 201

    duplicate = client.post("/api/customers", json=payload, headers=admin)
    assert duplicate.status_code == 409
    assert "already exists" in duplicate.json()["error"]


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "", "email": "a@example.com"},
        {"name": "A", "email": "not-an-email"},
        {"name": "A", "email": "a@example.com", "role": "admin"},  # unknown field
        {"email": "a@example.com"},  # missing name
    ],
)
def test_create_rejects_bad_bodies(client, admin, payload):
    assert client.post("/api/customers", json=payload, headers=admin).status_code == 400


def test_partial_update(client, admin, seeded):
    target = seeded[0]["id"]
    response = client.put(
        f"/api/customers/{target}", json={"phone": "1112223333"}, headers=admin
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["phone"] == "1112223333"
    assert data["name"] == "Rahul Sharma"  # untouched


def test_empty_update_rejected(client, admin, seeded):
    response = client.put(f"/api/customers/{seeded[0]['id']}", json={}, headers=admin)
    assert response.status_code == 400


def test_delete_returns_the_removed_row(client, admin, seeded):
    target = seeded[0]["id"]
    response = client.delete(f"/api/customers/{target}", headers=admin)
    assert response.status_code == 200
    assert response.json()["data"]["id"] == target
    assert client.get(f"/api/customers/{target}").status_code == 404


def test_oversized_body_rejected(client, admin):
    response = client.post(
        "/api/customers",
        json={"name": "A" * 200_000, "email": "a@example.com"},
        headers=admin,
    )
    assert response.status_code == 413


def test_unknown_route_is_404(client):
    assert client.get("/api/nope").status_code == 404
