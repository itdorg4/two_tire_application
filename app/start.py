"""Container entrypoint: wait for the DB, init schema + seed, then exec gunicorn."""
import os
import time

from app import init_db

for attempt in range(30):
    try:
        init_db()
        break
    except Exception as exc:  # MySQL may not accept connections yet
        print(f"DB not ready (attempt {attempt + 1}/30): {exc}", flush=True)
        time.sleep(2)
else:
    raise SystemExit("DB unavailable after waiting; giving up.")

os.execvp("gunicorn", [
    "gunicorn", "--bind", "0.0.0.0:5000", "--workers", "3", "app:app",
])
