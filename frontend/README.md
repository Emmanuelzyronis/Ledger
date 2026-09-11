# LEDGER Frontend

Reconciliation dashboard for the LEDGER service. It consumes **only** the
published `/v1` contract at `../docs/openapi/ledger.v1.json`. Unversioned paths
such as `/reports` are a compatibility alias and are never called from here.

Current state: **EMM-104 complete (scaffold + contract-checked typed client) and
the EMM-105 skeleton (layout and information architecture) in place.** Screens
render placeholder data; no live `/v1` calls are made yet.

## Stack

| Concern       | Choice                                                                                                    |
| ------------- | --------------------------------------------------------------------------------------------------------- |
| Framework     | Next.js 15, App Router, TypeScript (strict)                                                               |
| Rendering     | Server Components by default; the only client components are the nav active-state and the resolution form |
| API types     | `openapi-typescript`, generated from the published artifact (never hand-written)                          |
| Styling       | Tailwind CSS with a replaced default palette and project design tokens                                    |
| Tests         | Vitest                                                                                                    |
| Lint / format | ESLint (`next/core-web-vitals`, `next/typescript`) and Prettier                                           |

## Commands

```sh
npm install
npm run dev            # dev server on http://127.0.0.1:3000
npm run generate:api   # regenerate the typed client from the OpenAPI artifact
npm run typecheck      # tsc --noEmit
npm run lint           # eslint
npm run test           # vitest run
npm run build          # production build
npm run check          # generate + typecheck + lint + test + build
```

## Running it against the service

Terminal 1 — the service (repository root):

```sh
PYTHONPATH=src LEDGER_DATABASE_PATH=ledger.sqlite3 \
  LEDGER_API_TOKENS='dev-token:reconciliation_operator:source-a|source-b' \
  python3 -m ledger
# GET http://127.0.0.1:8080/v1/health
```

Terminal 2 — the dashboard:

```sh
cd frontend
cp .env.example .env.local     # then set LEDGER_API_TOKEN=dev-token
npm install
npm run dev                    # http://127.0.0.1:3000
```

Configuration (`.env.local`, never committed):

| Variable                    | Purpose                                                                                                               |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `LEDGER_API_BASE_URL`       | Service base URL. Default `http://127.0.0.1:8080`.                                                                    |
| `LEDGER_API_TOKEN`          | Bearer token. Read server-side only; there is no `NEXT_PUBLIC_` variant, so it is never inlined into browser bundles. |
| `LEDGER_API_CORRELATION_ID` | Optional default correlation id.                                                                                      |

## The generated client

`scripts/generate-api-client.mjs` reads `../docs/openapi/ledger.v1.json` and writes
two files:

- `src/lib/api/schema.ts` — every path, operation, and schema (`openapi-typescript`).
- `src/lib/api/operations.generated.ts` — the operation index the client is keyed
  by: `operationId -> { method, path, pathParams, queryParams, hasRequestBody,
successStatus, isPublic }`, plus the contract enums used by the UI.

No component supplies an endpoint string. `ledgerRequest(operationId, …)` in
`src/lib/api/client.ts` resolves the URL through the generated index, so a
dashboard action either names a contract operation or fails to compile.

Four tests guard the boundary:

| Test                           | What it prevents                                                                                                                                                                         |
| ------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `tests/contract-drift.test.ts` | Regenerates both artifacts in memory and compares them byte-for-byte with the committed files. Editing the contract without running `npm run generate:api` fails the build.              |
| `tests/endpoint-usage.test.ts` | Fails if any source file references a `/v1` path that is not in the artifact.                                                                                                            |
| `tests/contract-enums.test.ts` | Asserts the outcome, batch-state, discrepancy-state, and resolution-type tuples equal the contract's enums.                                                                              |
| `tests/design-system.test.ts`  | Fails on gradients, backdrop blur, glow, oversized radius, generic shadows, animation/transition polish, default-Tailwind palette colors, raw hex colors, and hero-scale type in `src/`. |

## Design system

Tokens live in `tailwind.config.ts`; the default palette is **replaced**, so
`bg-gray-100` does not exist and cannot be used by accident.

- **Neutral base** (`ink`, `surface`, `line`) plus **one accent** (`accent`) for
  primary actions and links.
- **Four desaturated status tones** (`status-matched`, `status-review`,
  `status-discrepancy`, `status-pending`), each a fg/bg/border triplet used by the
  status pills and the row left-border accent.
- **Borders over shadows.** `shadow-overlay` is the only shadow value.
- **Radius is capped** at `6px` for panels (`rounded-panel`) and `4px` for controls.
- Tabular figures for counts; monospace for ids, batches, and correlation ids.
- Plain, factual empty and loading states.

## Information architecture

| Route                 | Purpose                                                | Contract operations                                                                               |
| --------------------- | ------------------------------------------------------ | ------------------------------------------------------------------------------------------------- |
| `/ingest`             | Batch list with status, counters, and timeline         | `registerSource`, `createBatch`, `ingestRecord`, `getBatch`                                       |
| `/reconciliation`     | Matched/unmatched counts and the seven outcomes        | `getReport`, `listReconciliations`, `getReconciliation`                                           |
| `/discrepancies`      | Filterable/sortable queue                              | `listDiscrepancies`, `getDiscrepancy`, `getReconciliation`, `getAuditTrail`, `resolveDiscrepancy` |
| `/discrepancies/{id}` | Evidence, audit trail, resolution action, supersession | `getDiscrepancy`, `getReconciliation`, `getAuditTrail`, `resolveDiscrepancy`                      |
| `/reports`            | Report projection and export scope                     | `getReport`, `exportData`                                                                         |

Every screen also renders this list at the bottom, read from the generated
operation index at render time.

## Deployment (Vercel)

Production project: `ledger-dashboard` (scope `ibiezugbeemmanuel`), root directory `frontend/`.

```sh
cd frontend
npm run check                 # must pass first: it regenerates and verifies the client
npx vercel deploy --prod --yes
```

|                    |                                                                                                                                                                                                                 |
| ------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Production aliases | `https://ledger-dashboard-vert.vercel.app`, `https://ledger-dashboard-ibiezugbeemmanuel.vercel.app`                                                                                                             |
| Not this app       | `https://ledger-dashboard.vercel.app` — that subdomain belongs to a different Vercel account                                                                                                                    |
| Framework          | `vercel.json` pins `"framework": "nextjs"`. Without it a CLI-created project is detected as "Other" and no build runs (the deploy serves nothing).                                                              |
| Remote build       | `next build` only. The generated client is uploaded as source, so the remote build does not need `docs/openapi/ledger.v1.json` — and it never regenerates. Always run `npm run check` locally before deploying. |
| Environment        | None set yet: the app makes no live `/v1` calls. When data wiring lands, add `LEDGER_API_BASE_URL` and the bearer token with `vercel env` — never in a committed file.                                          |
| Access             | Deployment Protection (Vercel Authentication, `all_except_custom_domains`) is on, so anonymous visitors get the Vercel SSO wall. Use `vercel curl` from CI/automation.                                          |

## Not done in this pass

- Live data wiring, including the resolution submit path (EMM-105).
- End-to-end tests driving the real service over deterministic fixtures (EMM-105).
- Playwright/Remotion demo capture — explicitly out of scope.
- EMM-103 (same-batch idempotency defect) is a service-side issue and is not
  touched here; the contract documents it as a known limitation.
