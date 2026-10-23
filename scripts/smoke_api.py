"""Smoke test the API against the populated database.

    $env:DATABASE_URL="postgresql+psycopg://postgres@127.0.0.1:55432/scholarmind"
    $env:PYTHONPATH=".;services/api"
    python scripts/smoke_api.py

The checks are read-only. They confirm that the real corpus is served through
the HTTP layer: listing, detail, eligibility evaluation against the extracted
rules, and the assistant's behaviour when no model is configured.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "api"))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

BASE = "/api/v1"


def show(title: str, value: object) -> None:
    print(f"{title}: {json.dumps(value, indent=2, default=str)[:700]}")


def main() -> int:
    failures: list[str] = []

    with TestClient(app) as client:
        health = client.get(f"{BASE}/health")
        print(f"GET /health -> {health.status_code}")
        if health.status_code != 200:
            failures.append("health")

        ready = client.get(f"{BASE}/health/ready")
        print(f"GET /health/ready -> {ready.status_code} {ready.text[:120]}")
        if ready.status_code != 200:
            failures.append("ready")

        listing = client.get(f"{BASE}/scholarships", params={"limit": 5})
        print(f"GET /scholarships -> {listing.status_code}")
        if listing.status_code != 200:
            failures.append("scholarships")
            print(listing.text[:400])
            return 1

        payload = listing.json()
        items = payload.get("items") or payload.get("results") or []
        print(f"  total={payload.get('total')} returned={len(items)}")
        for item in items[:5]:
            deadline = item.get("cycle", {}).get("deadline_at") if isinstance(item.get("cycle"), dict) else None
            print(
                f"   - {item.get('name')[:60]:<60} deadline={deadline}"
                f" status={(item.get('cycle') or {}).get('status') if isinstance(item.get('cycle'), dict) else None}"
            )
        if not items:
            failures.append("empty listing")

        first = items[0] if items else None
        if first:
            detail = client.get(f"{BASE}/scholarships/{first['id']}")
            print(f"GET /scholarships/{{id}} -> {detail.status_code}")
            if detail.status_code != 200:
                failures.append("detail")
            else:
                body = detail.json()
                print(f"  name={body.get('name')}")
                print(f"  rules={len(body.get('eligibility_rules') or [])}"
                      f" funding={len(body.get('funding') or [])}"
                      f" documents={len(body.get('documents') or [])}")
                show("  provenance sample", (body.get("cycles") or [{}])[0])

            evidence = client.get(f"{BASE}/scholarships/{first['id']}/evidence")
            print(f"GET /scholarships/{{id}}/evidence -> {evidence.status_code}")
            if evidence.status_code == 200:
                quotes = evidence.json().get("evidence") or []
                print(f"  evidence items: {len(quotes)}")

            cycle_id = None
            detail_body = detail.json() if detail.status_code == 200 else {}
            cycles = detail_body.get("cycles") or []
            if cycles:
                cycle_id = cycles[0].get("id")

            if cycle_id:
                evaluate = client.post(
                    f"{BASE}/eligibility/evaluate",
                    json={
                        "cycle_ids": [cycle_id],
                        "profile": {
                            "nationality": "NGA",
                            "degree_level": "masters",
                            "work_experience_months": 36,
                        },
                        "explain": True,
                    },
                )
                print(f"POST /eligibility/evaluate -> {evaluate.status_code}")
                if evaluate.status_code != 200:
                    failures.append("evaluate")
                    print(evaluate.text[:400])
                else:
                    assessments = evaluate.json().get("assessments") or []
                    if assessments:
                        assessment = assessments[0]
                        print(f"  overall={assessment.get('overall_status')}"
                              f" summary={assessment.get('summary')}")

        ask = client.post(
            f"{BASE}/assistant/ask",
            json={"question": "What is the application deadline for the Chevening Scholarship?"},
        )
        print(f"POST /assistant/ask -> {ask.status_code}")
        if ask.status_code == 200:
            answer = ask.json()
            print(f"  answer={str(answer.get('answer'))[:180]}")
            print(f"  abstained={answer.get('abstained')} citations={len(answer.get('citations') or [])}")
        else:
            print(f"  {ask.text[:300]}")

    print("\nfailures:", failures or "none")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
