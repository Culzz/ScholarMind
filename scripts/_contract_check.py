"""Wire-contract check: the endpoints the React app calls, verified in-process.

Run with the same env vars as the test suite (DATABASE_URL + PYTHONPATH).
"""

from __future__ import annotations

import json
import os

from fastapi.testclient import TestClient

from app.main import create_app

ENDPOINTS = [
    ("GET", "/api/v1/scholarships", {"limit": 3}),
    ("GET", "/api/v1/scholarships", {"limit": 1, "sort": "deadline"}),
    ("GET", "/api/v1/health", None),
    ("GET", "/api/v1/scholarships/{sid}", None),
    ("GET", "/api/v1/scholarships/{sid}/evidence", None),
    ("POST", "/api/v1/assistant/ask", {"question": "What is Chevening?"}),
    ("POST", "/api/v1/eligibility/evaluate", {"profile": {"nationality": "NGA"}}),
    ("GET", "/api/v1/scholarships/{sid}/changes", None),
]

client = TestClient(create_app(), raise_server_exceptions=False)

listing = client.get("/api/v1/scholarships", params={"limit": 3}).json()
print("list keys:", sorted(listing.keys()))
items = listing.get("items", [])
print("item keys:", sorted(items[0].keys()) if items else "(no items)")
print("first item:", json.dumps({k: items[0][k] for k in list(items[0])[:10]}, default=str)[:400])

if items:
    sid = items[0].get("id")
    detail = client.get(f"/api/v1/scholarships/{sid}").json()
    print("detail keys:", sorted(detail.keys()))
    evidence = client.get(f"/api/v1/scholarships/{sid}/evidence").json()
    print("evidence keys:", sorted(evidence.keys()) if isinstance(evidence, dict) else "(list)")

ask = client.post(
    "/api/v1/assistant/ask",
    json={"question": "What is Chevening?"},
).json()
print("assistant keys:", sorted(ask.keys()))

evaluation = client.post(
    "/api/v1/eligibility/evaluate",
    json={"profile": {"nationality": "NGA"}},
).json()
print("evaluate keys:", sorted(evaluation.keys()))
if evaluation.get("assessments"):
    a0 = evaluation["assessments"][0]
    print("assessment keys:", sorted(a0.keys()))
    if a0.get("results"):
        print("result keys:", sorted(a0["results"][0].keys()))
