import re
from typing import List, Optional
from src.core.storage import Database
from src.core.models import Document, Term

class NotebookService:
    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()

    # --- Operações de Documento ---

    def create_document(self, title: str, content: str) -> Document:
        doc = Document(title=title, content=content)
        with self.db.get_connection() as conn:
            conn.execute(
                "INSERT INTO documents (id, title, content, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (doc.id, doc.title, doc.content, doc.created_at, doc.updated_at)
            )
        return doc

    def list_documents(self) -> List[Document]:
        with self.db.get_connection() as conn:
            rows = conn.execute("SELECT * FROM documents ORDER BY updated_at DESC").fetchall()
            return [Document(**dict(row)) for row in rows]

    def get_document(self, doc_id: str) -> Optional[Document]:
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
            return Document(**dict(row)) if row else None

    def update_document(self, doc_id: str, title: str, content: str):
        """Atualiza conteúdo e título com timestamp automático."""
        with self.db.get_connection() as conn:
            conn.execute(
                "UPDATE documents SET title = ?, content = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (title, content, doc_id)
            )

    # --- Operações de Termos / Notas Laterais ---

    def add_term_note(self, document_id: str, term_text: str, anchor_key: str, note_content: str, color: str = "#89b4fa") -> Term:
        term = Term(
            document_id=document_id,
            term_text=term_text,
            anchor_key=anchor_key,
            note_content=note_content,
            color=color
        )
        with self.db.get_connection() as conn:
            conn.execute(
                """INSERT INTO terms (id, document_id, term_text, anchor_key, note_content, color, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (term.id, term.document_id, term.term_text, term.anchor_key, term.note_content, term.color, term.created_at)
            )
        return term

    def get_note_by_anchor(self, anchor_key: str) -> Optional[Term]:
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT * FROM terms WHERE anchor_key = ?", (anchor_key,)).fetchone()
            return Term(**dict(row)) if row else None

    def list_terms_for_document(self, document_id: str) -> List[Term]:
        with self.db.get_connection() as conn:
            rows = conn.execute("SELECT * FROM terms WHERE document_id = ?", (document_id,)).fetchall()
            return [Term(**dict(row)) for row in rows]

    def update_term_note(self, anchor_key: str, new_note: str):
        """Atualiza o conteúdo de uma nota existente."""
        with self.db.get_connection() as conn:
            conn.execute(
                "UPDATE terms SET note_content = ? WHERE anchor_key = ?",
                (new_note, anchor_key)
            )

    # --- Configurações / Preferências de Usuário (Blindadas) ---

    def get_setting(self, key: str, default: str = "") -> str:
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else default

    def set_setting(self, key: str, value: str):
        with self.db.get_connection() as conn:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, str(value).strip())
            )

    def get_font_size(self, default: int = 15) -> int:
        """Lê o tamanho da fonte com validação de tipo e limites."""
        raw = self.get_setting("font_size", str(default))
        try:
            val = int(raw)
            return val if 10 <= val <= 40 else default
        except (ValueError, TypeError):
            return default

    def get_theme(self, default: str = "dark") -> str:
        """Garante que apenas temas válidos sejam retornados."""
        theme = self.get_setting("theme", default).lower()
        return theme if theme in {"dark", "light"} else default

    def get_text_color(self, default: str = "#cdd6f4") -> str:
        """Valida se a cor é um formato hexadecimal válido."""
        color = self.get_setting("text_color", default)
        if re.match(r"^#(?:[0-9a-fA-F]{3}){1,2}$", color):
            return color
        return default

    def rename_document(self, doc_id: str, new_title: str):
        """Renomeia apenas o título de um documento."""
        with self.db.get_connection() as conn:
            conn.execute(
                "UPDATE documents SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (new_title.strip(), doc_id)
            )

    def delete_document(self, doc_id: str):
        """Exclui o documento e todas as suas notas associadas (via CASCADE)."""
        with self.db.get_connection() as conn:
            conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))

    def duplicate_document(self, doc_id: str) -> Optional[Document]:
        """Clona um documento e recria seus termos com novas âncoras independentes."""
        original = self.get_document(doc_id)
        if not original:
            return None

        terms = self.list_terms_for_document(doc_id)
        new_content = original.content
        new_terms_to_insert = []

        # Gera novas chaves para evitar conflito de UNIQUE no banco
        for t in terms:
            new_anchor = f"anc_{uuid.uuid4().hex[:8]}"
            old_token = f"[[{t.term_text}|{t.anchor_key}]]"
            new_token = f"[[{t.term_text}|{new_anchor}]]"
            new_content = new_content.replace(old_token, new_token)
            new_terms_to_insert.append((t.term_text, new_anchor, t.note_content, getattr(t, 'color', '#89b4fa')))

        new_doc = self.create_document(f"{original.title} (Cópia)", new_content)

        for term_text, new_anchor, note_content, color in new_terms_to_insert:
            self.add_term_note(new_doc.id, term_text, new_anchor, note_content, color)

        return new_doc