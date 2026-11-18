"""Database role the application connects as.

The migration creates ``triage_app`` when the role is missing and sets its
password from ``APP_DB_PASSWORD``. When that variable is unset, the local
placeholder in ``.env.example`` is used so a laptop migrate still works.
Rotate the role with ``ALTER ROLE`` before Postgres is reachable beyond the demo host.
"""

import os

APP_ROLE = "triage_app"
APP_PASSWORD = os.environ.get("APP_DB_PASSWORD", "local-dev-app-password")
