import re
import uuid
import html
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Set

from config import BACKUPS_DIR
from src.core.storage import Database
from src.core.models import Document, Term
from src.core.parser import TextParser


def extract_anchors_from_html(content: str) -> Set[str]:
    """Extrai todas as chaves de âncoras realmente presentes no texto."""
    if not content:
        return set()
    anchors = set(re.findall(r'href=["\']anchor:([^"\']+)["\']', content))
    anchors.update(re.findall(r'\|([^\]|]+)\]\]', content))
    return anchors


class NotebookService:
    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()

    @staticmethod
    def _row_to_document(row) -> Document:
        data = dict(row)
        data["category"] = data.get("category") or "Geral"
        data["card_color"] = data.get("card_color") or ""
        return Document(**data)

    # --- Operações de Documento ---

    def create_document(
        self,
        title: str,
        content: str,
        category: str = "Geral",
        card_color: str = ""
    ) -> Document:
        doc = Document(
            title=title.strip() or "Sem título",
            content=content,
            category=category.strip() or "Geral",
            card_color=card_color or ""
        )
        with self.db.get_connection() as conn:
            conn.execute(
                """INSERT INTO documents (id, title, category, card_color, content, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (doc.id, doc.title, doc.category, doc.card_color, doc.content, doc.created_at, doc.updated_at)
            )
        self.save_history_snapshot(doc.id, doc.title, doc.content)
        return doc

    def list_documents(self, category_filter: Optional[str] = None) -> List[Document]:
        with self.db.get_connection() as conn:
            if category_filter and category_filter != "Todas":
                rows = conn.execute(
                    "SELECT * FROM documents WHERE category = ? ORDER BY updated_at DESC",
                    (category_filter,)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM documents ORDER BY updated_at DESC").fetchall()
            return [self._row_to_document(row) for row in rows]

    def list_categories(self) -> List[str]:
        with self.db.get_connection() as conn:
            rows = conn.execute("SELECT DISTINCT category FROM documents ORDER BY category ASC").fetchall()
            cats = [row["category"] for row in rows if row["category"]]
            return cats if cats else ["Geral"]

    def get_document(self, doc_id: str) -> Optional[Document]:
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
            return self._row_to_document(row) if row else None

    def update_document(
        self,
        doc_id: str,
        title: str,
        content: str,
        category: str = "Geral",
        save_snapshot: bool = True,
        clean_orphans: bool = True
    ):
        now_iso = datetime.now().isoformat()
        clean_title = title.strip() or "Sem título"
        clean_cat = category.strip() or "Geral"
        with self.db.get_connection() as conn:
            conn.execute(
                "UPDATE documents SET title = ?, content = ?, category = ?, updated_at = ? WHERE id = ?",
                (clean_title, content, clean_cat, now_iso, doc_id)
            )
        if save_snapshot:
            self.save_history_snapshot(doc_id, clean_title, content)
        if clean_orphans:
            self.clean_orphaned_terms(doc_id, content)

    def rename_document(self, doc_id: str, new_title: str):
        now_iso = datetime.now().isoformat()
        with self.db.get_connection() as conn:
            conn.execute(
                "UPDATE documents SET title = ?, updated_at = ? WHERE id = ?",
                (new_title.strip() or "Sem título", now_iso, doc_id)
            )

    def update_document_category(self, doc_id: str, category: str):
        now_iso = datetime.now().isoformat()
        with self.db.get_connection() as conn:
            conn.execute(
                "UPDATE documents SET category = ?, updated_at = ? WHERE id = ?",
                (category.strip() or "Geral", now_iso, doc_id)
            )

    def update_document_card_color(self, doc_id: str, card_color: str):
        now_iso = datetime.now().isoformat()
        with self.db.get_connection() as conn:
            conn.execute(
                "UPDATE documents SET card_color = ?, updated_at = ? WHERE id = ?",
                (card_color or "", now_iso, doc_id)
            )

    def delete_document(self, doc_id: str):
        with self.db.get_connection() as conn:
            conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))

    def duplicate_document(self, doc_id: str) -> Optional[Document]:
        original = self.get_document(doc_id)
        if not original:
            return None

        terms = self.list_terms_for_document(doc_id)
        new_content = original.content
        new_terms_to_insert = []

        for t in terms:
            new_anchor = f"anc_{uuid.uuid4().hex[:8]}"
            new_content = re.sub(
                rf'href=["\']anchor:{re.escape(t.anchor_key)}["\']',
                f'href="anchor:{new_anchor}"',
                new_content
            )
            new_content = new_content.replace(f"|{t.anchor_key}]]", f"|{new_anchor}]]")
            new_terms_to_insert.append(
                (t.term_text, new_anchor, t.note_content, getattr(t, "color", "#ffe066"))
            )

        new_doc = self.create_document(
            f"{original.title} (Cópia)",
            new_content,
            original.category,
            original.card_color
        )
        for term_text, new_anchor, note_content, color in new_terms_to_insert:
            self.add_term_note(new_doc.id, term_text, new_anchor, note_content, color)

        return new_doc

    # --- Backup e Restauração Atômica ---

    def create_database_backup(self, custom_path: Optional[Path] = None) -> Path:
        if custom_path is None:
            BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            target_path = BACKUPS_DIR / f"notebook_backup_{timestamp}.db"
        else:
            target_path = Path(custom_path)
            target_path.parent.mkdir(parents=True, exist_ok=True)

        src_conn = sqlite3.connect(self.db.db_path)
        dst_conn = sqlite3.connect(target_path)
        try:
            with dst_conn:
                src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
            src_conn.close()

        return target_path

    def restore_database_backup(self, backup_file_path: Path) -> bool:
        backup_path = Path(backup_file_path)
        if not backup_path.exists():
            return False

        test_conn = sqlite3.connect(backup_path)
        try:
            rows = test_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('documents', 'terms', 'settings');"
            ).fetchall()
            if len(rows) < 3:
                return False
        except Exception:
            return False
        finally:
            test_conn.close()

        src_conn = sqlite3.connect(backup_path)
        dst_conn = sqlite3.connect(self.db.db_path)
        try:
            with dst_conn:
                src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
            src_conn.close()

        return True

    # --- Histórico de Modificações (Snapshots) ---

    def save_history_snapshot(self, doc_id: str, title: str, content: str):
        history_id = str(uuid.uuid4())
        now_iso = datetime.now().isoformat(timespec="seconds")
        with self.db.get_connection() as conn:
            last = conn.execute(
                "SELECT title, content FROM document_history WHERE document_id = ? ORDER BY saved_at DESC LIMIT 1",
                (doc_id,)
            ).fetchone()
            if last and last["title"] == title and last["content"] == content:
                return

            conn.execute(
                "INSERT INTO document_history (id, document_id, title, content, saved_at) VALUES (?, ?, ?, ?, ?)",
                (history_id, doc_id, title, content, now_iso)
            )
            conn.execute(
                """
                DELETE FROM document_history WHERE id NOT IN (
                    SELECT id FROM document_history WHERE document_id = ? ORDER BY saved_at DESC LIMIT 20
                ) AND document_id = ?
                """,
                (doc_id, doc_id)
            )

    def list_history_snapshots(self, doc_id: str) -> List[Dict]:
        with self.db.get_connection() as conn:
            rows = conn.execute(
                "SELECT id, title, saved_at, length(content) as content_len "
                "FROM document_history WHERE document_id = ? ORDER BY saved_at DESC",
                (doc_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_history_snapshot(self, history_id: str) -> Optional[Dict]:
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT * FROM document_history WHERE id = ?", (history_id,)).fetchone()
            return dict(row) if row else None

    # --- Saneamento e Termos / Anotações ---

    def clean_orphaned_terms(self, document_id: str, content: str):
        active_anchors = extract_anchors_from_html(content)
        with self.db.get_connection() as conn:
            rows = conn.execute("SELECT anchor_key FROM terms WHERE document_id = ?", (document_id,)).fetchall()
            for r in rows:
                key = r["anchor_key"]
                if key not in active_anchors:
                    conn.execute("DELETE FROM terms WHERE anchor_key = ?", (key,))

    def count_terms(self, document_id: str, content: Optional[str] = None) -> int:
        if content is not None:
            return len(extract_anchors_from_html(content))

        doc = self.get_document(document_id)
        if doc:
            return len(extract_anchors_from_html(doc.content))

        with self.db.get_connection() as conn:
            row = conn.execute("SELECT COUNT(*) as count FROM terms WHERE document_id = ?", (document_id,)).fetchone()
            return row["count"] if row else 0

    def add_term_note(
        self,
        document_id: str,
        term_text: str,
        anchor_key: str,
        note_content: str,
        color: str = "#ffe066"
    ) -> Term:
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

    def restore_terms_snapshot(self, document_id: str, terms: List[Term]):
        """Restaura exatamente um conjunto de termos (usado pelo Desfazer/Refazer global)."""
        with self.db.get_connection() as conn:
            conn.execute("DELETE FROM terms WHERE document_id = ?", (document_id,))
            for t in terms:
                conn.execute(
                    """INSERT INTO terms (id, document_id, term_text, anchor_key, note_content, color, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (t.id, document_id, t.term_text, t.anchor_key, t.note_content, t.color, t.created_at)
                )

    def get_note_by_anchor(self, anchor_key: str) -> Optional[Term]:
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT * FROM terms WHERE anchor_key = ?", (anchor_key,)).fetchone()
            return Term(**dict(row)) if row else None

    def list_terms_for_document(self, document_id: str, clean_orphans: bool = True) -> List[Term]:
        if clean_orphans:
            doc = self.get_document(document_id)
            if doc:
                self.clean_orphaned_terms(document_id, doc.content)

        with self.db.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM terms WHERE document_id = ? ORDER BY created_at ASC",
                (document_id,)
            ).fetchall()
            return [Term(**dict(row)) for row in rows]

    def update_term_note(self, anchor_key: str, new_note: str):
        with self.db.get_connection() as conn:
            conn.execute("UPDATE terms SET note_content = ? WHERE anchor_key = ?", (new_note, anchor_key))

    def update_term_color(self, doc_id: str, anchor_key: str, new_color: str):
        with self.db.get_connection() as conn:
            conn.execute("UPDATE terms SET color = ? WHERE anchor_key = ?", (new_color, anchor_key))

    def delete_term(self, doc_id: str, anchor_key: str):
        with self.db.get_connection() as conn:
            conn.execute("DELETE FROM terms WHERE anchor_key = ?", (anchor_key,))

    # --- Configurações ---

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
        raw = self.get_setting("font_size", str(default))
        try:
            val = int(raw)
            return val if 10 <= val <= 40 else default
        except (ValueError, TypeError):
            return default

    def get_theme(self, default: str = "dark") -> str:
        theme = self.get_setting("theme", default).lower()
        return theme if theme in {"dark", "light"} else default

    def get_text_color(self, default: str = "#cdd6f4") -> str:
        color = self.get_setting("text_color", default)
        return color if re.match(r"^#(?:[0-9a-fA-F]{3}){1,2}$", color) else default

    # --- Exportação / Importação ---

    def export_to_printable_html(self, doc_id: str) -> Optional[str]:
        doc = self.get_document(doc_id)
        if not doc:
            return None

        terms = self.list_terms_for_document(doc_id)
        content = TextParser.extract_body_inner(doc.content)
        content = re.sub(r'(?<![a-zA-Z-])font-size:\s*[^;"]+;?', "", content)
        content = re.sub(r'(?<![a-zA-Z-])color:\s*#[0-9a-fA-F]+;?', "", content)

        for t in terms:
            badge = (
                f'<span style="background-color: {t.color}; color: #111111; '
                f'padding: 2px 6px; border-radius: 4px;">{html.escape(t.term_text)}</span>'
            )
            content = re.sub(
                rf'<a\s+[^>]*href=["\']anchor:{re.escape(t.anchor_key)}["\'][^>]*>(.*?)</a>',
                lambda _, b=badge: b,
                content,
                flags=re.DOTALL
            )

        glossary_section = ""
        if terms:
            glossary_rows = "".join(
                f'''
                <tr>
                    <td style="width: 30%; font-weight: bold; padding: 10px; border-bottom: 1px solid #e2e8f0; vertical-align: top;">
                        <span style="background-color: {t.color}; color: #111; padding: 2px 6px; border-radius: 4px;">{html.escape(t.term_text)}</span>
                    </td>
                    <td style="width: 70%; padding: 10px; border-bottom: 1px solid #e2e8f0; color: #334155; line-height: 1.5; vertical-align: top;">
                        {html.escape(t.note_content).replace(chr(10), "<br>")}
                    </td>
                </tr>
                '''
                for t in terms
            )
            glossary_section = f"""
            <div style="margin-top: 40px; page-break-inside: avoid;">
                <div style="background-color: #f1f5f9; padding: 10px 16px; border-radius: 6px; border-left: 4px solid #3b82f6; margin-bottom: 12px;">
                    <b style="font-size: 13pt; color: #1e293b;">📌 Glossário e Anotações de Estudo</b>
                </div>
                <table style="width: 100%; border-collapse: collapse; font-size: 10.5pt;">
                    {glossary_rows}
                </table>
            </div>
            """

        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{
            font-family: "Segoe UI", Arial, sans-serif;
            font-size: 11.5pt;
            color: #1e293b;
            line-height: 1.6;
            margin: 0; padding: 0;
        }}
        .header-box {{
            border-bottom: 2px solid #0f172a;
            padding-bottom: 10px;
            margin-bottom: 20px;
        }}
        .doc-title {{ font-size: 20pt; font-weight: 800; color: #0f172a; margin: 0 0 4px 0; }}
        .doc-meta {{ font-size: 9pt; color: #64748b; }}
        p {{ margin: 0 0 12px 0; }}
    </style>
</head>
<body>
    <div class="header-box">
        <div class="doc-title">{html.escape(doc.title)}</div>
        <div class="doc-meta">Categoria: {html.escape(doc.category)} • ANote</div>
    </div>
    <div class="main-content">{content}</div>
    {glossary_section}
</body>
</html>"""

    def export_document_data(self, doc_id: str) -> Optional[dict]:
        doc = self.get_document(doc_id)
        if not doc:
            return None

        terms = self.list_terms_for_document(doc_id)
        return {
            "version": "1.3",
            "title": doc.title,
            "category": doc.category,
            "card_color": doc.card_color,
            "content": doc.content,
            "terms": [
                {
                    "term_text": t.term_text,
                    "anchor_key": t.anchor_key,
                    "note_content": t.note_content,
                    "color": getattr(t, "color", "#ffe066")
                }
                for t in terms
            ]
        }

    def import_document_data(self, data: dict) -> Optional[Document]:
        if not isinstance(data, dict) or "title" not in data or "content" not in data:
            return None

        content = data["content"]
        raw_terms = data.get("terms", [])
        category = data.get("category", "Geral")
        card_color = data.get("card_color", "")
        remapped_terms = []

        for t in raw_terms:
            old_anchor = t.get("anchor_key", "")
            new_anchor = f"anc_{uuid.uuid4().hex[:8]}"
            term_text = t.get("term_text", "")
            note_content = t.get("note_content", "")
            color = t.get("color", "#ffe066")

            if old_anchor:
                content = re.sub(
                    rf'href=["\']anchor:{re.escape(old_anchor)}["\']',
                    f'href="anchor:{new_anchor}"',
                    content
                )
                content = content.replace(f"|{old_anchor}]]", f"|{new_anchor}]]")

            remapped_terms.append((term_text, new_anchor, note_content, color))

        new_doc = self.create_document(data["title"], content, category, card_color)
        for term_text, new_anchor, note_content, color in remapped_terms:
            self.add_term_note(new_doc.id, term_text, new_anchor, note_content, color)

        return new_doc

    def export_to_markdown(self, doc_id: str) -> Optional[str]:
        doc = self.get_document(doc_id)
        if not doc:
            return None

        terms = self.list_terms_for_document(doc_id)
        clean_text = TextParser.extract_body_inner(doc.content)
        clean_text = re.sub(
            r'<a\s+[^>]*href=["\']anchor:[^"\']+["\'][^>]*>(.*?)</a>',
            r"**\1**",
            clean_text,
            flags=re.DOTALL
        )
        clean_text = re.sub(r"</p>", "\n\n", clean_text, flags=re.IGNORECASE)
        clean_text = re.sub(r"<br\s*/?>", "\n", clean_text, flags=re.IGNORECASE)
        clean_text = re.sub(r"<[^>]+>", "", clean_text)
        clean_text = html.unescape(clean_text).replace("\xa0", " ").strip()

        md_lines = [
            f"# {doc.title}\n",
            f"*Categoria: {doc.category}*\n\n",
            clean_text,
            "\n\n---\n",
            "## 📌 Glossário e Notas de Estudo\n"
        ]

        if terms:
            for t in terms:
                md_lines.append(f"- **{t.term_text}**: {t.note_content}")
        else:
            md_lines.append("_Nenhum termo marcado neste documento._")

        return "\n".join(md_lines)