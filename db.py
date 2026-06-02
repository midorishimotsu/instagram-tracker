import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "instagram_tracker.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS daily_metrics (
                date TEXT PRIMARY KEY,
                follower_count INTEGER NOT NULL,
                follower_delta INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS posts (
                post_id TEXT PRIMARY KEY,
                caption TEXT DEFAULT '',
                media_type TEXT DEFAULT '',
                posted_at TEXT DEFAULT '',
                permalink TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS post_metrics (
                post_id TEXT NOT NULL,
                date TEXT NOT NULL,
                reach INTEGER DEFAULT 0,
                saved INTEGER DEFAULT 0,
                shares INTEGER DEFAULT 0,
                likes INTEGER DEFAULT 0,
                comments INTEGER DEFAULT 0,
                follows INTEGER DEFAULT 0,
                profile_visits INTEGER DEFAULT 0,
                total_interactions INTEGER DEFAULT 0,
                PRIMARY KEY (post_id, date),
                FOREIGN KEY (post_id) REFERENCES posts(post_id)
            );
        """)


if __name__ == "__main__":
    init_db()
    print("Database initialized.")
