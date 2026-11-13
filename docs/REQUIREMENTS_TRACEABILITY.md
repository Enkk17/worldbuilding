# Requirements Traceability

This matrix tracks the delivered milestones. The complete functional, security, and release criteria remain those in `docs/specifications/WORLDWEAVE_M0/`.

| Requirement | Implementation | Verification | State |
|---|---|---|---|
| FR-AUTH-01 account registration policy | FastAPI registration endpoint; `bootstrap_only`, `open`, and `closed` modes | `backend/tests/test_auth.py` | Implemented; tests pass |
| FR-AUTH-02 login | Argon2id credential verification and generic credential errors | `backend/tests/test_auth.py` | Implemented; tests pass |
| FR-AUTH-03 revocable sessions | Opaque session cookie, hashed server-side token, logout revocation and expiry | `backend/tests/test_auth.py` | Implemented; tests pass |
| FR-AUTH-04 multi-universe membership | Membership model with five ranked roles | `backend/tests/test_universes.py`, `test_release_e2e.py` | Implemented; tests pass |
| FR-AUTH-05 membership or explicit public-read access | Central permission matrix and visibility filter | `backend/tests/test_universe_security.py`, `test_codex_visibility.py`, `test_security_audit.py` | Implemented; tests pass |
| FR-CODEX-* entities, types, relations | Codex module and Nexus graph endpoint | `backend/tests/test_codex.py`, `test_codex_validation.py` | Implemented; tests pass |
| FR-CHRON-* documents, revisions, comments | Chronicle module | `backend/tests/test_chronicle.py` | Implemented; tests pass |
| FR-COLLAB-* realtime editing | Yjs rooms, tickets, persistence, compaction | `backend/tests/test_collaboration.py`, `test_release_e2e.py` | Implemented; tests pass |
| FR-ATLAS-* maps, markers, regions, assets | Atlas module | `backend/tests/test_atlas_chronos.py` | Implemented; tests pass |
| FR-CHRONOS-* calendars, eras, events | Chronos module | `backend/tests/test_atlas_chronos.py` | Implemented; tests pass |
| FR-SEARCH-* unified search | PostgreSQL FTS with permission filtering | `backend/tests/test_search.py` | Implemented; tests pass |
| FR-IO-* import/export | Bundle generation and validated import | `backend/tests/test_import_export.py`, `test_release_e2e.py` | Implemented; tests pass |
| NFR-OPS-01 health/readiness and structured logs | `/api/healthz`, `/api/readyz`, request IDs, JSON logs | `backend/tests/test_health.py` | Implemented; verified |
| NFR-REL-01 durable committed writes | PostgreSQL-backed sessions and content; durable realtime acknowledgements | Restart durability scenario and live PostgreSQL drill | Implemented; verified |
| NFR-SEC-01 cross-universe isolation and XSS safety | `universe_id` scoping, visibility filter, content sanitization | `backend/tests/test_security_audit.py` | Implemented; tests pass |
| NFR-OPS-02 backup and restore | Database and media backups with checksum sidecars and a verified restore drill | `docs/BACKUP_RESTORE.md` drill evidence | Implemented; verified |
| All M1–M9 migrations | Alembic history `0001`–`0007` | Clean-database migration and FTS index verification | Implemented; verified |
| Release regression suite | Ten release scenarios | `backend/tests/test_release_e2e.py` | Implemented; tests pass |
| Release security audit | Cross-cutting security properties | `backend/tests/test_security_audit.py` | Implemented; tests pass |
