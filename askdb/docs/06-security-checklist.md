# Security checklist (Phase 7)

Status: implemented controls vs remaining work.

| Control | Status | Notes |
| --- | --- | --- |
| Argon2id password hashing | Done | `app/auth/passwords.py` |
| JWT access + rotating refresh, reuse detection | Done | Phase 1 |
| CORS allowlist | Done | settings + middleware |
| CSRF double-submit on cookie mutations | Done | |
| Login rate limiting | Done | |
| Analytics SELECT-only role + `READ ONLY` tx + statement listener | Done | `db/session.py` |
| SQL text guardrails (`sql_is_safe`) | Done | Phase 3 / chat |
| Upload size + extension checks | Done | Knowledge service |
| Industry isolation for documents | Done | per-industry directories |
| Web retrieval off by default | Done | `WEB_RETRIEVAL_ENABLED=false` |
| Secret redaction in logs | Done | |
| Pydantic validation | Done | |
| Security headers | Done | |
| No Streamlit / no parent imports in `askdb/` | Done | |
| PDF/DOCX binary parsers | Partial | UTF-8 text/Markdown/HTML in this build |
| Qdrant + Mongo production wiring | Partial | readiness probes exist; local hash index used for RAG |
| Prompt-injection corpus tests | Pending | add under `tests/security/` when LLM key available |
| Accessibility audit | Pending | manual pass on shell + dashboard |
| SSRF-safe web fetch | Pending | gated off until allowlist fetch lands |

## Operator notes

1. Never put `askdb_owner` credentials in the API runtime DSN.
2. Set `COOKIE_SECURE=true` and exact `CORS_ALLOWED_ORIGINS` in production.
3. Rotate `JWT_SECRET_KEY` with a break-glass plan; refresh families invalidate on reuse.
