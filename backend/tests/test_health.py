from __future__ import annotations


def test_health_and_readiness_report_service_state(client):
    health = client.get("/api/healthz")
    readiness = client.get("/api/readyz")

    assert health.status_code == 200
    assert health.json() == {"status": "healthy"}
    assert readiness.status_code == 200
    assert readiness.json() == {
        "status": "ready",
        "checks": {"database": "ready"},
    }


def test_unauthenticated_request_gets_request_id_and_error_envelope(client):
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.headers.get("x-request-id")
    assert response.json()["error"]["code"] == "authentication_required"
    assert response.json()["error"]["request_id"] == response.headers["x-request-id"]
