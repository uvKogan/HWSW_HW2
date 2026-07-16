"""
External persistence for the FaaS architecture.

Each function invocation is a brand-new process with no memory of the
last call (stateless execution). State has to live outside the
process, exactly like a real FaaS function would reach out to a
database/object store. We use sqlite3 (stdlib) as a stand-in for that
external service.
"""

import json
import sqlite3
from pathlib import Path

from common.operations import OPERATIONS, initial_state

DB_PATH = Path(__file__).parent / "data" / "state.db"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS state_blob (id INTEGER PRIMARY KEY CHECK (id = 0), data TEXT NOT NULL)")
    return conn


def load_state() -> dict:
    conn = _connect()
    try:
        row = conn.execute("SELECT data FROM state_blob WHERE id = 0").fetchone()
        return json.loads(row[0]) if row else initial_state()
    finally:
        conn.close()


def save_state(state: dict) -> None:
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO state_blob (id, data) VALUES (0, ?) ON CONFLICT(id) DO UPDATE SET data = excluded.data",
            (json.dumps(state),),
        )
        conn.commit()
    finally:
        conn.close()


def reset_state() -> None:
    DB_PATH.unlink(missing_ok=True)


def transactional_apply(op_name: str, params: dict) -> dict:
    """Run load -> op -> save under ONE sqlite transaction (BEGIN IMMEDIATE).

    The naive path (load_state / save_state) uses two separate connections
    with the operation in between, so concurrent invocations both read the
    old blob and the second save clobbers the first (lost update). Here a
    single connection takes the write lock up front; a concurrent invocation
    blocks (busy_timeout) until this one commits, then reads the *updated*
    state -- closing the seat-race. Note this necessarily serialises on the
    single state row: because FaaS state is one JSON blob, this is effectively
    a global state lock, not per-seat locking -- the coarse-external-state
    tax. Enabled per-invocation via OLYMPICS_FAAS_TXN (see _runtime.run).
    """
    conn = _connect()
    try:
        conn.isolation_level = None  # manual transaction control
        conn.execute("PRAGMA busy_timeout = 10000")
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT data FROM state_blob WHERE id = 0").fetchone()
        state = json.loads(row[0]) if row else initial_state()
        result = OPERATIONS[op_name](state, params)
        conn.execute(
            "INSERT INTO state_blob (id, data) VALUES (0, ?) "
            "ON CONFLICT(id) DO UPDATE SET data = excluded.data",
            (json.dumps(state),),
        )
        conn.execute("COMMIT")
        return result
    finally:
        conn.close()
