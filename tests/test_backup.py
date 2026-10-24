def _names(client):
    return {row["name"] for row in client.get("/api/customers").json()}


def test_shop_and_anonymous_cannot_export_or_import(anon):
    assert anon.get("/api/admin/export").status_code == 401
    assert anon.post("/api/admin/import", json={"format": "kinney-aviation-backup"}).status_code == 403

    anon.headers["X-Kinney-Request"] = "1"
    assert anon.post("/api/admin/import", json={"format": "kinney-aviation-backup"}).status_code == 401
    signed = anon.post("/api/login", json={"username": "ron", "password": "test-shop-password"})
    assert signed.status_code == 200
    assert anon.get("/api/admin/export").status_code == 403
    assert anon.post("/api/admin/import", json={}).status_code == 403


def test_export_contains_the_shop_and_password_hashes(client):
    response = client.get("/api/admin/export")
    assert response.status_code == 200
    assert "kinney-aviation-backup.json" in response.headers["content-disposition"]
    body = response.json()
    assert body["format"] == "kinney-aviation-backup"
    assert body["version"] == 1
    assert "N5183K" in {row["registration"] for row in body["aircraft"]}
    assert any(row["title"] == "Continue the annual at Flagstaff" for row in body["schedule"])
    assert any(row["password_hash"].startswith("scrypt$") for row in body["users"])
    assert "auth_sessions" not in body
    assert "test-admin-password" not in response.text
    assert "test-shop-password" not in response.text


def test_import_replaces_the_shop_and_keeps_the_session(client):
    exported = client.get("/api/admin/export").json()
    for owner in exported["customers"]:
        if owner["name"] == "Elena Vasquez":
            owner["name"] = "Imported Owner"
    for entry in exported["schedule"]:
        if entry["title"] == "Continue the annual at Flagstaff":
            entry["title"] = "Imported visit"

    result = client.post("/api/admin/import", json=exported)
    assert result.status_code == 200, result.text
    summary = result.json()
    assert summary["message"] == "Shop data replaced."
    assert summary["customers"] == len(exported["customers"])
    assert summary["role"] == "admin"
    assert "password_hash" not in result.text
    assert "scrypt$" not in result.text

    assert client.get("/api/me").json()["username"] == "admin"
    assert "Imported Owner" in _names(client)
    assert "Elena Vasquez" not in _names(client)

    invoices = {row["number"]: row for row in client.get("/api/invoices").json()}
    assert invoices["INV-2026-001"]["total_cents"] == 186200
    assert invoices["INV-2026-001"]["status"] == "paid"
    assert invoices["INV-2026-002"]["balance_cents"] == 13350

    calendar = client.get("/api/calendar?start=2026-10-01&end=2026-10-31").json()
    assert any(item["title"] == "Imported visit" for item in calendar["items"])
    assert client.get("/api/shop").json()["mechanic_name"] == "Ron Kinney"

    again = client.post("/api/admin/import", json=exported)
    assert again.status_code == 200
    assert client.get("/api/me").status_code == 200


def test_bad_import_leaves_the_shop_in_place(client):
    missing = client.post("/api/admin/import", json={"format": "something-else", "version": 1})
    assert missing.status_code == 400
    assert "Elena Vasquez" in _names(client)

    exported = client.get("/api/admin/export").json()
    exported["aircraft"][0]["customer_id"] = 999999
    broken = client.post("/api/admin/import", json=exported)
    assert broken.status_code == 400
    assert "Elena Vasquez" in _names(client)
    assert client.get("/api/me").json()["role"] == "admin"

    exported = client.get("/api/admin/export").json()
    exported["aircraft"].append({**exported["aircraft"][0], "id": 99999})
    duplicate = client.post("/api/admin/import", json=exported)
    assert duplicate.status_code == 400
    assert "Elena Vasquez" in _names(client)


def test_import_without_the_current_account_still_signs_them_in(client):
    exported = client.get("/api/admin/export").json()
    exported["users"] = [row for row in exported["users"] if row["username"] != "admin"]
    result = client.post("/api/admin/import", json=exported)
    assert result.status_code == 200, result.text
    me = client.get("/api/me").json()
    assert me["username"] == "admin"
    assert me["role"] == "admin"
    usernames = {row["username"] for row in client.get("/api/admin/users").json()}
    assert usernames == {"admin", "ron"}


def test_import_can_leave_the_importer_as_a_shop_account(client):
    exported = client.get("/api/admin/export").json()
    for row in exported["users"]:
        if row["username"] == "admin":
            row["role"] = "shop"
            row["active"] = False
    result = client.post("/api/admin/import", json=exported)
    assert result.status_code == 200, result.text
    assert result.json()["role"] == "shop"
    me = client.get("/api/me").json()
    assert me["username"] == "admin"
    assert me["role"] == "shop"
    assert me["active"] is True
    assert client.get("/api/admin/export").status_code == 403
    assert "Elena Vasquez" in _names(client)
