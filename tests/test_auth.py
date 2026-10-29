from sqlalchemy import select


def test_shop_data_requires_sign_in(anon):
    health = anon.get("/api/health")
    assert health.status_code == 200

    blocked = anon.get("/api/dashboard")
    assert blocked.status_code == 401
    assert "Elena" not in blocked.text

    missing_header = anon.post("/api/login", json={"username": "admin", "password": "test-admin-password"})
    assert missing_header.status_code == 403


def test_login_and_logout(anon):
    anon.headers["X-Kinney-Request"] = "1"
    unknown = anon.post("/api/login", json={"username": "admin", "password": "not-the-password"})
    assert unknown.status_code == 401
    assert unknown.json()["detail"] == "Those credentials were not recognized."

    missing = anon.post("/api/login", json={"username": "nobody", "password": "not-the-password"})
    assert missing.status_code == 401
    assert missing.json()["detail"] == unknown.json()["detail"]

    signed = anon.post("/api/login", json={"username": "Admin", "password": "test-admin-password"})
    assert signed.status_code == 200
    body = signed.json()
    assert body["username"] == "admin"
    assert body["role"] == "admin"
    assert "password" not in body
    assert anon.get("/api/me").json()["display_name"] == "Administrator"
    assert anon.post("/api/logout").status_code == 204
    assert anon.get("/api/dashboard").status_code == 401


def test_passwords_are_stored_hashed(fresh_database):
    from app.database import SessionLocal
    from app.models import User

    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.username == "admin"))
        assert user is not None
        assert user.password_hash.startswith("scrypt$")
        assert "test-admin-password" not in user.password_hash
    finally:
        db.close()


def test_shop_user_cannot_administer(anon):
    anon.headers["X-Kinney-Request"] = "1"
    signed = anon.post("/api/login", json={"username": "ron", "password": "test-shop-password"})
    assert signed.status_code == 200
    assert signed.json()["role"] == "shop"
    assert anon.get("/api/admin/users").status_code == 403
    assert anon.get("/api/records").status_code == 200


def test_administrator_manages_accounts(client, anon):
    created = client.post(
        "/api/admin/users",
        json={
            "username": "dispatch",
            "display_name": "Dispatch Desk",
            "password": "dispatch-pass-1",
            "role": "shop",
        },
    )
    assert created.status_code == 201
    assert "password" not in created.json()
    user_id = created.json()["id"]

    duplicate = client.post(
        "/api/admin/users",
        json={
            "username": "dispatch",
            "display_name": "Again",
            "password": "dispatch-pass-1",
            "role": "shop",
        },
    )
    assert duplicate.status_code == 409

    short = client.post(
        "/api/admin/users",
        json={"username": "shorty", "display_name": "Short", "password": "no", "role": "shop"},
    )
    assert short.status_code == 422

    same = client.post(
        "/api/admin/users",
        json={"username": "pilot", "display_name": "Pilot Desk", "password": "pilot", "role": "shop"},
    )
    assert same.status_code == 201

    anon.headers["X-Kinney-Request"] = "1"
    assert anon.post("/api/login", json={"username": "dispatch", "password": "dispatch-pass-1"}).status_code == 200

    reset = client.patch(f"/api/admin/users/{user_id}", json={"password": "dispatch-pass-2"})
    assert reset.status_code == 200
    assert anon.get("/api/me").status_code == 401
    assert anon.post("/api/login", json={"username": "dispatch", "password": "dispatch-pass-1"}).status_code == 401
    assert anon.post("/api/login", json={"username": "dispatch", "password": "dispatch-pass-2"}).status_code == 200

    deactivated = client.patch(f"/api/admin/users/{user_id}", json={"active": False})
    assert deactivated.status_code == 200
    assert anon.get("/api/me").status_code == 401
    assert anon.post("/api/login", json={"username": "dispatch", "password": "dispatch-pass-2"}).status_code == 401


def test_last_administrator_stays(client):
    admin_id = client.get("/api/me").json()["id"]
    assert client.patch(f"/api/admin/users/{admin_id}", json={"active": False}).status_code == 409
    assert client.patch(f"/api/admin/users/{admin_id}", json={"role": "shop"}).status_code == 409
    assert client.get("/api/me").json()["role"] == "admin"


def test_password_change_replaces_the_session(client, anon):
    changed = client.post(
        "/api/account/password",
        json={"current_password": "test-admin-password", "new_password": "replacement-pass"},
    )
    assert changed.status_code == 200
    assert client.get("/api/me").status_code == 401
    anon.headers["X-Kinney-Request"] = "1"
    assert anon.post("/api/login", json={"username": "admin", "password": "test-admin-password"}).status_code == 401
    signed = anon.post("/api/login", json={"username": "admin", "password": "replacement-pass"})
    assert signed.status_code == 200


def test_mutation_without_the_request_header_is_rejected(client):
    response = client.post("/api/customers", json={"name": "Nope"}, headers={"X-Kinney-Request": ""})
    assert response.status_code == 403


def test_sign_in_locks_after_repeated_failures(anon):
    anon.headers["X-Kinney-Request"] = "1"
    for _ in range(10):
        failed = anon.post("/api/login", json={"username": "admin", "password": "wrong-password-1"})
        assert failed.status_code == 401
    blocked = anon.post("/api/login", json={"username": "admin", "password": "test-admin-password"})
    assert blocked.status_code == 429
