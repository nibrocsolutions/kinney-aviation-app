def _items(client, start, end):
    response = client.get("/api/calendar", params={"start": start, "end": end})
    assert response.status_code == 200
    return response.json()["items"]


def test_october_shows_work_annuals_and_planned_visits(client):
    items = _items(client, "2026-10-01", "2026-10-31")
    by_day = {}
    for item in items:
        by_day.setdefault(item["date"], []).append(item)

    opened = by_day["2026-10-18"]
    assert any(item["source"] == "record" and "N5183K" in item["title"] for item in opened)
    assert any(item["source"] == "record" and item["registration"] == "N35DR" for item in by_day["2026-10-20"])

    visit = next(item for item in by_day["2026-10-24"] if item["source"] == "entry")
    assert visit["starts_at"] == "08:00"
    assert visit["kind"] == "visit"
    assert visit["editable"] is True
    assert "Flagstaff" in visit["title"]

    assert any(item["source"] == "entry" and item["kind"] == "parts" for item in by_day["2026-10-27"])
    annual = next(item for item in by_day["2026-10-30"] if item["source"] == "annual")
    assert annual["registration"] == "N22AZ"
    assert annual["editable"] is False
    assert annual["href"].startswith("#fleet/")


def test_invoice_due_dates_skip_paid_invoices(client):
    items = _items(client, "2026-03-01", "2026-03-31")
    dues = [item for item in items if item["source"] == "invoice" and item["date"] == "2026-03-21"]
    assert len(dues) == 1
    assert "INV-2026-002" in dues[0]["title"]
    assert all("INV-2026-001" not in item["title"] for item in items)


def test_schedule_can_be_added_and_removed(client):
    aircraft_id = next(item["id"] for item in client.get("/api/aircraft").json() if item["registration"] == "N8146Q")
    created = client.post(
        "/api/schedule",
        json={
            "scheduled_on": "2026-10-23",
            "starts_at": "13:00",
            "kind": "ferry",
            "title": "Pick up the Archer in Prescott",
            "aircraft_id": aircraft_id,
            "notes": "Owner will meet the airplane.",
        },
    )
    assert created.status_code == 201
    entry_id = created.json()["id"]
    assert created.json()["registration"] == "N8146Q"

    items = _items(client, "2026-10-23", "2026-10-23")
    assert any(item["entry_id"] == entry_id and item["starts_at"] == "13:00" for item in items)

    moved = client.patch(f"/api/schedule/{entry_id}", json={"scheduled_on": "2026-10-25", "starts_at": None})
    assert moved.status_code == 200
    assert moved.json()["scheduled_on"] == "2026-10-25"
    assert moved.json()["starts_at"] is None

    assert client.delete(f"/api/schedule/{entry_id}").status_code == 204
    remaining = _items(client, "2026-10-25", "2026-10-25")
    assert all(item["entry_id"] != entry_id for item in remaining)


def test_calendar_rejects_a_long_span(client, anon):
    assert client.get("/api/calendar", params={"start": "2026-01-01", "end": "2026-06-01"}).status_code == 400
    assert anon.get("/api/calendar", params={"start": "2026-10-01", "end": "2026-10-31"}).status_code == 401
