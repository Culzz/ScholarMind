// Load profile for the ScholarMind API.
//
// Exercises three endpoints against a running instance:
//
//   GET  /api/v1/health              - liveness smoke check
//   POST /api/v1/assistant/ask       - the answering path (hybrid retrieval)
//   POST /api/v1/eligibility/evaluate - the deterministic rule engine
//
// Run with:
//
//   k6 run infra/load/assistant.js
//   BASE_URL=https://staging.example.org k6 run infra/load/assistant.js
//
// Thresholds are documented in infra/load/README.md. Results must be copied
// into research/experiments/ before a load run is cited anywhere.

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

// Target under test. Override with BASE_URL for staging or shared environments.
const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';

const ASSISTANT_QUESTION =
  'What is the application deadline for the Chevening 2027 cycle?';

const ASSISTANT_BODY = {
  question: ASSISTANT_QUESTION,
  top_k: 10,
  mode: 'hybrid',
};

const ELIGIBILITY_BODY = {
  cycle_ids: [],
  scholarship_ids: [],
  profile: { nationality: 'NGA' },
};

const JSON_HEADERS = { 'Content-Type': 'application/json' };

// Custom metrics.
const assistantLatency = new Trend('assistant_latency', true); // time in ms
const smokeChecks = new Rate('smoke_check_rate');
const assistantChecks = new Rate('assistant_check_rate');
const eligibilityChecks = new Rate('eligibility_check_rate');

export const options = {
  discardResponseBodies: false,
  scenarios: {
    smoke: {
      exec: 'smoke',
      startTime: '0s',
      vus: 1,
      iterations: 1,
      gracefulStop: '10s',
    },
    assistant: {
      exec: 'assistant',
      startTime: '10s',
      rate: 2, // two questions per second
      timeUnit: '1s',
      duration: '30s',
      preAllocatedVUs: 4,
      maxVUs: 8,
      gracefulStop: '15s',
    },
    eligibility: {
      exec: 'eligibility',
      startTime: '10s',
      rate: 2,
      timeUnit: '1s',
      duration: '30s',
      preAllocatedVUs: 2,
      maxVUs: 4,
      gracefulStop: '15s',
    },
  },
  thresholds: {
    // Assistant latency budget (docs/EVALUATION.md, latency section).
    'http_req_duration{endpoint:assistant}': ['p(95)<8000'],
    // The same budget expressed on the custom trend, so it survives tag changes.
    assistant_latency: ['p(95)<8000'],
    // Error budget: fewer than 1% of requests may fail.
    http_req_failed: ['rate<0.01'],
    'http_req_failed{endpoint:assistant}': ['rate<0.01'],
    // The health endpoint must always answer.
    smoke_check_rate: ['rate==1'],
    assistant_check_rate: ['rate>0.99'],
    eligibility_check_rate: ['rate>0.99'],
    checks: ['rate>0.99'],
  },
};

export function smoke() {
  const res = http.get(`${BASE_URL}/api/v1/health`, {
    tags: { endpoint: 'health' },
  });
  const ok = check(res, {
    'health: status is 200': (r) => r.status === 200,
    'health: body is JSON': (r) => r.body !== null && r.body !== undefined,
  });
  smokeChecks.add(ok);
  sleep(1);
}

export function assistant() {
  const res = http.post(
    `${BASE_URL}/api/v1/assistant/ask`,
    JSON.stringify(ASSISTANT_BODY),
    {
      headers: JSON_HEADERS,
      tags: { endpoint: 'assistant' },
    },
  );

  const ok = check(res, {
    'assistant: status is 200': (r) => r.status === 200,
    'assistant: body has boolean abstained': (r) =>
      r.status === 200 && typeof r.json('abstained') === 'boolean',
    'assistant: body has evidence array': (r) =>
      r.status === 200 && Array.isArray(r.json('evidence')),
  });

  assistantChecks.add(ok);
  assistantLatency.add(res.timings.duration);
  sleep(0.2);
}

export function eligibility() {
  // An empty selection of cycles legitimately answers 404 ("no cycles matched
  // the request"), so 404 is an expected status here and must not inflate
  // http_req_failed.
  const res = http.post(
    `${BASE_URL}/api/v1/eligibility/evaluate`,
    JSON.stringify(ELIGIBILITY_BODY),
    {
      headers: JSON_HEADERS,
      tags: { endpoint: 'eligibility' },
      responseCallback: http.expectedStatuses(200, 404),
    },
  );

  const ok = check(res, {
    'eligibility: status is 200 or 404': (r) => r.status === 200 || r.status === 404,
    'eligibility: 200 body has assessments': (r) =>
      r.status !== 200 || Array.isArray(r.json('assessments')),
  });

  eligibilityChecks.add(ok);
  sleep(0.2);
}

export function handleSummary(data) {
  const assistant = data.metrics['http_req_duration{endpoint:assistant}'];
  const failed = data.metrics.http_req_failed;
  const checks = data.metrics.checks;

  const p95 = assistant && assistant.values ? assistant.values['p(95)'] : null;
  const failedRate = failed && failed.values ? failed.values.rate : null;
  const checkRate = checks && checks.values ? checks.values.rate : null;

  const lines = [];
  lines.push('ScholarMind load profile summary');
  lines.push(`  target:            ${BASE_URL}`);
  lines.push(`  assistant p95:     ${p95 === null ? 'n/a' : p95.toFixed(0)} ms`);
  lines.push(
    `  http_req_failed:   ${failedRate === null ? 'n/a' : (failedRate * 100).toFixed(2)}%`,
  );
  lines.push(
    `  checks passed:     ${checkRate === null ? 'n/a' : (checkRate * 100).toFixed(2)}%`,
  );
  lines.push('');
  lines.push('Record this run under research/experiments/ before citing it.');

  return {
    stdout: lines.join('\n') + '\n',
  };
}
