import sqlite3
from pathlib import Path

DB_PATH = Path("data/blockwatcher.db")


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS wallet (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                address TEXT NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS processed_transactions (
                tx_hash TEXT NOT NULL,
                category TEXT NOT NULL,
                PRIMARY KEY (tx_hash, category)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS monitor_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                last_block INTEGER NOT NULL
            )
        """)


def get_wallet():
    with connect() as conn:
        row = conn.execute(
            "SELECT address FROM wallet WHERE id = 1"
        ).fetchone()

        return row["address"] if row else None


def add_wallet(address):
    address = address.lower()

    with connect() as conn:
        exists = conn.execute(
            "SELECT 1 FROM wallet WHERE id = 1"
        ).fetchone()

        if exists:
            return False

        conn.execute(
            "INSERT INTO wallet (id, address) VALUES (1, ?)",
            (address,)
        )

        return True


def remove_wallet():
    with connect() as conn:
        conn.execute("DELETE FROM wallet WHERE id = 1")
        conn.execute("DELETE FROM monitor_state")


def get_checkpoint():
    with connect() as conn:
        row = conn.execute(
            "SELECT last_block FROM monitor_state WHERE id = 1"
        ).fetchone()

        return row["last_block"] if row else None


def set_checkpoint(block_number):
    with connect() as conn:
        conn.execute("""
            INSERT INTO monitor_state (id, last_block)
            VALUES (1, ?)
            ON CONFLICT(id)
            DO UPDATE SET last_block = excluded.last_block
        """, (block_number,))


def is_processed(unique_id, category):
    with connect() as conn:
        row = conn.execute("""
            SELECT 1
            FROM processed_transactions
            WHERE tx_hash = ? AND category = ?
        """, (unique_id, category)).fetchone()

        return row is not None


def mark_processed(unique_id, category):
    with connect() as conn:
        conn.execute("""
            INSERT OR IGNORE INTO processed_transactions
            (tx_hash, category)
            VALUES (?, ?)
        """, (unique_id, category))