# API reference

The authoritative, always-current contract is the generated OpenAPI schema at
`/docs` (Swagger UI), `/redoc` and `/openapi.json` on a running API. Both are disabled
when `ENVIRONMENT=production`.

This document covers the conventions and the endpoints that exist today. Later phases
extend it in place.

## Conventions

**Base path.** Everything except the probes lives under `/api/v1`. Probes are
unversioned because orchestrators are configured once and should not have to follow an
API version.

**Casing.** Requests and responses are camelCase on the wire; the Python models are
snake_case and the alias generator bridges the two. Both spellings are accepted on input,
so a client is never broken by the difference.

**Authentication.** Cookies, not headers. Sign-in sets three:

| Cookie | HttpOnly | Path | Purpose |
| --- | --- | --- | --- |
| `nql_access` | yes | `/` | Short-lived JWT, default 15 minutes |
| `nql_refresh` | yes | `/api/v1/auth` | Opaque rotating token, default 14 days |
| `nql_csrf` | no | `/` | Double-submit value the client echoes in `x-csrf-token` |

The refresh cookie is scoped to the auth path, so a request to any other route cannot
carry it. A bearer `Authorization` header is also accepted for scripts and integration
tests, which have no cookie jar; that path skips CSRF because there is no ambient
credential to abuse.

**CSRF.** Every unsafe method on a cookie-authenticated route requires `x-csrf-token` to
match the `nql_csrf` cookie. Safe methods do not.

**Industry.** Requests may carry `x-industry: automotive|insurance`. Omitted, the
caller's saved default applies.

**Errors.** One shape, always:

```json
{
  "error": {
    "code": "invalid_credentials",
    "message": "The email or password is incorrect.",
    "requestId": "01JB2Q...",
    "details": {}
  }
}
```

`code` is stable and safe to branch on; `message` is safe to show a user and never
contains internals; `requestId` also appears in the `x-request-id` response header and in
the structured log, so a user-reported failure can be found without guessing.

**Pagination.** Cursor-based, because an OFFSET scan over a multi-million-row table gets
slower the deeper you page:

```json
{ "items": [], "meta": { "total": null, "limit": 50, "nextCursor": "...", "hasMore": true } }
```

`total` is null when counting would cost a full scan.

## Status codes

| Code | Meaning here |
| --- | --- |
| 400 | Malformed request |
| 401 | No session, or an expired or invalid token. The client should refresh once, then sign in |
| 403 | Authenticated but not permitted, including a CSRF mismatch |
| 404 | No such resource, or one the caller may not know exists |
| 409 | Conflict, such as an email already registered |
| 422 | Validation failure, with the offending fields in `details` |
| 429 | Rate limited. `Retry-After` is set |
| 503 | A dependency is unavailable |

A 404 is deliberately returned in place of a 403 where confirming existence would itself
leak information.

## Probes

### `GET /health`

Unauthenticated liveness. Reports only that the process is up — never dependency detail,
because this endpoint is typically reachable from outside.

```json
{ "status": "ok", "service": "nql-insight-api", "version": "0.1.0",
  "environment": "development", "time": "2026-01-01T00:00:00Z" }
```

### `GET /ready`

Unauthenticated readiness. Returns 200 with `status` of `ready` or `degraded`, and 503
with `not_ready`.

The application database is required. An analytics database being down *degrades* the
service rather than taking it offline, because the other industry may still be fully
usable. Dependencies not yet wired up report `not_configured` instead of `ok`, so the
probe never claims health it cannot verify.

## Authentication

### `POST /api/v1/auth/login`

Body: `{ "email": "...", "password": "..." }`. Sets the three cookies and returns
`{ user, csrfToken, accessExpiresAt }`.

An unknown address and a wrong password return the same 401 `invalid_credentials`, and
the unknown-user path still performs a hash verification against a dummy value so the
response time does not reveal which case occurred.

Rate limited per address and per client IP, default six attempts per minute. Exceeding it
returns 429 with `Retry-After` and records an audit event.

### `POST /api/v1/auth/refresh`

