"""SQLite connection helpers."""
import sqlite3
from pathlib import Path

from . import config

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def connect(path=None):
    path = Path(path or config.DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # WAL lets the web server read while the collector thread writes.
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(conn):
    conn.executescript(SCHEMA_PATH.read_text())
    conn.commit()
