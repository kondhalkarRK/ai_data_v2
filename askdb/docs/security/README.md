# Soci security baseline and ASVS Level 2 register

Updated: 2026-11-24. Scope: `askdb` only, including its API and web application.

**Status: application hardening implemented; ASVS Level 2 verification is incomplete.**
Do not describe Soci as ASVS certified, fully compliant, or protected against every attack.
The attached register contains all **253 Level 1 and Level 2 requirements** from ASVS
5.0.0. Level 2 includes applicable Level 1 requirements. An unassessed requirement is
not a pass; a partial implementation is not a pass either. Applicability decisions,
operational evidence, and independent assessment still need owners and review.

## Implemented in this change

| Control | Behaviour | Verification |
| --- | --- | --- |
| Immediate session revocation | Every authenticated request checks for a live refresh-token family belonging to that user. Logout, password change, or refresh-token reuse revocation blocks captured access JWTs immediately. Normal token rotation continues to work. | `tests/test_security_baseline.py` |
| Bearer-only logout | Logging out without a cookie revokes the authenticated token's session family. | `tests/test_security_baseline.py` |
| Cookie/header CSRF protection | A bearer header cannot bypass CSRF when an access cookie is actually used for authentication. | `tests/test_security_baseline.py` |
| Browser origin protection | Unsafe requests with an Origin outside the configured CORS allowlist are rejected, including login and refresh. Cross-site Fetch Metadata requests without Origin are rejected. Script clients without browser headers still use existing authentication/CSRF rules. | `tests/test_security_baseline.py` |
| Per-user API limit | `RATE_LIMIT_API_PER_MINUTE` now limits authenticated requests and returns HTTP 429 with Retry-After. Health probes and login are not charged to this budget. | `tests/test_security_baseline.py` |
| Password reauthentication limit | Password-change attempts use the login limiter with a separate per-user key. | Application implementation; deployment behaviour still needs acceptance |
| Trusted client identity | Raw X-Forwarded-For is ignored by the application. Security decisions use the ASGI peer address, which a correctly configured trusted proxy may update. | Forged-header throttle regression |
| Production configuration | Startup rejects disabled provider TLS verification without a CA bundle, missing/wildcard trusted hosts, HTTP CORS origins, insecure cookies, short JWT secrets and authentication bypass. Local development remains supported. | Production settings regressions |
| Response protection | API security headers cover host rejection and application failures. Unexpected errors remain generic and uncacheable. Caller-supplied request IDs are bounded and allowlisted. | Error/header regressions |
| Diagnostic redaction | JSON and development text formatters redact recognised credentials in exception tracebacks. This is not a complete PII/DLP system. | Formatter and existing redaction tests |

Existing controls retained include Argon2id hashing, rotating hashed refresh tokens,
server-side roles and regional scoping, read-only analytics transactions, SQL validation,
query timeouts, administrative/login auditing and model quotas. These need continued
verification across all relevant workflows; their presence alone does not close a requirement.

## Register and source

- [ASVS_L2_REGISTER.csv](ASVS_L2_REGISTER.csv): requirement text, applicability/review status,
  code evidence, test evidence and remaining work. No requirement is currently marked as
  fully verified. Pending rows require assessment rather than an assumption of safety.
- [asvs-5.0.0-source.csv](asvs-5.0.0-source.csv): pinned official requirements used to build
  the register. Source SHA-256:
  `98c8fe911b9edb403af8ee05d3ce8201ecac2659e313b053890a62847cdcf680`.
