# db

Postgres schema and repositories for agentic triage. Contract: `docs/uml/er-diagram.md`.

```bash
cd db
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
DATABASE_URL=postgresql+psycopg://triage:…@localhost:5432/triage \
  .venv/bin/alembic upgrade head
.venv/bin/pytest
```

`alembic upgrade head` creates every ER table, `CREATE EXTENSION vector`, and the `triage_app` role. That role can `INSERT` and `SELECT` `audit_events` and cannot `UPDATE` or `DELETE` them. Its password is the local placeholder `APP_DB_PASSWORD` in `.env.example`. Rotate it with `ALTER ROLE` outside a laptop or demo VM.

The application should connect as `triage_app`. The migration role owns the tables and is the only role that can tamper with the audit log; the chain verifier treats that as an incident.

Tests use `TEST_DATABASE_URL` when it is set, otherwise a local Postgres 16 with pgvector (`postgresql+psycopg://ubuntu@/postgres` as a superuser who can create a database).
