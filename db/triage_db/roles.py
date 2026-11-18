"""Database role the application connects as.

``APP_PASSWORD`` is the local placeholder named ``APP_DB_PASSWORD`` in
``.env.example``. The initial migration creates ``triage_app`` with that
password when the role is missing. Rotate it with ``ALTER ROLE`` before
Postgres is reachable beyond the demo host.
"""

APP_ROLE = "triage_app"
APP_PASSWORD = "local-dev-app-password"
