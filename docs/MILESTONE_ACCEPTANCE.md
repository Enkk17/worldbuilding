# Milestone Acceptance

No milestone is complete based on planned work alone. Update each item only with evidence from an actual run.

## M0 — Product and architecture baseline

- [x] Supplied M0 documentation and all three ADRs reviewed.
- [x] Source specification pack retained under `docs/specifications/WORLDWEAVE_M0/`.
- [x] Architecture remains modular monolith; no AI features or external SaaS requirement added.

## M1 — Foundation

- [x] React/Vite account access and first-run account landing implemented.
- [x] FastAPI auth/health contract and generated client implemented.
- [x] PostgreSQL SQLAlchemy models and Alembic migration authored.
- [x] Docker Compose and Windows operation scripts authored.
- [x] Python auth, session, error-envelope, security, and health tests pass (13 tests).
- [x] Workspace TypeScript typecheck passes.
- [x] Web production build passes.
- [x] Alembic migration applies to the development PostgreSQL database from the pre-M1 state.
- [x] API health/readiness verified against the running service (both returned HTTP 200).
- [x] Docker Compose syntax validates.
- [ ] GitHub Actions CI completes successfully, including migration against its clean PostgreSQL service.
- [ ] Docker Desktop clean start, stop-with-data-preserved, backup, and restore drill completed.
- [x] M1 documentation and requirement evidence updated with current verification results and remaining gates.

## M2–M9

Not started. Follow the ordered gates and acceptance criteria in `docs/specifications/WORLDWEAVE_M0/ROADMAP.md`. In particular, do not claim realtime collaboration until its persistence, recovery, permissions, and disconnection tests pass.
