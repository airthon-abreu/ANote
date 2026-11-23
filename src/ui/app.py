import sys
import uuid
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QListWidget, QListWidgetItem, QTextBrowser, QPlainTextEdit,
    QLabel, QPushButton, QLineEdit, QTextEdit, QMessageBox, QStackedWidget,
    QInputDialog, QSpinBox, QColorDialog
)
from PySide6.QtCore import Qt, QUrl

from src.core.services import NotebookService
from src.core.parser import TextParser

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Caderno Interativo Offline")
        self.resize(1150, 720)

        self.service = NotebookService()
        self.current_document_id = None
        self.current_anchor_key = None

        # Carrega preferências com validação estrita (anti-crash)
        self.current_theme = self.service.get_theme("dark")
        self.font_size = self.service.get_font_size(15)
        default_color = "#cdd6f4" if self.current_theme == "dark" else "#1f2328"
        self.text_color = self.service.get_text_color(default_color)

        self._apply_theme(self.current_theme)
        self._setup_ui()
        self._load_documents()

    def _apply_theme(self, theme_name: str):
        # Whitelist estrita para prevenir Path Traversal
        if theme_name not in {"dark", "light"}:
            theme_name = "dark"

        self.current_theme = theme_name
        assets_dir = Path(__file__).resolve().parent / "assets"
        qss_file = assets_dir / f"{theme_name}.qss"
        if qss_file.exists():
            self.setStyleSheet(qss_file.read_text(encoding="utf-8"))
        self.service.set_setting("theme", theme_name)

    def _setup_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(8, 8, 8, 8)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)

        # COLUNA 1: Lista de Documentos
        col_docs = QWidget()
        layout_docs = QVBoxLayout(col_docs)
        layout_docs.addWidget(QLabel("<b>Meus Documentos</b>"))

        self.btn_new_doc = QPushButton("+ Novo Documento")
        self.btn_new_doc.clicked.connect(self._create_new_document)
        layout_docs.addWidget(self.btn_new_doc)

        self.list_docs = QListWidget()
        self.list_docs.itemClicked.connect(self._on_document_selected)
        layout_docs.addWidget(self.list_docs)

        splitter.addWidget(col_docs)

        # COLUNA 2: Centro (Texto & Customização)
        col_center = QWidget()
        layout_center = QVBoxLayout(col_center)

        # Barra 1: Ações do Documento
        bar_top = QHBoxLayout()
        self.input_doc_title = QLineEdit()
        self.input_doc_title.setPlaceholderText("Título do documento...")
        bar_top.addWidget(self.input_doc_title)

        self.btn_toggle_mode = QPushButton("Alternar p/ Modo Edição")
        self.btn_toggle_mode.clicked.connect(self._toggle_mode)
        bar_top.addWidget(self.btn_toggle_mode)

        self.btn_mark_term = QPushButton("★ Marcar Termo")
        self.btn_mark_term.setEnabled(False)
        self.btn_mark_term.clicked.connect(self._mark_selected_term)
        bar_top.addWidget(self.btn_mark_term)

        layout_center.addLayout(bar_top)

        # Barra 2: Formatação & Alternador de Tema
        bar_format = QHBoxLayout()
        bar_format.addWidget(QLabel("Fonte:"))

        self.spin_font_size = QSpinBox()
        self.spin_font_size.setRange(10, 40)
        self.spin_font_size.setValue(self.font_size)
        self.spin_font_size.valueChanged.connect(self._on_font_size_changed)
        bar_format.addWidget(self.spin_font_size)

        self.btn_text_color = QPushButton("🎨 Cor da Letra")
        self.btn_text_color.clicked.connect(self._choose_text_color)
        bar_format.addWidget(self.btn_text_color)

        bar_format.addStretch()

        theme_icon = "☀️ Modo Claro" if self.current_theme == "dark" else "🌙 Modo Escuro"
        self.btn_theme = QPushButton(theme_icon)
        self.btn_theme.clicked.connect(self._toggle_theme)
        bar_format.addWidget(self.btn_theme)

        layout_center.addLayout(bar_format)

        # Stack Leitor vs Editor
        self.stack_center = QStackedWidget()

        self.reader = QTextBrowser()
        self.reader.setOpenLinks(False)
        self.reader.anchorClicked.connect(self._on_anchor_clicked)
        self.stack_center.addWidget(self.reader)

        self.editor = QPlainTextEdit()
        self.stack_center.addWidget(self.editor)

        layout_center.addWidget(self.stack_center)
        splitter.addWidget(col_center)

        # COLUNA 3: Painel Lateral
        col_side = QWidget()
        layout_side = QVBoxLayout(col_side)
        layout_side.addWidget(QLabel("<b>Painel de Contexto / Nota</b>"))

        self.lbl_term_title = QLabel("<i>Nenhum termo selecionado</i>")
        self.lbl_term_title.setWordWrap(True)
        self.lbl_term_title.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout_side.addWidget(self.lbl_term_title)

        self.txt_term_note = QTextEdit()
        self.txt_term_note.setPlaceholderText("A anotação do termo aparecerá aqui...")
        layout_side.addWidget(self.txt_term_note)

        self.btn_save_note = QPushButton("Salvar Alteração na Nota")
        self.btn_save_note.setEnabled(False)
        self.btn_save_note.clicked.connect(self._save_note_changes)
        layout_side.addWidget(self.btn_save_note)

        splitter.addWidget(col_side)
        splitter.setSizes([220, 600, 280])

    # ==========================================
    # Customizações e Persistência
    # ==========================================

    def _toggle_theme(self):
        new_theme = "light" if self.current_theme == "dark" else "dark"
        self._apply_theme(new_theme)

        if new_theme == "light" and self.text_color == "#cdd6f4":
            self.text_color = "#1f2328"
            self.service.set_setting("text_color", self.text_color)
        elif new_theme == "dark" and self.text_color == "#1f2328":
            self.text_color = "#cdd6f4"
            self.service.set_setting("text_color", self.text_color)

        self.btn_theme.setText("☀️ Modo Claro" if new_theme == "dark" else "🌙 Modo Escuro")
        self._refresh_reader()

    def _on_font_size_changed(self, value: int):
        self.font_size = value
        self.service.set_setting("font_size", str(value))
        self._refresh_reader()

    def _choose_text_color(self):
        color = QColorDialog.getColor(title="Escolha a cor da letra")
        if color.isValid():
            self.text_color = color.name()
            self.service.set_setting("text_color", self.text_color)
            self._refresh_reader()

    def _refresh_reader(self):
        if not self.current_document_id:
            return
        doc = self.service.get_document(self.current_document_id)
        if doc:
            terms = self.service.list_terms_for_document(self.current_document_id)
            colors = {t.anchor_key: (getattr(t, 'color', None) or '#89b4fa') for t in terms}
            bg_color = "#181825" if self.current_theme == "dark" else "#ffffff"

            html_content = TextParser.to_html(
                doc.content,
                term_colors=colors,
                font_size=self.font_size,
                text_color=self.text_color,
                bg_color=bg_color
            )
            self.reader.setHtml(html_content)

        self.editor.setStyleSheet(f"font-size: {self.font_size}px; color: {self.text_color};")
        self.txt_term_note.setStyleSheet(f"font-size: {self.font_size}px; color: {self.text_color};")

    # ==========================================
    # Lógica de Documentos e Notas
    # ==========================================

    def _load_documents(self):
        self.list_docs.clear()
        docs = self.service.list_documents()
        for doc in docs:
            item = QListWidgetItem(doc.title)
            item.setData(Qt.ItemDataRole.UserRole, doc.id)
            self.list_docs.addItem(item)

        if docs:
            self.list_docs.setCurrentRow(0)
            self._load_document_data(docs[0].id)

    def _create_new_document(self):
        title, ok = QInputDialog.getText(self, "Novo Documento", "Título do documento:")
        if ok and title.strip():
            doc = self.service.create_document(title.strip(), "Cole ou digite seu texto aqui...")
            self._load_documents()
            for i in range(self.list_docs.count()):
                if self.list_docs.item(i).data(Qt.ItemDataRole.UserRole) == doc.id:
                    self.list_docs.setCurrentRow(i)
                    self._load_document_data(doc.id)
                    break

    def _on_document_selected(self, item: QListWidgetItem):
        doc_id = item.data(Qt.ItemDataRole.UserRole)
        self._load_document_data(doc_id)

    def _load_document_data(self, doc_id: str):
        doc = self.service.get_document(doc_id)
        if not doc:
            return

        self.current_document_id = doc.id
        self.input_doc_title.setText(doc.title)
        self.editor.setPlainText(doc.content)

        self._refresh_reader()

        self.lbl_term_title.setText("<i>Selecione um termo grifado</i>")
        self.txt_term_note.clear()
        self.btn_save_note.setEnabled(False)

    def _toggle_mode(self):
        if self.stack_center.currentIndex() == 0:
            self.stack_center.setCurrentIndex(1)
            self.btn_toggle_mode.setText("Salvar e Ir p/ Leitura")
            self.btn_mark_term.setEnabled(True)
        else:
            new_content = self.editor.toPlainText()
            new_title = self.input_doc_title.text().strip() or "Sem título"

            # Utiliza método desacoplado no service (sem SQL na UI)
            self.service.update_document(self.current_document_id, new_title, new_content)

            self.stack_center.setCurrentIndex(0)
            self.btn_toggle_mode.setText("Alternar p/ Modo Edição")
            self.btn_mark_term.setEnabled(False)

            self._refresh_reader()

            current_item = self.list_docs.currentItem()
            if current_item:
                current_item.setText(new_title)

    def _mark_selected_term(self):
        cursor = self.editor.textCursor()
        selected_text = cursor.selectedText().strip()

        if not selected_text:
            QMessageBox.warning(self, "Aviso", "Selecione uma palavra ou frase no texto para marcar.")
            return

        note_content, ok = QInputDialog.getMultiLineText(
            self, f"Anotação para: '{selected_text}'", "Digite o conceito/nota para este termo:"
        )

        if ok and note_content.strip():
            color = QColorDialog.getColor(title=f"Cor de destaque para: {selected_text}")
            highlight_color = color.name() if color.isValid() else "#89b4fa"

            anchor_key = f"anc_{uuid.uuid4().hex[:8]}"

            self.service.add_term_note(
                document_id=self.current_document_id,
                term_text=selected_text,
                anchor_key=anchor_key,
                note_content=note_content.strip(),
                color=highlight_color
            )

            token = f"[[{selected_text}|{anchor_key}]]"
            cursor.insertText(token)

            QMessageBox.information(self, "Sucesso", f"Termo '{selected_text}' marcado com sucesso!")

    def _on_anchor_clicked(self, url: QUrl):
        url_str = url.toString()
        if not url_str.startswith("anchor:"):
            return

        anchor_key = url_str.replace("anchor:", "")
        term = self.service.get_note_by_anchor(anchor_key)

        if term:
            self.current_anchor_key = term.anchor_key
            self.lbl_term_title.setText(f"Termo: {term.term_text}")
            self.txt_term_note.setPlainText(term.note_content)
            self.btn_save_note.setEnabled(True)

    def _save_note_changes(self):
        if not self.current_anchor_key:
            return

        new_note = self.txt_term_note.toPlainText().strip()
        # Utiliza método desacoplado no service (sem SQL na UI)
        self.service.update_term_note(self.current_anchor_key, new_note)
        QMessageBox.information(self, "Salvo", "Nota atualizada com sucesso no banco de dados!")


def run_app():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())