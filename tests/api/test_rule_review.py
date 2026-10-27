"""The rule review queue: proposals in, human-approved engine rules out.

A candidate becomes a rule only through this queue, so the tests pin down the
whole contract: only admins act, approval re-validates and writes an
``eligibility_rules`` row with ``authored_by='human'``, rejection disabled
candidates, and invalid edits are refused with the validator's reasons.
"""

from __future__ import annotations

import json
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
def admin(client: TestClient):
    """A registered user promoted to admin, with an access token."""
    email = f"admin-{uuid.uuid4().hex[:12]}@example.test"
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "a long enough password"},
    )
    assert response.status_code == 201, response.text

    from app.db.session import get_engine

    with get_engine().begin() as connection:
        connection.execute(
            text("UPDATE users SET role = 'admin' WHERE email = :email"), {"email": email}
        )
    login = client.post("/api/v1/auth/login", json={"email": email, "password": "a long enough password"})
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    yield {"email": email, "token": token}

    with get_engine().begin() as connection:
        connection.execute(text("DELETE FROM users WHERE email = :email"), {"email": email})


@pytest.fixture()
def cycle(admin, client: TestClient):
    """A scholarship with one current cycle, for candidates to attach to."""
    from app.db.session import get_engine

    with get_engine().begin() as connection:
        source_id = connection.execute(
            text(
                """
                INSERT INTO source_documents (id, url, source_type, trust_tier)
                VALUES (gen_random_uuid(), :url, 'official_primary', 'official_primary')
                RETURNING id::text
                """
            ),
            {"url": f"https://queue-test.example.org/{uuid.uuid4().hex[:12]}"},
        ).scalar_one()
        row = connection.execute(
            text(
                """
                INSERT INTO scholarships (id, name, slug, provider_type, status, canonical_source_id)
                VALUES (gen_random_uuid(), 'Queue Test Award',
                        'queue-test-' || substring(gen_random_uuid()::text, 1, 8),
                        'university', 'active', CAST(:source_id AS uuid))
                RETURNING id::text
                """
            ),
            {"source_id": source_id},
        ).scalar_one()
        connection.execute(
            text("UPDATE source_documents SET scholarship_id = CAST(:sid AS uuid) WHERE id = CAST(:source_id AS uuid)"),
            {"sid": row, "source_id": source_id},
        )
        cycle_id = connection.execute(
            text(
                """
                INSERT INTO scholarship_cycles (id, scholarship_id, intake_year, is_current)
                VALUES (gen_random_uuid(), CAST(:sid AS uuid), 2027, true)
                RETURNING id::text
                """
            ),
            {"sid": row},
        ).scalar_one()
    yield {"scholarship_id": row, "cycle_id": cycle_id}

    with get_engine().begin() as connection:
        connection.execute(
            text("DELETE FROM rule_candidates WHERE cycle_id = CAST(:cid AS uuid)"),
            {"cid": cycle_id},
        )
        connection.execute(
            text("DELETE FROM eligibility_rules WHERE cycle_id = CAST(:cid AS uuid)"),
            {"cid": cycle_id},
        )
        connection.execute(
            text("DELETE FROM scholarship_cycles WHERE id = CAST(:cid AS uuid)"),
            {"cid": cycle_id},
        )
        connection.execute(text("DELETE FROM scholarships WHERE id = CAST(:sid AS uuid)"), {"sid": row})


GPA_QUOTE = "Applicants must have a minimum CGPA of 4.0 out of 5.0"


def _insert_candidate(cycle: dict, *, value=4.0, kind="gpa", subject="gpa.min_overall", operator="gte") -> str:
    from app.db.session import get_engine

    with get_engine().begin() as connection:
        return connection.execute(
            text(
                """
                INSERT INTO rule_candidates
                    (cycle_id, kind, subject, operator, value, comparator, rule_text,
                     span_start, span_end, span_text, drafted_by, confidence, status, validation_notes)
                VALUES (CAST(:cycle_id AS uuid), :kind, :subject, :operator, CAST(:value AS jsonb),
                        'mandatory', :rule_text, 10, 10 + :len, :rule_text, 'llm', 0.5, 'proposed', '[]'::jsonb)
                RETURNING id::text
                """
            ),
            {
                "cycle_id": cycle["cycle_id"],
                "kind": kind,
                "subject": subject,
                "operator": operator,
                "value": json.dumps(value),
                "rule_text": GPA_QUOTE,
                "len": len(GPA_QUOTE),
            },
        ).scalar_one()


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_non_admin_cannot_list_the_queue(client: TestClient) -> None:
    email = f"student-{uuid.uuid4().hex[:12]}@example.test"
    registered = client.post(
        "/api/v1/auth/register", json={"email": email, "password": "a long enough password"}
    )
    assert registered.status_code == 201
    login = client.post("/api/v1/auth/login", json={"email": email, "password": "a long enough password"})
    response = client.get("/api/v1/admin/rule-candidates", headers=_headers(login.json()["access_token"]))
    assert response.status_code == 403

    from app.db.session import get_engine

    with get_engine().begin() as connection:
        connection.execute(text("DELETE FROM users WHERE email = :email"), {"email": email})


