"""
Seed the configured database (MySQL in Docker) from a SQLite .db file.

Reads rows out of an existing SQLite file (the app's old `app.db`) and loads
them into whatever database `app.py` is configured for via env vars. Run it
inside the app container so it can reach the `db` service:

    docker compose run --rm \
        -v ./app/app.db:/seed/app.db \
        -e SEED_DB=/seed/app.db \
        app python seed.py

Existing rows in the target tables are cleared first, so the result mirrors
the source file (plus a couple of extra sample rows for the guestbook).
"""
import os
import sqlite3
import sys

from app import app, db, init_db, Profile, Experience, Project, Message

SEED_DB = os.environ.get("SEED_DB") or (sys.argv[1] if len(sys.argv) > 1 else "app.db")


def rows(conn, table):
    cur = conn.execute(f"SELECT * FROM {table}")
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def main():
    if not os.path.exists(SEED_DB):
        raise SystemExit(f"Source SQLite file not found: {SEED_DB}")

    init_db()  # make sure target tables exist

    src = sqlite3.connect(SEED_DB)

    with app.app_context():
        # Wipe target tables (children first is irrelevant here — no FKs)
        for model in (Message, Project, Experience, Profile):
            db.session.query(model).delete()
        db.session.commit()

        for r in rows(src, "profile"):
            db.session.add(Profile(**r))
        for r in rows(src, "experience"):
            db.session.add(Experience(**r))
        for r in rows(src, "project"):
            db.session.add(Project(**r))
        for r in rows(src, "messages"):
            r.pop("created_at", None)  # let the DB default stamp it
            db.session.add(Message(**r))

        # A couple of extra sample guestbook entries so the page isn't empty
        db.session.add_all([
            Message(name="Ada Lovelace", email="ada@example.com",
                    body="Love the GitOps writeup — very clean pipeline!"),
            Message(name="Grace Hopper", email="grace@example.com",
                    body="Nice observability stack. Care to share the dashboards?"),
        ])

        db.session.commit()

        print("Seed complete:")
        print(f"  profile     : {Profile.query.count()}")
        print(f"  experience  : {Experience.query.count()}")
        print(f"  project     : {Project.query.count()}")
        print(f"  messages    : {Message.query.count()}")

    src.close()


if __name__ == "__main__":
    main()
