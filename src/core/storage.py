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
        """Garante abertura, commit automático e fechamento seguro da conexão."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()  # <-- IMPEDE O VAZAMENTO DE CONEXÕES

    def _init_db(self):
        """Inicializa as tabelas caso não existam e aplica migrações de esquema."""
        with self.get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
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
                    color TEXT DEFAULT '#89b4fa',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_terms_document ON terms(document_id);
                CREATE INDEX IF NOT EXISTS idx_terms_anchor ON terms(anchor_key);
            """)

            try:
                conn.execute("ALTER TABLE terms ADD COLUMN color TEXT DEFAULT '#89b4fa';")
            except sqlite3.OperationalError:
                pass