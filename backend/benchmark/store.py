import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def connect(path: Path):
    db = sqlite3.connect(path)
    try:
        with db:
            yield db
    finally:
        db.close()


def initialize(path, metadata):
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as db:
        db.execute("CREATE TABLE IF NOT EXISTS metadata (id INTEGER PRIMARY KEY CHECK (id = 1), payload TEXT)")
        db.execute("CREATE TABLE IF NOT EXISTS entries (seq INTEGER PRIMARY KEY, essay_id TEXT, payload TEXT, raw TEXT)")
        db.execute("INSERT OR IGNORE INTO metadata VALUES (1, ?)", (json.dumps(metadata),))


def add(path, row, raw=None):
    with connect(path) as db:
        db.execute("INSERT INTO entries (essay_id, payload, raw) VALUES (?, ?, ?)",
                   (row["essay_id"], json.dumps(row, ensure_ascii=False), raw))


def read(path):
    with connect(path) as db:
        db.execute("BEGIN")
        metadata = json.loads(db.execute("SELECT payload FROM metadata WHERE id = 1").fetchone()[0])
        rows = [json.loads(row[0]) for row in db.execute("SELECT payload FROM entries ORDER BY seq")]
    latest = {row["essay_id"]: row for row in rows}
    return metadata, list(latest.values()), rows


def export(path):
    with connect(path) as db:
        return list(db.execute("SELECT essay_id, payload, raw FROM entries ORDER BY seq"))
