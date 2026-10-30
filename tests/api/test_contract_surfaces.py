"""Contract tests for the profile, applications and tracked tasks endpoints.

These tests need a database (CI provides one; locally set ``DATABASE_URL``).
They are skipped when Postgres is unreachable so the rest of the unit suite can
run anywhere.
"""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import create_app


def _database_available() -> bool:
    if not os.getenv("DATABASE_URL"):
        return False
    try:
        from app.db.session import get_engine

        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _database_available(), reason="needs a reachable PostgreSQL database"
)


@pytest.fixture()
def client():
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture()
def student(client: TestClient):
    """A registered student with a bearer token and cleaned-up rows afterwards."""
    email = f"contract-{uuid.uuid4().hex[:12]}@example.test"
    register = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "a long enough password", "full_name": "Test Student"},
    )
    assert register.status_code == 201, register.text
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "a long enough password"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    user_id = client.get("/api/v1/auth/me", headers=headers).json()["id"]
    yield {"headers": headers, "user_id": user_id, "client": client}
    from app.db.session import get_engine

    with get_engine().begin() as connection:
        connection.execute(text("DELETE FROM users WHERE email = :email"), {"email": email})


def test_get_profile_returns_an_honest_empty_profile(student) -> None:
    response = student["client"].get("/api/v1/profile", headers=student["headers"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["completeness"] == 0.0
    assert body["fields_of_study"] == []
    assert body["nationality_country_iso3"] is None


def test_put_profile_computes_completeness_and_merges(student) -> None:
    client = student["client"]
    headers = student["headers"]

    first = client.put(
        "/api/v1/profile",
        headers=headers,
        json={"nationality_country_iso3": "NGA", "current_degree_level": "masters"},
    )
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["nationality_country_iso3"] == "NGA"
    assert 0 < body["completeness"] < 1

    # A partial put keeps the stored values and adds new ones.
    second = client.put(
        "/api/v1/profile",
        headers=headers,
        json={"gpa_value": 4.2, "gpa_scale": "nigerian_5"},
    )
    assert second.status_code == 200, second.text
    merged = second.json()
    assert merged["nationality_country_iso3"] == "NGA"
    assert merged["gpa_value"] == 4.2
    assert merged["completeness"] > body["completeness"]

    # Unknown fields are rejected outright; no silent data loss.
    rejected = client.put(
        "/api/v1/profile",
        headers=headers,
        json={"hacker_field": "nope"},
    )
    assert rejected.status_code == 422, rejected.text


def test_evaluate_defaults_to_all_current_cycles(client: TestClient) -> None:
    """No selection means the whole current-cycle shortlist, never a 404."""
    response = client.post("/api/v1/eligibility/evaluate", json={"profile": {}})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["assessments"], "the seeded corpus has current cycles to evaluate"
    assessment = body["assessments"][0]
    assert "verdict_counts" in assessment
    assert "counts" in assessment
    assert assessment["verdict_counts"] == assessment["counts"]
    assert "created_at" in assessment and assessment["created_at"]


def _pick_cycle(client: TestClient) -> dict[str, str] | None:
    listing = client.get("/api/v1/scholarships", params={"limit": 1}).json()
    items = listing.get("items") or []
    for item in items:
        cycle = item.get("current_cycle")
        if cycle and cycle.get("id"):
            return {"scholarship_id": item["id"], "cycle_id": cycle["id"]}
    return None


def test_application_creation_generates_tasks_and_patch_updates(student) -> None:
    client = student["client"]
    headers = student["headers"]
    target = _pick_cycle(client)
    if target is None:
        pytest.skip("the seeded corpus has no scholarship with a current cycle")

    created = client.post(
        "/api/v1/applications",
        headers=headers,
        json={"scholarship_id": target["scholarship_id"], "cycle_id": target["cycle_id"]},
    )
    assert created.status_code == 200, created.text
    application = created.json()
    assert application["status"] == "planning"
    assert application["tasks_generated"] >= 0

    tasks = client.get(
        "/api/v1/tasks",
        headers=headers,
        params={"application_id": application["id"]},
    ).json()
    assert tasks["items"], "a generated application carries at least a submission task"
    task = tasks["items"][0]
    assert task["status"] == "todo"
    assert task["is_auto_generated"] is True

    def _mark(task: dict, status: str) -> dict:
        response = client.patch(
            f"/api/v1/tasks/{task['id']}",
            headers=headers,
            json={"status": status},
        )
        assert response.status_code == 200, response.text
        return response.json()

    done = _mark(task, "done")
    assert done["status"] == "done"
    assert done["completed_at"] is not None

    blocked = _mark(done, "blocked")
    assert blocked["status"] == "blocked"
    assert blocked["completed_at"] is None, "leaving 'done' clears completed_at"

    unknown = client.patch(
        f"/api/v1/tasks/{task['id']}",
        headers=headers,
        json={"status": "vibes"},
    )
    assert unknown.status_code == 409, unknown.text

    # Duplicate application for the same cycle is refused.
    duplicate = client.post(
        "/api/v1/applications",
        headers=headers,
        json={"scholarship_id": target["scholarship_id"], "cycle_id": target["cycle_id"]},
    )
    assert duplicate.status_code == 409, duplicate.text

    status_update = client.patch(
        f"/api/v1/applications/{application['id']}",
        headers=headers,
        json={"status": "preparing"},
    )
    assert status_update.status_code == 200, status_update.text
    assert status_update.json()["status"] == "preparing"


def test_scholarship_list_carries_spa_contract_keys(client: TestClient) -> None:
    listing = client.get("/api/v1/scholarships", params={"limit": 5}).json()
    assert listing["next_cursor"] is not None
    assert listing["total"]
    item = listing["items"][0]
    for key in (
        "current_cycle",
        "official_url",
        "rule_count",
        "provider_country_iso3",
        "deadline_claim_state",
    ):
        assert key in item, f"missing {key} in list item"

    page_two = client.get(
        "/api/v1/scholarships", params={"limit": 5, "cursor": listing["next_cursor"]}
    )
    assert page_two.status_code == 200, page_two.text
    page_two_item_ids = {entry["id"] for entry in page_two.json()["items"]}
    if page_two_item_ids:
        first_page_ids = {entry["id"] for entry in listing["items"]}
        assert not (page_two_item_ids & first_page_ids), "cursor pages overlap"

    broken = client.get("/api/v1/scholarships", params={"limit": 5, "cursor": "@@@"})
    assert broken.status_code == 404, broken.text


def test_scholarship_detail_serves_the_spa_envelope(client: TestClient) -> None:
    listing = client.get("/api/v1/scholarships", params={"limit": 1}).json()
    item = listing["items"][0]
    detail = client.get(f"/api/v1/scholarships/{item['id']}").json()
    for key in (
        "scholarship",
        "cycles",
        "funding_components",
        "required_documents",
        "rules",
        "sources",
        "latest_assessment",
    ):
        assert key in detail, f"missing {key} in detail envelope"
    assert detail["scholarship"]["id"] == item["id"]
    assert isinstance(detail["cycles"], list)
    assert detail["latest_assessment"] is None
    for rule in detail["rules"]:
        assert "authored_by" in rule
        assert rule["comparability"]


def test_history_and_evidence_serve_spa_field_names(client: TestClient) -> None:
    listing = client.get("/api/v1/scholarships", params={"limit": 1}).json()
    item = listing["items"][0]
    history = client.get(f"/api/v1/scholarships/{item['id']}/history").json()
    assert set(history.keys()) == {"changes", "conflicts"}
    for entry in history["changes"]:
        assert "field_name" in entry
    for entry in history["conflicts"]:
        assert "field_name" in entry

    evidence = client.get(f"/api/v1/scholarships/{item['id']}/evidence").json()
    for claim in evidence["claims"]:
        assert "claim_text" in claim and "snapshot_id" in claim
        break
