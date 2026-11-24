import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator
from config import DB_PATH

class Database:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        with self.get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    category TEXT DEFAULT 'Geral',
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS terms (
                    id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    term_text TEXT NOT NULL,
                    anchor_key TEXT UNIQUE NOT NULL,
                    note_content TEXT NOT NULL,
                    color TEXT DEFAULT '#ffe066',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS document_history (
                    id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    saved_at TEXT NOT NULL,
                    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_terms_document ON terms(document_id);
                CREATE INDEX IF NOT EXISTS idx_terms_anchor ON terms(anchor_key);
                CREATE INDEX IF NOT EXISTS idx_history_doc ON document_history(document_id);
            """)

            doc_cols = [r["name"] for r in conn.execute("PRAGMA table_info(documents);").fetchall()]
            if "category" not in doc_cols:
                conn.execute("ALTER TABLE documents ADD COLUMN category TEXT DEFAULT 'Geral';")

            term_cols = [r["name"] for r in conn.execute("PRAGMA table_info(terms);").fetchall()]
            if "color" not in term_cols:
                conn.execute("ALTER TABLE terms ADD COLUMN color TEXT DEFAULT '#ffe066';")