Takes the refresh cookie, no body. Rotates the token and returns a fresh session.

Rotation is single-use. Presenting an already-rotated token means either the client
replayed it or someone captured it, so the entire token family is revoked, an audit event
is written, and the cookies are cleared. That revocation is committed even though the
request then fails — a security decision must not be rolled back by the error that
follows it.

### `POST /api/v1/auth/logout`

Requires CSRF. Body: `{ "allSessions": false }`. `true` revokes every session for the
user, not just this browser. Returns 204 and clears the cookies.

### `GET /api/v1/auth/me`

The caller's profile: `{ id, email, fullName, role, defaultIndustry, isActive,
mustChangePassword, lastLoginAt, createdAt }`.

### `PATCH /api/v1/auth/me/preferences`

Requires CSRF. Body: `{ "defaultIndustry": "insurance" }`. Returns the updated profile.

### `POST /api/v1/auth/me/password`

Requires CSRF. Body: `{ "currentPassword": "...", "newPassword": "..." }`. Returns 204.

The new password must satisfy the configured policy: minimum length, mixed case, a digit,
and not equal to the current one. Every session including the caller's is revoked, so the
client must sign in again — a password change that left old sessions alive would not
actually lock anyone out.

### `POST /api/v1/auth/users` — admin

Requires CSRF. Creates an account. Returns 201 with the profile, or 409 if the email is
taken. There is no self-service sign-up; the first administrator comes from
`scripts/create_admin.py`.

### `GET /api/v1/auth/users` — admin

`?limit=100&offset=0`, capped at 500. Returns profiles, never password hashes.

## System

### `GET /api/v1/industries`

Authenticated. Each entry reports `databaseAvailable` and `semanticPackLoaded` so the UI
can distinguish "this industry is unavailable" from "you are not allowed to see it".

### `GET /api/v1/diagnostics` — admin

Non-secret configuration, dependency reports and cache statistics. Secrets appear only as
booleans under `secretsConfigured`, so there is no redacted value that could be
partially recovered.

## Semantic Core

All routes require at least the viewer role and resolve the industry from `?industry=`,
then `x-industry`, then the user's saved default.

### `GET /api/v1/semantic/packs`

Summaries for every validated pack: version, domain, and counts of tables,
relationships, measures, dimensions and glossary terms.

### `GET /api/v1/semantic/pack`

The complete typed semantic model and business glossary for the active industry. Pack
loading validates primary keys, table/column references, measure sources and glossary
mappings before returning anything.

### `GET /api/v1/semantic/ontology`

A deterministic, cached graph snapshot containing nodes, edges, clusters and build
metadata. The browser does not parse YAML or derive relationships; it only lays out this
already-validated snapshot.

### `GET /api/v1/data/tables`

Lists semantic tables for the active industry with physical names, primary keys and
estimated row counts from `pg_class`.

### `GET /api/v1/data/preview/{table}`

Keyset-paginated rows (`cursor` + `limit`). Never uses `OFFSET`. Row count is capped by
`SQL_PREVIEW_PAGE_SIZE` / `SQL_MAX_RESULT_ROWS`.

### `GET /api/v1/data/export/{table}`

CSV of one capped preview page (same guardrails and row cap).

### `GET /api/v1/data/quality/{table}`

Legacy data-quality health score on a capped sample (nulls, duplicates, outliers,
cardinality, date gaps).

## Coming in later phases

Documented here as they land, with the same conventions.

### KPI / dashboard

- `GET /api/v1/kpis/filters`
- `GET /api/v1/kpis/summary`
- `POST /api/v1/kpis/scenario` (dormant until forecast data exists)

### Chat / activity

- `POST /api/v1/chat/ask` (SSE)
- `GET /api/v1/history`
- `GET|POST /api/v1/questions`
- `GET /api/v1/cost`

### Knowledge

- `GET|POST /api/v1/documents`
- `POST /api/v1/documents/search`
- `DELETE /api/v1/documents/{id}`

Hardening references: [security checklist](06-security-checklist.md),
[parity checklist](07-parity-checklist.md).

