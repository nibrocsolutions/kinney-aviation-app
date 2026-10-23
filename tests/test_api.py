from datetime import date, timedelta


def _by_number(rows):
    return {row["number"]: row for row in rows}


def test_health_and_homepage(client):
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    page = client.get("/")
    assert page.status_code == 200
    body = page.text
    assert "Kinney Aviation" in body
    assert "Records" in body
    assert "Billing" in body
    assert "Present" in body
    assert "Briefing" in body
    assert "Calendar" in body
    assert "Sign in" in body


def test_seeded_fleet_billing_matches_the_work_orders(client):
    aircraft = client.get("/api/aircraft").json()
    registrations = {item["registration"] for item in aircraft}
    assert {"N5183K", "N8146Q", "N35DR", "N22AZ"} <= registrations

    invoices = _by_number(client.get("/api/invoices").json())
    assert invoices["INV-2026-001"]["status"] == "paid"
    assert invoices["INV-2026-001"]["total_cents"] == 186200
    assert invoices["INV-2026-001"]["balance_cents"] == 0
    assert invoices["INV-2026-001"]["registration"] == "N8146Q"

    assert invoices["INV-2026-002"]["status"] == "partial"
    assert invoices["INV-2026-002"]["total_cents"] == 23350
    assert invoices["INV-2026-002"]["balance_cents"] == 13350

    cirrus = invoices["INV-2026-003"]
    assert cirrus["status"] == "issued"
    assert cirrus["total_cents"] == 86150
    assert cirrus["amount_due_cents"] == 86150
    assert any(line["description"].startswith("AD-CLAMP-KIT") for line in cirrus["lines"])
    assert any(line["kind"] == "travel" and line["amount_cents"] == 20900 for line in cirrus["lines"])

    draft = invoices["INV-2026-004"]
    assert draft["status"] == "draft"
    assert draft["total_cents"] == 103140
    assert draft["balance_cents"] == 103140
    assert draft["amount_due_cents"] == 0
    assert draft["stale"] is False
    assert draft["registration"] == "N5183K"

    skyhawk = next(item for item in aircraft if item["registration"] == "N5183K")
    briefing = client.get(f"/api/present/aircraft/{skyhawk['id']}")
    assert briefing.status_code == 200
    assert briefing.json()["open_balance_cents"] == 103140

    dashboard = client.get("/api/dashboard").json()
    assert dashboard["shop"]["mechanic_name"] == "Ron Kinney"
    assert dashboard["open_work"] == 2
    assert dashboard["awaiting_parts"] == 1
    assert dashboard["unbilled_count"] == 1
    assert dashboard["fleet_count"] == 4
    assert dashboard["receivables_cents"] == sum(
        item["amount_due_cents"] for item in invoices.values() if item["status"] in {"issued", "partial"}
    )
    assert dashboard["receivables_cents"] == 99500
    assert dashboard["draft_cents"] == 103140
    remaining = [item["days_remaining"] for item in dashboard["annuals"]]
    assert remaining == sorted(remaining)
    assert all(days <= 60 for days in remaining)


