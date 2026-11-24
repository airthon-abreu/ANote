import re
from typing import List, Optional
from src.core.storage import Database
from src.core.models import Document, Term

class NotebookService:
    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()

    # --- Operações de Documento ---
    def update_term_color(self, anchor_key: str, new_color: str):
        """Atualiza apenas a cor de destaque de um termo existente."""
        with self.db.get_connection() as conn:
            conn.execute(
                "UPDATE terms SET color = ? WHERE anchor_key = ?",
                (new_color, anchor_key)
            )

    def export_to_printable_html(self, doc_id: str) -> Optional[str]:
        """Gera um layout de design editorial em A4 profissional para o PDF."""
        doc = self.get_document(doc_id)
        if not doc:
            return None

        terms = self.list_terms_for_document(doc_id)
        
        # 1. Limpa fontes em 'px' geradas pelo editor para não encolherem no PDF
        content = doc.content
        content = re.sub(r'font-size:\s*[^;"]+;?', '', content)
        content = re.sub(r'color:\s*#[0-9a-fA-F]+;?', '', content)  # Deixa o texto base escuro para impressão

        # 2. Converte termos para etiquetas coloridas de leitura
        for t in terms:
            badge = (
                f'<span style="background-color: {t.color}; color: #111111; '
                f'padding: 2px 6px; border-radius: 4px; font-weight: bold;">{t.term_text}</span>'
            )
            content = re.sub(rf'<a href="anchor:{t.anchor_key}"[^>]*>(.*?)</a>', badge, content)

        # 3. Monta a tabela de notas do glossário
        if terms:
            glossary_rows = "".join(
                f'''
                <tr>
                    <td style="width: 30%; font-weight: bold; padding: 10px; border-bottom: 1px solid #e2e8f0; vertical-align: top;">
                        <span style="background-color: {t.color}; color: #111; padding: 2px 6px; border-radius: 4px;">{t.term_text}</span>
                    </td>
                    <td style="width: 70%; padding: 10px; border-bottom: 1px solid #e2e8f0; color: #334155; line-height: 1.5; vertical-align: top;">
                        {t.note_content}
                    </td>
                </tr>
                '''
                for t in terms
            )
            glossary_section = f"""
            <div style="margin-top: 45px; page-break-inside: avoid;">
                <div style="background-color: #f1f5f9; padding: 12px 18px; border-radius: 6px; border-left: 4px solid #3b82f6; margin-bottom: 15px;">
                    <b style="font-size: 13pt; color: #1e293b;">📌 Glossário e Anotações de Estudo</b>
                </div>
                <table style="width: 100%; border-collapse: collapse; font-size: 10.5pt;">
                    {glossary_rows}
                </table>
            </div>
            """
        else:
            glossary_section = ""

        # 4. Template Completo do PDF em Folha A4
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{
                    font-family: "Segoe UI", Arial, Helvetica, sans-serif;
                    font-size: 11.5pt;
                    color: #1e293b;
                    line-height: 1.7;
                    margin: 0;
                    padding: 0;
                }}
                .header-box {{
                    border-bottom: 2px solid #0f172a;
                    padding-bottom: 12px;
                    margin-bottom: 25px;
                }}
                .doc-title {{
                    font-size: 22pt;
                    font-weight: 800;
                    color: #0f172a;
                    margin: 0 0 6px 0;
                }}
                .doc-meta {{
                    font-size: 9pt;
                    color: #64748b;
                }}
                p {{
                    margin: 0 0 14px 0;
                }}
            </style>
        </head>
        <body>
            <div class="header-box">
                <div class="doc-title">{doc.title}</div>
                <div class="doc-meta">Documento gerado via Caderno Interativo Offline</div>
            </div>
            
            <div class="main-content">
                {content}
            </div>

            {glossary_section}
        </body>
        </html>
        """

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

# ==========================================
    # Exportação e Importação
    # ==========================================

    def export_document_data(self, doc_id: str) -> Optional[dict]:
        """Gera um dicionário completo com o documento e todas as suas notas associadas."""
        doc = self.get_document(doc_id)
        if not doc:
            return None

        terms = self.list_terms_for_document(doc_id)
        return {
            "version": "1.0",
            "title": doc.title,
            "content": doc.content,
            "terms": [
                {
                    "term_text": t.term_text,
                    "anchor_key": t.anchor_key,
                    "note_content": t.note_content,
                    "color": getattr(t, 'color', '#89b4fa')
                }
                for t in terms
            ]
        }

    def import_document_data(self, data: dict) -> Optional[Document]:
        """Importa um documento, remapeando as âncoras para evitar conflitos de chaves únicas."""
        if "title" not in data or "content" not in data:
            return None

        content = data["content"]
        raw_terms = data.get("terms", [])
        remapped_terms = []

        # Remapeia âncoras antigas para novas chaves exclusivas
        for t in raw_terms:
            old_anchor = t.get("anchor_key", "")
            new_anchor = f"anc_{uuid.uuid4().hex[:8]}"
            term_text = t.get("term_text", "")
            note_content = t.get("note_content", "")
            color = t.get("color", "#89b4fa")

            if old_anchor:
                # Substitui tanto no formato HTML quanto no formato legado
                content = content.replace(f'anchor:{old_anchor}', f'anchor:{new_anchor}')
                content = content.replace(f'|{old_anchor}]]', f'|{new_anchor}]]')

            remapped_terms.append((term_text, new_anchor, note_content, color))

        # Cria o novo documento
        new_doc = self.create_document(data["title"], content)

        # Salva os termos vinculados com as novas chaves
        for term_text, new_anchor, note_content, color in remapped_terms:
            self.add_term_note(new_doc.id, term_text, new_anchor, note_content, color)

        return new_doc

    def export_to_markdown(self, doc_id: str) -> Optional[str]:
        """Gera um arquivo Markdown limpo com o texto e um glossário no final."""
        doc = self.get_document(doc_id)
        if not doc:
            return None

        terms = self.list_terms_for_document(doc_id)

        # Remove tags HTML simples mantendo quebras de linha
        clean_text = doc.content
        clean_text = re.sub(r'<a href="anchor:[^"]+"[^>]*>(.*?)</a>', r'**\1**', clean_text)
        clean_text = re.sub(r'</p>', '\n\n', clean_text)
        clean_text = re.sub(r'<[^>]+>', '', clean_text).strip()

        md_lines = [
            f"# {doc.title}\n",
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