- Source: [OWASP ASVS 5.0.0 CSV](https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/docs_en/OWASP_Application_Security_Verification_Standard_5.0.0_en.csv).
  OWASP requirement text retains its original attribution and
  [project licensing](https://github.com/OWASP/ASVS).

## Remaining work before an L2 claim

| Priority | Work | Owner / evidence needed |
| --- | --- | --- |
| High | MFA/SSO strategy, session idle and absolute lifetime, compromised-password checks, temporary-password enforcement, sensitive admin reauthentication and account recovery review | App team and client identity/security team; end-to-end verification |
| High | Frontend CSP still permits inline scripts. Add and test a nonce/hash policy compatible with Next.js, theming, exports and Outlook authentication | App team; production browser tests |
| High | Existing `nql_*` cookie names do not implement ASVS secure/host prefixes. Coordinate a frontend/backend cookie migration, refresh-path changes and old-cookie cleanup | App team; HTTPS browser and cross-host tests |
| High | Verify ownership and scope on every read, write, cache, download, export, report, feedback and document route, including after permission changes | App team/security assessor; adversarial route matrix |
| High | LLM outbound-data classification, allowlisted fields, PII/secret masking and provider retention/no-training agreements | App and client security teams; captured request evidence with synthetic data |
| High | Private database access, least-privilege runtime roles, database TLS, external HTTPS, secrets vault, encryption and key rotation | Client infrastructure team; deployed configuration and tests |
| High | Distributed login/API throttling and edge request-body/concurrency limits. Current in-process limits apply per API worker and reset on restart | Infrastructure/app teams; multi-worker/load tests |
| High | SSRF review of every outbound client. Web-fetch DNS validation alone does not establish protection against DNS rebinding | App/infra teams; controlled network tests and egress restrictions |
| High | Upload/parser safety, malware scanning, document ACL/deletion checks, and prompt-injection evaluations | App/security teams; keep unverified document/web features gated |
| High | Dependency and secret scanning, software inventory, patching process and independent penetration testing | Engineering/security teams; scan reports and remediation evidence |
| High | Retention/deletion policy, protected audit collection, alerting, backup restoration, incident response and access reviews | Client operations/security teams; exercised procedures |
| Required | Review every remaining register row, justify non-applicability and verify applicable controls | Named control owners and independent reviewer |

Provider compliance does not establish Soci compliance. Private model endpoints still
process the prompt/context sent to them. ASVS application controls also do not replace
AI-specific prompt-injection, data-leakage and grounding evaluations.

## Configuration and rollout

No database migration or package installation is required for these code changes.
Restart the API. Keep local demo development settings; do not switch a local HTTP demo
to production without HTTPS and the required infrastructure configuration.

For production, configure actual deployment values through a secret manager or protected
environment. Example values only:

```ini
ENVIRONMENT=production
AUTH_BYPASS=false
COOKIE_SECURE=true
JWT_SECRET_KEY=<new-cryptographically-random-secret-at-least-32-characters>
CORS_ALLOWED_ORIGINS=https://soci.client.example
TRUSTED_HOSTS=soci.client.example,soci-api.client.example
SSL_VERIFY=true
# Set only when an approved private CA is needed:
SSL_CERT_FILE=
RATE_LIMIT_LOGIN_PER_MINUTE=5
RATE_LIMIT_API_PER_MINUTE=120
```

- Use exact frontend HTTPS origins. Wildcards are not a substitute for configuration.
- Permit database connections only from approved services. Runtime analytics roles must
  have SELECT-only privileges; do not deploy owner/superuser credentials in runtime URLs.
- At the reverse proxy, overwrite untrusted forwarding headers. Configure Uvicorn's
  trusted proxy list to the actual proxy addresses, not every network address. Verify the
  complete proxy chain: otherwise all users may share a throttle bucket or IPs may be forged.
- A live-session database lookup is now made for each authenticated request; the existing
  family/user indexes are reused. Measure this under production load.
- JWTs with no live registered family are rejected. This intentionally ends access for
  revoked sessions and manually minted/unregistered tokens.
- Complete-session revocation takes effect on subsequent authorization checks; it does
  not automatically cancel an already running query or stream. Evaluate cancellation
  requirements and streamed/exported data after permission changes separately.

## Reproduce the automated evidence

Run from `apps/api`, using the existing virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_security_baseline.py tests/test_auth_api.py tests/test_auth_audit.py tests/test_tokens.py tests/test_redaction.py tests/test_ssl_config.py tests/test_governance.py -o addopts='' -q
```

| Validation | Result |
| --- | --- |
| Focused security/authentication/governance suite | 72 passed |
| Existing region, response-rating, prompt-injection, reliability and password regressions | 54 passed |
| Ruff checks on changed Python files and new regression tests | Passed |
| Client gateway, live PostgreSQL, ingress/HTTPS, multiple API workers, real browsers and external penetration testing | Not verified in this change |

The second suite uses synthetic legacy-retrieval fixtures with
`ASK_ME_RAG_ENABLED=false` in the test process. The initial run inherited the local RAG
setting and failed one legacy-search fixture; the explicitly isolated run passed all 54.
No `.env` file was edited. These fixtures do not prove production database permissions,
proxy configuration, TLS, provider privacy, multi-worker controls or full ASVS conformance.