def test_integrated_billing_from_a_work_order(client):
    owner = client.post(
        "/api/customers",
        json={"name": "Mesa Test Owner", "city": "Mesa", "email": "mesa@example.com"},
    )
    assert owner.status_code == 201
    owner_id = owner.json()["id"]

    aircraft = client.post(
        "/api/aircraft",
        json={
            "customer_id": owner_id,
            "registration": "n100ka",
            "make": "Cessna",
            "model": "182",
            "home_airport": "kffz",
        },
    )
    assert aircraft.status_code == 201
    assert aircraft.json()["registration"] == "N100KA"
    aircraft_id = aircraft.json()["id"]

    duplicate = client.post(
        "/api/aircraft",
        json={"customer_id": owner_id, "registration": "N100KA", "make": "Cessna", "model": "182"},
    )
    assert duplicate.status_code == 409

    blocked = client.delete(f"/api/customers/{owner_id}")
    assert blocked.status_code == 409

    empty = client.post(
        "/api/records",
        json={"aircraft_id": aircraft_id, "kind": "repair", "title": "Empty squawk", "discrepancy": "None yet."},
    )
    assert empty.status_code == 201
    assert client.post(f"/api/records/{empty.json()['id']}/invoice").status_code == 400

    created = client.post(
        "/api/records",
        json={
            "aircraft_id": aircraft_id,
            "kind": "repair",
            "title": "Landing light",
            "discrepancy": "Landing light inoperative.",
            "location": "KFFZ",
        },
    )
    assert created.status_code == 201
    record_id = created.json()["id"]

    with_labor = client.post(
        f"/api/records/{record_id}/labor",
        json={"description": "Replace landing light", "hours": 2.5, "rate_cents": 12500},
    )
    assert with_labor.status_code == 201
    assert with_labor.json()["labor_cents"] == 31250

    with_part = client.post(
        f"/api/records/{record_id}/parts",
        json={
            "part_number": "GE4509",
            "description": "Landing light lamp",
            "quantity": 2,
            "unit_price_cents": 500,
        },
    )
    assert with_part.status_code == 201
    record = with_part.json()
    assert record["parts_cents"] == 1000
    assert record["total_cents"] == 32250

    invoice = client.post(f"/api/records/{record_id}/invoice")
    assert invoice.status_code == 201
    body = invoice.json()
    assert body["status"] == "draft"
    assert body["total_cents"] == 32250
    assert body["stale"] is False
    assert body["record_number"] == record["number"]
    invoice_id = body["id"]
    assert client.post(f"/api/records/{record_id}/invoice").status_code == 409

    client.post(
        f"/api/records/{record_id}/labor",
        json={"description": "Operational check", "hours": 1, "rate_cents": 12500},
    )
    stale = client.get(f"/api/invoices/{invoice_id}").json()
    assert stale["stale"] is True

    refreshed = client.post(f"/api/invoices/{invoice_id}/refresh")
    assert refreshed.status_code == 200
    assert refreshed.json()["total_cents"] == 44750
    assert refreshed.json()["stale"] is False

    issued = client.post(f"/api/invoices/{invoice_id}/issue")
    assert issued.status_code == 200
    issued_body = issued.json()
    assert issued_body["status"] == "issued"
    assert issued_body["issued_on"] == date.today().isoformat()
    assert issued_body["due_on"] == (date.today() + timedelta(days=15)).isoformat()
    assert client.post(f"/api/invoices/{invoice_id}/refresh").status_code == 409
    assert client.post(
        f"/api/records/{record_id}/labor",
        json={"description": "Extra", "hours": 1, "rate_cents": 12500},
    ).status_code == 409

    narrative = client.patch(
        f"/api/records/{record_id}",
        json={"corrective_action": "Replaced both lamps and ops-checked the circuit."},
    )
    assert narrative.status_code == 200

    too_much = client.post(f"/api/invoices/{invoice_id}/payments", json={"amount_cents": 999999, "method": "check"})
    assert too_much.status_code == 400

    partial = client.post(
        f"/api/invoices/{invoice_id}/payments",
        json={"amount_cents": 10000, "method": "check", "reference": "221"},
    )
    assert partial.status_code == 201
    assert partial.json()["status"] == "partial"
    assert partial.json()["amount_due_cents"] == 34750

    paid = client.post(
        f"/api/invoices/{invoice_id}/payments",
        json={"amount_cents": 34750, "method": "ach", "reference": "ACH-9"},
    )
    assert paid.status_code == 201
    assert paid.json()["status"] == "paid"
    assert paid.json()["amount_due_cents"] == 0

    briefing = client.get(f"/api/present/aircraft/{aircraft_id}")
    assert briefing.status_code == 200
    assert briefing.json()["aircraft"]["registration"] == "N100KA"
    sheet = client.get(f"/api/present/records/{record_id}")
    assert sheet.status_code == 200
    assert "Landing light" in sheet.json()["record"]["title"]
    presented = client.get(f"/api/present/invoices/{invoice_id}")
    assert presented.status_code == 200
    assert presented.json()["invoice"]["status"] == "paid"


def test_issued_invoice_keeps_its_travel_line(client):
    records = client.get("/api/records").json()
    cirrus = next(row for row in records if row["number"] == "WO-2026-003")
    locked = client.patch(f"/api/records/{cirrus['id']}", json={"travel_hours": 4})
    assert locked.status_code == 409
    edited = client.patch(
        f"/api/records/{cirrus['id']}",
        json={"discrepancy": "Exhaust AD complied with. Clamps replaced."},
    )
    assert edited.status_code == 200
    assert edited.json()["travel_hours"] == 2.2


def test_void_lets_the_work_order_be_billed_again(client):
    records = client.get("/api/records").json()
    draft = next(row for row in records if row["invoice"] and row["invoice"]["status"] == "draft")
    invoice_id = draft["invoice"]["id"]
    voided = client.post(f"/api/invoices/{invoice_id}/void")
    assert voided.status_code == 200
    assert voided.json()["status"] == "void"
    rebilled = client.post(f"/api/records/{draft['id']}/invoice")
    assert rebilled.status_code == 201
    assert rebilled.json()["status"] == "draft"
    assert rebilled.json()["total_cents"] == draft["total_cents"]
