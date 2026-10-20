# Load test profile

`assistant.js` is a [k6](https://k6.io) script that exercises the ScholarMind API under a
short, sustained arrival rate. It is the reduced profile that runs against a containerised
stack on every pull request; the full saturation test is a separate, nightly job.

## What it exercises

| Endpoint | Scenario | What it checks |
|---|---|---|
| `GET /api/v1/health` | `smoke` (once) | The service is up and answers `200`. |
| `POST /api/v1/assistant/ask` | `assistant` (2 req/s for 30s) | Status `200`; the JSON body has a boolean `abstained` and an `evidence` array. |
| `POST /api/v1/eligibility/evaluate` | `eligibility` (2 req/s for 30s) | Status `200` or `404`; a `200` body has an `assessments` array. |

The assistant request body is a realistic question, not a ping:

```json
{"question": "What is the application deadline for the Chevening 2027 cycle?", "top_k": 10, "mode": "hybrid"}
```

The eligibility request body is:

```json
{"cycle_ids": [], "scholarship_ids": [], "profile": {"nationality": "NGA"}}
```

An empty cycle selection legitimately returns `404` ("no cycles matched the request"), so that
status is treated as expected for this endpoint and does not count towards the error budget.

## Running it

k6 is not installed by the repository; install it separately
(`brew install k6`, `choco install k6`, or the official binary).

```sh
# against a local stack
k6 run infra/load/assistant.js

# against another environment
BASE_URL=https://staging.example.org k6 run infra/load/assistant.js

# keep the raw output for the experiment record
BASE_URL=https://staging.example.org k6 run --out json=results.json infra/load/assistant.js
```

`BASE_URL` defaults to `http://localhost:8000`. The script does not authenticate; the API
rate limiter must therefore be configured to allow the profile's request rate, otherwise the
run measures the limiter rather than the service.

## Thresholds

| Threshold | Value | Meaning |
|---|---|---|
| `http_req_duration{endpoint:assistant}` | `p(95)<8000` | 95% of assistant answers complete within 8 seconds. This is the budget the hybrid retrieval plus generation path is allowed to spend. |
| `assistant_latency` | `p(95)<8000` | The same budget on a custom trend metric, so it still applies if the request tags change. Both must pass. |
| `http_req_failed` | `rate<0.01` | Fewer than 1% of requests may fail. |
| `http_req_failed{endpoint:assistant}` | `rate<0.01` | The assistant path is held to the same error budget in isolation. |
| `smoke_check_rate` | `rate==1` | The health endpoint must answer every time. |
| `assistant_check_rate` | `rate>0.99` | Almost every assistant response must satisfy the body-shape checks. |
| `eligibility_check_rate` | `rate>0.99` | Almost every eligibility response must satisfy the body-shape checks. |
| `checks` | `rate>0.99` | Aggregate of all checks. |

A breached threshold makes the k6 run exit non-zero, which fails the CI job that invoked it.

## Recording results

A load run is evidence only when it is filed. Copy the console summary and the raw k6 output
into the experiment tree before citing it:

```
research/experiments/<experiment-id>/<YYYYMMDDTHHMMSSZ>/load-assistant-summary.txt
research/experiments/<experiment-id>/<YYYYMMDDTHHMMSSZ>/load-assistant-results.json
```

Include the `BASE_URL`, the commit hash of the code under test, the machine the run executed on,
and the k6 version (`k6 version`). Numbers that are not in `research/experiments/` are not
citable in a paper, a release note or a pull request.
