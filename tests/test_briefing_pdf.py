def test_sample_password_fallback_accepts_the_username():
    from app.auth import normalize_password
    from app.seed import _password_for

    assert normalize_password("admin") == "admin"
    assert normalize_password("ron") == "ron"
    assert _password_for("", "admin", "ADMIN_PASSWORD") == ("admin", False)
    assert _password_for("", "ron", "SHOP_PASSWORD") == ("ron", False)


def test_aircraft_briefing_downloads_as_pdf(client, anon):
    assert anon.get("/api/present/aircraft/1/pdf").status_code == 401

    aircraft = client.get("/api/aircraft").json()
    skyhawk = next(row for row in aircraft if row["registration"] == "N5183K")
    response = client.get(f"/api/present/aircraft/{skyhawk['id']}/pdf")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert 'filename="N5183K-briefing.pdf"' in response.headers["content-disposition"]
    body = response.content
    assert body.startswith(b"%PDF")
    assert b"N5183K" in body
    assert b"Elena Vasquez" in body
    assert b"AIRCRAFT BRIEFING" in body
    assert b"TACH / HOBBS" in body
    assert b"WORK ORDER" in body
    assert b"Open items" in body
    assert b"%%EOF" in body
    assert client.get("/api/present/aircraft/999999/pdf").status_code == 404

    from app.briefing_pdf import briefing_pdf
    from app.schemas import PresentAircraft

    sheet = PresentAircraft.model_validate(client.get(f"/api/present/aircraft/{skyhawk['id']}").json())
    sheet.logbook = list(sheet.logbook) * 40
    continued = briefing_pdf(sheet)
    assert b"Page 2 of" in continued
    assert continued.count(b"N5183K") >= 2

    anon.headers["X-Kinney-Request"] = "1"
    signed = anon.post("/api/login", json={"username": "ron", "password": "test-shop-password"})
    assert signed.status_code == 200
    shop_copy = anon.get(f"/api/present/aircraft/{skyhawk['id']}/pdf")
    assert shop_copy.status_code == 200
    assert shop_copy.content.startswith(b"%PDF")