def test_approved_candidate_becomes_a_human_authored_rule(client: TestClient, admin, cycle) -> None:
    candidate_id = _insert_candidate(cycle)
    response = client.post(
        f"/api/v1/admin/rule-candidates/{candidate_id}/approve",
        json={"note": "matches the eligibility page"},
        headers=_headers(admin["token"]),
    )
    assert response.status_code == 200, response.text
    rule_id = response.json()["rule_id"]

    from app.db.session import get_engine

    with get_engine().begin() as connection:
        rule = connection.execute(
            text(
                """
                SELECT kind, subject, operator, value, authored_by, confidence
                FROM eligibility_rules WHERE id::text = :rule_id
                """
            ),
            {"rule_id": rule_id},
        ).mappings().first()
        assert rule["authored_by"] == "human"
        assert float(rule["confidence"]) == 1.0
        assert rule["subject"] == "gpa.min_overall"
        status = connection.execute(
            text("SELECT status FROM rule_candidates WHERE id::text = :id"),
            {"id": candidate_id},
        ).scalar_one()
        assert status == "approved"
        # clean up
        connection.execute(text("DELETE FROM eligibility_rules WHERE id::text = :rule_id"), {"rule_id": rule_id})


def test_approve_refuses_a_candidate_that_no_longer_validates(client: TestClient, admin, cycle) -> None:
    candidate_id = _insert_candidate(cycle, value=4.0)
    response = client.post(
        f"/api/v1/admin/rule-candidates/{candidate_id}/approve",
        json={"edits": {"value": 4.5}},  # 4.5 is not inside the quoted text
        headers=_headers(admin["token"]),
    )
    assert response.status_code == 409, response.text
    assert "claimed value" in json.dumps(response.json()["error"]["detail"])

    from app.db.session import get_engine

    with get_engine().begin() as connection:
        status = connection.execute(
            text("SELECT status FROM rule_candidates WHERE id::text = :id"),
            {"id": candidate_id},
        ).scalar_one()
        assert status == "proposed"
        created = connection.execute(
            text("SELECT count(*) FROM eligibility_rules WHERE rule_text = :q"), {"q": GPA_QUOTE}
        ).scalar_one()
        assert created == 0  # the engine table is untouched by the refusal


def test_rejected_candidate_never_becomes_a_rule(client: TestClient, admin, cycle) -> None:
    candidate_id = _insert_candidate(cycle)
    response = client.post(
        f"/api/v1/admin/rule-candidates/{candidate_id}/reject",
        json={"note": "aggregated from a dated brochure"},
        headers=_headers(admin["token"]),
    )
    assert response.status_code == 200, response.text

    approve_again = client.post(
        f"/api/v1/admin/rule-candidates/{candidate_id}/approve", json={}, headers=_headers(admin["token"])
    )
    assert approve_again.status_code == 409

    # The cycle fixture teardown cleans up: the rejection left no rule behind.
    from app.db.session import get_engine

    with get_engine().begin() as connection:
        rules = connection.execute(
            text("SELECT count(*) FROM eligibility_rules WHERE rule_text = :q"), {"q": GPA_QUOTE}
        ).scalar_one()
        assert rules == 0


def test_queue_listing_filters_by_status(client: TestClient, admin, cycle) -> None:
    proposed = _insert_candidate(cycle)
    response = client.get(
        "/api/v1/admin/rule-candidates?status=proposed", headers=_headers(admin["token"])
    )
    assert response.status_code == 200, response.text
    ids = [item["id"] for item in response.json()["items"]]
    assert proposed in ids

    client.post(
        f"/api/v1/admin/rule-candidates/{proposed}/reject", json={}, headers=_headers(admin["token"])
    )
    after = client.get(
        "/api/v1/admin/rule-candidates?status=proposed", headers=_headers(admin["token"])
    ).json()["items"]
    assert proposed not in [item["id"] for item in after]

    from app.db.session import get_engine

    with get_engine().begin() as connection:
        connection.execute(text("DELETE FROM rule_candidates WHERE id::text = :id"), {"id": proposed})
