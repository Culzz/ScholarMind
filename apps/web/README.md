# ScholarMind Web

React 18 + TypeScript + Vite + Tailwind client for the ScholarMind scholarship intelligence
platform. Every material fact is rendered with its **claim state** (`confirmed`,
`not_established`, `needs_verification`, `stale`, `expired`) and colour is never the only
signal — each state always ships with a text label.

## Run commands

```bash
npm install
npm run dev        # Vite dev server on http://localhost:5173
npm run build      # type-check (tsc --noEmit) + production build into dist/
npm run preview    # serve the production build locally
npm test           # vitest run (unit + component tests, jsdom)
npm run test:watch # vitest in watch mode
npm run typecheck  # tsc --noEmit only
npm run lint       # eslint
```

## Configuration

Copy `.env.example` to `.env.local` and adjust:

```
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

No secrets belong in the client bundle. `VITE_*` variables are inlined into the bundle by
Vite, so only non-sensitive configuration belongs here.

## Architecture

```
src/
├── app/routes.tsx      Route table (lazy loaded) + router instance
├── components/         Cross-feature components (ClaimChip, FundingBreakdown, ...)
│   └── ui/             Dependency-free primitives (Button, Card, Table, Dialog, ...)
├── features/           One folder per product surface (discovery, assistant, planner, ...)
├── hooks/              TanStack Query hooks, one per API domain
├── lib/                api client, claim-state registry, formatting, auth
└── types/api.ts        Typed API contracts
```

### Data-fetching rules

* Every data surface renders **loading / empty / error / stale** states using `components/ui`.
* `lib/claims.ts` is the single source of truth for claim-state labels and Tailwind classes.
  Never hard-code a claim colour elsewhere.
* Assistant answers render the answer, its claim list, cited evidence excerpts with snapshot
  time, freshness warnings and a conflict banner. `abstained: true` renders an explicit
  "evidence insufficient" panel listing `missing_information` — never a blank box.
* Eligibility renders rule-by-rule verdicts with reason, evidence links and a
  "what's still missing" list. There is no single percentage-match score anywhere.
* Recommendations are labelled a prioritisation aid, never a probability of admission.

## Authentication model

`src/lib/auth.tsx` keeps the access token **in memory only** — it is never written to
`localStorage`/`sessionStorage`, so an XSS payload cannot exfiltrate a long-lived token.
Token refresh relies on an `httpOnly`, `Secure`, `SameSite=Lax` refresh cookie set by the
API; `lib/api.ts` sends `credentials: 'include'` and attempts a silent refresh on `401`.
Sign-out clears the in-memory token and calls the API's logout endpoint.
