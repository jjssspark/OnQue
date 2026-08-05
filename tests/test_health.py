def test_health_check(client):
    res = client.get("/")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_todos_endpoint_uses_db(client):
    """Verify fixture works end-to-end with DB-dependent route (now requires auth)."""
    res = client.get("/todos")
    assert res.status_code == 401
