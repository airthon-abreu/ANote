import sys
import uuid
import json
import re
import ctypes
from ctypes import c_int, sizeof
from pathlib import Path
from typing import Dict

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QListWidget, QListWidgetItem, QTextBrowser, QTextEdit,
    QLabel, QPushButton, QLineEdit, QMessageBox, QStackedWidget,
    QInputDialog, QSpinBox, QColorDialog, QMenu, QDialog,
    QTableWidget, QTableWidgetItem, QHeaderView, QKeySequenceEdit,
    QFrame, QFileDialog
)
from PySide6.QtCore import Qt, QUrl, QPoint, QObject, QEvent, QMarginsF
from PySide6.QtGui import (
    QTextCursor, QTextCharFormat, QFont, QColor, QKeySequence, 
    QShortcut, QIcon, QTextDocument, QPdfWriter, QPageSize, QPageLayout
)

from src.core.services import NotebookService
from src.core.parser import TextParser

DEFAULT_SHORTCUTS = {
    "save_doc": ("Ctrl+S", "Salvar Documento Atual"),
    "undo": ("Ctrl+Z", "Desfazer Ação no Editor"),
    "redo": ("Ctrl+Shift+Z", "Refazer Ação no Editor"),
    "toggle_mode": ("Ctrl+E", "Alternar Leitura / Edição"),
    "mark_term": ("Ctrl+M", "Marcar Termo Selecionado"),
    "new_doc": ("Ctrl+N", "Criar Novo Documento"),
    "import_doc": ("Ctrl+O", "Importar Caderno (.json)"),
    "export_doc": ("Ctrl+Shift+S", "Exportar Documento (PDF/JSON/MD)"),
    "focus_search": ("Ctrl+F", "Focar na Barra de Pesquisa"),
    "bold": ("Ctrl+B", "Aplicar Negrito"),
    "italic": ("Ctrl+I", "Aplicar Itálico"),
    "underline": ("Ctrl+U", "Sublinhar Texto"),
    "toggle_left": ("Ctrl+1", "Recolher / Mostrar Painel Esquerdo"),
    "toggle_right": ("Ctrl+2", "Recolher / Mostrar Painel Direito"),
}

# Utilitário Nativo: Barra de Título Escura no Windows
def apply_windows_dark_titlebar(widget: QWidget, dark: bool = True):
    if sys.platform != "win32":
        return
    try:
        hwnd = int(widget.winId())
        val = c_int(1 if dark else 0)
        res = ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(val), sizeof(val))
        if res != 0:
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(val), sizeof(val))
    except Exception:
        pass


class WindowThemeFilter(QObject):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Show and isinstance(watched, QWidget) and watched.isWindow():
            is_dark = (self.main_window.current_theme == "dark")
            apply_windows_dark_titlebar(watched, is_dark)
        return super().eventFilter(watched, event)


# =========================================================================
# Janela Modal: Configurações de Atalhos
# =========================================================================
class SettingsDialog(QDialog):
    def __init__(self, service: NotebookService, parent=None):
        super().__init__(parent)
        self.service = service
        self.setWindowTitle("Configurações - Atalhos de Teclado")
        self.resize(620, 560)
        self.editor_widgets: Dict[str, QKeySequenceEdit] = {}

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        lbl_info = QLabel(
            "<b>Personalize os atalhos do teclado:</b><br>"
            "<small style='color: #89b4fa;'>Pressione as teclas no campo desejado. "
            "Para desativar um atalho, clique em 'Limpar'.</small>"
        )
        lbl_info.setWordWrap(True)
        layout.addWidget(lbl_info)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Ação", "Atalho Personalizado", ""])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 170)
        self.table.setColumnWidth(2, 95)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        layout.addWidget(self.table)

        self._populate_table()

        bar_actions = QHBoxLayout()
        btn_reset = QPushButton("Restaurar Padrões")
        btn_reset.clicked.connect(self._reset_defaults)
        bar_actions.addWidget(btn_reset)

        bar_actions.addStretch()

        btn_save = QPushButton("Salvar Configurações")
        btn_save.clicked.connect(self._save_and_close)
        bar_actions.addWidget(btn_save)

        layout.addLayout(bar_actions)

    def _populate_table(self):
        self.table.setRowCount(len(DEFAULT_SHORTCUTS))
        for row, (action_key, (default_seq, description)) in enumerate(DEFAULT_SHORTCUTS.items()):
            item_desc = QTableWidgetItem(f"  {description}")
            item_desc.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.table.setItem(row, 0, item_desc)

            current_seq = self.service.get_setting(f"shortcut_{action_key}", default_seq)
            key_edit = QKeySequenceEdit(QKeySequence(current_seq))
            key_edit.setFixedHeight(30)
            self.editor_widgets[action_key] = key_edit
            self.table.setCellWidget(row, 1, key_edit)

            btn_clear = QPushButton("Limpar")
            btn_clear.setFixedHeight(28)
            btn_clear.clicked.connect(lambda _, ke=key_edit: ke.clear())
            self.table.setCellWidget(row, 2, btn_clear)

    def _reset_defaults(self):
        for action_key, (default_seq, _) in DEFAULT_SHORTCUTS.items():
            if action_key in self.editor_widgets:
                self.editor_widgets[action_key].setKeySequence(QKeySequence(default_seq))

    def _save_and_close(self):
        for action_key, key_edit in self.editor_widgets.items():
            seq_text = key_edit.keySequence().toString()
            self.service.set_setting(f"shortcut_{action_key}", seq_text)
        self.accept()


# =========================================================================
# Janela Principal
# =========================================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ANote")
        self.resize(1280, 780)

        self.service = NotebookService()
        self.current_document_id = None
        self.current_anchor_key = None
        self.registered_shortcuts = []

        self.current_theme = self.service.get_theme("dark")
        self.font_size = self.service.get_font_size(15)
        default_color = "#cdd6f4" if self.current_theme == "dark" else "#1f2328"
        self.text_color = self.service.get_text_color(default_color)

        self._setup_ui()
        self._apply_theme(self.current_theme)
        self._bind_shortcuts()
        self._load_documents()

    def _apply_theme(self, theme_name: str):
        if theme_name not in {"dark", "light"}:
            theme_name = "dark"

        self.current_theme = theme_name
        assets_dir = Path(__file__).resolve().parent / "assets"
        qss_file = assets_dir / f"{theme_name}.qss"
        if qss_file.exists():
            self.setStyleSheet(qss_file.read_text(encoding="utf-8"))
        self.service.set_setting("theme", theme_name)
        apply_windows_dark_titlebar(self, dark=(theme_name == "dark"))

    def _create_separator(self):
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setFixedHeight(24)
        line.setStyleSheet("color: #45475a; margin: 0 4px;")
        return line

    def _get_shortcut(self, action_key: str) -> str:
        default_seq = DEFAULT_SHORTCUTS[action_key][0]
        return self.service.get_setting(f"shortcut_{action_key}", default_seq)

    def _bind_shortcuts(self):
        for sc in self.registered_shortcuts:
            sc.setEnabled(False)
            sc.deleteLater()
        self.registered_shortcuts.clear()

        actions_map = {
            "save_doc": self._save_current_document,
            "undo": self.editor.undo,
            "redo": self.editor.redo,
            "toggle_mode": self._toggle_mode,
            "mark_term": self._mark_selected_term,
            "new_doc": self._create_new_document,
            "import_doc": self._import_document,
            "export_doc": self._export_current_document,
            "focus_search": self.input_search.setFocus,
            "bold": self._format_bold,
            "italic": self._format_italic,
            "underline": self._format_underline,
            "toggle_left": self._toggle_left_panel,
            "toggle_right": self._toggle_right_panel,
        }

        for action_key, handler in actions_map.items():
            key_seq = self._get_shortcut(action_key)
            if key_seq.strip():
                shortcut = QShortcut(QKeySequence(key_seq), self)
                shortcut.activated.connect(handler)
                self.registered_shortcuts.append(shortcut)

        redo_alt = QShortcut(QKeySequence("Ctrl+Y"), self.editor)
        redo_alt.activated.connect(self.editor.redo)
        self.registered_shortcuts.append(redo_alt)

        self._update_all_tooltips()

    def _setup_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(6, 4, 6, 6)
        main_layout.setSpacing(6)

        # 1. Componentes Centrais
        self.reader = QTextBrowser()
        self.reader.setOpenLinks(False)
        self.reader.anchorClicked.connect(self._on_anchor_clicked)

        self.editor = QTextEdit()
        # Detecta quando o cursor se posiciona sobre um termo marcado no modo de edição
        self.editor.cursorPositionChanged.connect(self._on_editor_cursor_moved)

        self.stack_center = QStackedWidget()
        self.stack_center.addWidget(self.reader)
        self.stack_center.addWidget(self.editor)

        # 2. Barra Superior Unificada (46px)
        top_toolbar = QWidget()
        top_toolbar.setFixedHeight(46)
        layout_toolbar = QHBoxLayout(top_toolbar)
        layout_toolbar.setContentsMargins(4, 2, 4, 2)
        layout_toolbar.setSpacing(5)

        self.btn_toggle_left = QPushButton("◧ Cadernos")
        self.btn_toggle_left.clicked.connect(self._toggle_left_panel)
        layout_toolbar.addWidget(self.btn_toggle_left)

        layout_toolbar.addWidget(self._create_separator())

        self.btn_new_doc = QPushButton("📄 Novo")
        self.btn_new_doc.clicked.connect(self._create_new_document)
        layout_toolbar.addWidget(self.btn_new_doc)

        self.btn_save = QPushButton("💾 Salvar")
        self.btn_save.clicked.connect(self._save_current_document)
        layout_toolbar.addWidget(self.btn_save)

        self.btn_import = QPushButton("📥 Importar")
        self.btn_import.clicked.connect(self._import_document)
        layout_toolbar.addWidget(self.btn_import)

        self.btn_export = QPushButton("📤 Exportar")
        self.btn_export.clicked.connect(self._export_current_document)
        layout_toolbar.addWidget(self.btn_export)

        layout_toolbar.addWidget(self._create_separator())

        self.btn_undo = QPushButton("↩ Desfazer")
        self.btn_undo.clicked.connect(self.editor.undo)
        layout_toolbar.addWidget(self.btn_undo)

        self.btn_redo = QPushButton("↪ Refazer")
        self.btn_redo.clicked.connect(self.editor.redo)
        layout_toolbar.addWidget(self.btn_redo)

        layout_toolbar.addWidget(self._create_separator())

        self.btn_toggle_mode = QPushButton("✏️ Modo Edição")
        self.btn_toggle_mode.clicked.connect(self._toggle_mode)
        layout_toolbar.addWidget(self.btn_toggle_mode)

        self.btn_mark_term = QPushButton("★ Marcar Termo")
        self.btn_mark_term.setEnabled(False)
        self.btn_mark_term.clicked.connect(self._mark_selected_term)
        layout_toolbar.addWidget(self.btn_mark_term)

        layout_toolbar.addWidget(self._create_separator())

        self.btn_bold = QPushButton("B")
        self.btn_bold.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.btn_bold.setFixedWidth(32)
        self.btn_bold.clicked.connect(self._format_bold)
        layout_toolbar.addWidget(self.btn_bold)

        self.btn_italic = QPushButton("I")
        f_italic = QFont("Segoe UI", 10)
        f_italic.setItalic(True)
        self.btn_italic.setFont(f_italic)
        self.btn_italic.setFixedWidth(32)
        self.btn_italic.clicked.connect(self._format_italic)
        layout_toolbar.addWidget(self.btn_italic)

        self.btn_underline = QPushButton("U")
        f_und = QFont("Segoe UI", 10)
        f_und.setUnderline(True)
        self.btn_underline.setFont(f_und)
        self.btn_underline.setFixedWidth(32)
        self.btn_underline.clicked.connect(self._format_underline)
        layout_toolbar.addWidget(self.btn_underline)

        self.spin_font_size = QSpinBox()
        self.spin_font_size.setRange(10, 48)
        self.spin_font_size.setValue(self.font_size)
        self.spin_font_size.valueChanged.connect(self._on_font_size_changed)
        layout_toolbar.addWidget(self.spin_font_size)

        self.btn_color_selection = QPushButton("🎨 Cor")
        self.btn_color_selection.clicked.connect(self._format_color_selection)
        layout_toolbar.addWidget(self.btn_color_selection)

        layout_toolbar.addStretch()

        self.btn_theme = QPushButton("☀️ Claro")
        self.btn_theme.clicked.connect(self._toggle_theme)
        layout_toolbar.addWidget(self.btn_theme)

        self.btn_settings = QPushButton("⚙️ Atalhos")
        self.btn_settings.clicked.connect(self._open_settings_dialog)
        layout_toolbar.addWidget(self.btn_settings)

        layout_toolbar.addWidget(self._create_separator())

        self.btn_toggle_right = QPushButton("◨ Notas")
        self.btn_toggle_right.clicked.connect(self._toggle_right_panel)
        layout_toolbar.addWidget(self.btn_toggle_right)

        main_layout.addWidget(top_toolbar, 0)

        # 3. Área de Trabalho Dividida
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.splitter, 1)

        # Painel Esquerdo: Lista de Documentos
        self.col_docs = QWidget()
        layout_docs = QVBoxLayout(self.col_docs)
        layout_docs.setContentsMargins(2, 2, 2, 2)
        layout_docs.addWidget(QLabel("<b>Cadernos / Páginas</b>"))

        self.input_search = QLineEdit()
        self.input_search.setPlaceholderText("🔍 Pesquisar documentos...")
        self.input_search.textChanged.connect(self._filter_documents)
        layout_docs.addWidget(self.input_search)

        self.list_docs = QListWidget()
        self.list_docs.itemClicked.connect(self._on_document_selected)
        self.list_docs.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_docs.customContextMenuRequested.connect(self._show_document_context_menu)
        layout_docs.addWidget(self.list_docs)

        self.splitter.addWidget(self.col_docs)

        # Painel Central: Folha de Conteúdo
        self.col_center = QWidget()
        layout_center = QVBoxLayout(self.col_center)
        layout_center.setContentsMargins(2, 2, 2, 2)

        self.input_doc_title = QLineEdit()
        self.input_doc_title.setPlaceholderText("Título do caderno...")
        self.input_doc_title.setStyleSheet("font-size: 15px; font-weight: bold; padding: 6px;")
        layout_center.addWidget(self.input_doc_title)

        layout_center.addWidget(self.stack_center)
        self.splitter.addWidget(self.col_center)

        # Painel Direito: Anotações de Contexto e Customização do Termo
        self.col_side = QWidget()
        layout_side = QVBoxLayout(self.col_side)
        layout_side.setContentsMargins(2, 2, 2, 2)
        layout_side.addWidget(QLabel("<b>Anotação de Contexto</b>"))

        self.lbl_term_title = QLabel("<i>Nenhum termo ativo</i>")
        self.lbl_term_title.setWordWrap(True)
        self.lbl_term_title.setStyleSheet("font-weight: bold; font-size: 14px; color: #89b4fa;")
        layout_side.addWidget(self.lbl_term_title)

        # Botão para alterar a cor da marcação sem remarcar o termo
        self.btn_change_term_color = QPushButton("🎨 Alterar Cor da Marcação")
        self.btn_change_term_color.setEnabled(False)
        self.btn_change_term_color.clicked.connect(self._change_active_term_color)
        layout_side.addWidget(self.btn_change_term_color)

        self.txt_term_note = QTextEdit()
        self.txt_term_note.setPlaceholderText("A nota do termo aparecerá aqui ao clicar...")
        layout_side.addWidget(self.txt_term_note)

        self.btn_save_note = QPushButton("Salvar Alteração na Nota")
        self.btn_save_note.setEnabled(False)
        self.btn_save_note.clicked.connect(self._save_note_changes)
        layout_side.addWidget(self.btn_save_note)

        self.splitter.addWidget(self.col_side)

        self.splitter.setCollapsible(0, True)
        self.splitter.setCollapsible(1, False)
        self.splitter.setCollapsible(2, True)
        self.splitter.setSizes([240, 740, 280])

    def _toggle_left_panel(self):
        self.col_docs.setVisible(not self.col_docs.isVisible())

    def _toggle_right_panel(self):
        self.col_side.setVisible(not self.col_side.isVisible())

    def _update_all_tooltips(self):
        k_save = self._get_shortcut("save_doc") or "Sem atalho"
        k_toggle = self._get_shortcut("toggle_mode") or "Sem atalho"
        k_mark = self._get_shortcut("mark_term") or "Sem atalho"
        k_new = self._get_shortcut("new_doc") or "Sem atalho"
        k_import = self._get_shortcut("import_doc") or "Sem atalho"
        k_export = self._get_shortcut("export_doc") or "Sem atalho"
        k_search = self._get_shortcut("focus_search") or "Sem atalho"
        k_undo = self._get_shortcut("undo") or "Sem atalho"
        k_redo = self._get_shortcut("redo") or "Sem atalho"
        k_bold = self._get_shortcut("bold") or "Sem atalho"
        k_italic = self._get_shortcut("italic") or "Sem atalho"
        k_und = self._get_shortcut("underline") or "Sem atalho"
        k_left = self._get_shortcut("toggle_left") or "Sem atalho"
        k_right = self._get_shortcut("toggle_right") or "Sem atalho"

        self.btn_toggle_left.setToolTip(f"<b>Painel Esquerdo:</b> Mostra ou recolhe a lista de cadernos.<br><i>Atalho: {k_left}</i>")
        self.btn_toggle_right.setToolTip(f"<b>Painel Direito:</b> Mostra ou recolhe o painel de notas.<br><i>Atalho: {k_right}</i>")
        self.btn_new_doc.setToolTip(f"<b>Novo Caderno:</b> Cria uma nova página de estudo.<br><i>Atalho: {k_new}</i>")
        self.btn_save.setToolTip(f"<b>Salvar:</b> Grava as alterações do texto no banco SQLite.<br><i>Atalho: {k_save}</i>")
        self.btn_import.setToolTip(f"<b>Importar:</b> Carrega um arquivo de caderno (.json).<br><i>Atalho: {k_import}</i>")
        self.btn_export.setToolTip(f"<b>Exportar:</b> Salva em PDF paginado, Markdown ou JSON.<br><i>Atalho: {k_export}</i>")
        self.btn_undo.setToolTip(f"<b>Desfazer:</b> Reverte a última ação de texto.<br><i>Atalho: {k_undo}</i>")
        self.btn_redo.setToolTip(f"<b>Refazer:</b> Reaplica a última ação desfeita.<br><i>Atalho: {k_redo}</i>")
        self.btn_toggle_mode.setToolTip(f"<b>Alternar Modo:</b> Alterna entre Leitura Interativa e Edição Rica.<br><i>Atalho: {k_toggle}</i>")
        self.btn_mark_term.setToolTip(f"<b>Marcar Termo:</b> Associa uma anotação lateral ao trecho selecionado.<br><i>Atalho: {k_mark}</i>")
        self.btn_change_term_color.setToolTip("<b>Alterar Cor:</b> Muda a cor de destaque do termo selecionado sem precisar remarcar.")
        self.btn_bold.setToolTip(f"<b>Negrito:</b> Aplica negrito ao texto selecionado.<br><i>Atalho: {k_bold}</i>")
        self.btn_italic.setToolTip(f"<b>Itálico:</b> Aplica itálico ao texto selecionado.<br><i>Atalho: {k_italic}</i>")
        self.btn_underline.setToolTip(f"<b>Sublinhado:</b> Sublinha o texto selecionado.<br><i>Atalho: {k_und}</i>")
        self.spin_font_size.setToolTip("<b>Tamanho da Fonte:</b> Modifica o tamanho do texto da folha ou seleção.")
        self.btn_color_selection.setToolTip("<b>Cor do Texto:</b> Aplica uma cor específica na seleção de texto.")
        self.input_search.setToolTip(f"<b>Pesquisar:</b> Filtra cadernos pelo título em tempo real.<br><i>Atalho: {k_search}</i>")
        self.list_docs.setToolTip("<b>Navegador:</b> Clique para abrir. Use o botão direito para Renomear, Duplicar, Exportar ou Excluir.")
        self.btn_theme.setToolTip("<b>Tema:</b> Alterna entre Modo Escuro e Modo Claro.")
        self.btn_settings.setToolTip("<b>Configurações:</b> Personalize os atalhos de teclado do aplicativo.")

    # ==========================================
    # Edição Dinâmica de Termos (Modo Leitura e Edição)
    # ==========================================

    def _on_editor_cursor_moved(self):
        """Detecta quando o cursor no editor toca em um termo marcado e ativa o painel lateral."""
        if self.stack_center.currentIndex() != 1:
            return

        cursor = self.editor.textCursor()
        fmt = cursor.charFormat()
        href = fmt.anchorHref()

        if href and href.startswith("anchor:"):
            anchor_key = href.replace("anchor:", "")
            self._load_active_term(anchor_key)

    def _load_active_term(self, anchor_key: str):
        term = self.service.get_note_by_anchor(anchor_key)
        if term:
            if not self.col_side.isVisible():
                self.col_side.setVisible(True)

            self.current_anchor_key = term.anchor_key
            self.lbl_term_title.setText(f"Termo: {term.term_text}")
            self.txt_term_note.setPlainText(term.note_content)
            self.btn_save_note.setEnabled(True)
            self.btn_change_term_color.setEnabled(True)

    def _change_active_term_color(self):
        """Altera a cor do termo ativo diretamente no banco e atualiza o texto na hora."""
        if not self.current_anchor_key:
            return

        term = self.service.get_note_by_anchor(self.current_anchor_key)
        if not term:
            return

        color = QColorDialog.getColor(title=f"Escolha a nova cor para: {term.term_text}")
        if color.isValid():
            new_color = color.name()
            # 1. Atualiza no banco
            self.service.update_term_color(self.current_anchor_key, new_color)

            # 2. Atualiza no editor e no leitor em tempo real
            self._refresh_views()
            doc = self.service.get_document(self.current_document_id)
            if doc:
                terms = self.service.list_terms_for_document(self.current_document_id)
                colors = {t.anchor_key: (getattr(t, 'color', None) or '#89b4fa') for t in terms}
                clean_content = TextParser.clean_legacy_tokens(doc.content, colors)
                self.editor.setHtml(clean_content)

            QMessageBox.information(self, "Sucesso", f"Cor do termo '{term.term_text}' atualizada!")

    # ==========================================
    # Funções de Importação e Exportação (PDF / JSON / MD)
    # ==========================================

    def _import_document(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Importar Caderno", "", "Caderno Interativo (*.json)"
        )
        if not file_path:
            return

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            new_doc = self.service.import_document_data(data)
            if new_doc:
                self._load_documents()
                self._select_document_by_id(new_doc.id)
                QMessageBox.information(self, "Sucesso", f"Caderno '{new_doc.title}' importado com sucesso!")
            else:
                QMessageBox.warning(self, "Erro", "Arquivo inválido ou corrompido.")
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Falha ao importar caderno:\n{e}")

    def _export_current_document(self):
        if not self.current_document_id:
            QMessageBox.warning(self, "Aviso", "Selecione um documento para exportar.")
            return

        menu = QMenu(self)
        action_pdf = menu.addAction("📄 Documento Formatado em PDF (.pdf)")
        action_json = menu.addAction("📦 Pacote Completo do Caderno (.json)")
        action_md = menu.addAction("📝 Documento Markdown com Glossário (.md)")

        selected = menu.exec(self.btn_export.mapToGlobal(QPoint(0, self.btn_export.height())))
        if selected == action_pdf:
            self._export_document_pdf(self.current_document_id)
        elif selected == action_json:
            self._export_document_json(self.current_document_id)
        elif selected == action_md:
            self._export_document_md(self.current_document_id)

    def _export_document_pdf(self, doc_id: str):
        doc = self.service.get_document(doc_id)
        if not doc:
            return

        safe_title = "".join(c for c in doc.title if c.isalnum() or c in (' ', '_', '-')).strip() or "documento"
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Exportar para PDF", f"{safe_title}.pdf", "Documento PDF (*.pdf)"
        )
        if not file_path:
            return

        try:
            printable_html = self.service.export_to_printable_html(doc_id)
            if not printable_html:
                return

            # Configura o gravador de PDF com margens proporcionadas de A4
            writer = QPdfWriter(file_path)
            writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
            writer.setResolution(96)  # Resolução padrão de renderização tipográfica do Qt
            writer.setPageMargins(QMarginsF(18, 18, 18, 18), QPageLayout.Unit.Millimeter)

            pdf_doc = QTextDocument()
            # Ajusta a largura do documento para casar com a área útil da página A4
            page_rect = writer.pageLayout().paintRectPixels(writer.resolution())
            pdf_doc.setTextWidth(page_rect.width())
            pdf_doc.setHtml(printable_html)

            pdf_doc.print_(writer)
            QMessageBox.information(self, "Sucesso", "Documento PDF gerado com sucesso!")
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Falha ao exportar PDF:\n{e}")

    def _export_document_json(self, doc_id: str):
        doc = self.service.get_document(doc_id)
        if not doc:
            return
        safe_title = "".join(c for c in doc.title if c.isalnum() or c in (' ', '_', '-')).strip() or "caderno"
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Exportar Caderno", f"{safe_title}.json", "Caderno Interativo (*.json)"
        )
        if file_path:
            data = self.service.export_document_data(doc_id)
            if data:
                Path(file_path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
                QMessageBox.information(self, "Sucesso", "Pacote do caderno exportado com sucesso!")

    def _export_document_md(self, doc_id: str):
        doc = self.service.get_document(doc_id)
        if not doc:
            return
        safe_title = "".join(c for c in doc.title if c.isalnum() or c in (' ', '_', '-')).strip() or "caderno"
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Exportar Markdown", f"{safe_title}.md", "Markdown (*.md)"
        )
        if file_path:
            content = self.service.export_to_markdown(doc_id)
            if content:
                Path(file_path).write_text(content, encoding="utf-8")
                QMessageBox.information(self, "Sucesso", "Documento Markdown exportado com sucesso!")

    # ==========================================
    # Lógica Geral e Controle
    # ==========================================

    def _open_settings_dialog(self):
        dlg = SettingsDialog(self.service, self)
        if dlg.exec():
            self._bind_shortcuts()
            QMessageBox.information(self, "Sucesso", "Atalhos atualizados com sucesso!")

    def _save_current_document(self):
        if not self.current_document_id:
            return

        new_title = self.input_doc_title.text().strip() or "Sem título"
        if self.stack_center.currentIndex() == 1:
            new_content = self.editor.toHtml()
        else:
            doc = self.service.get_document(self.current_document_id)
            new_content = doc.content if doc else ""

        self.service.update_document(self.current_document_id, new_title, new_content)

        current_item = self.list_docs.currentItem()
        if current_item:
            current_item.setText(new_title)

        self._refresh_views()
        self.statusBar().showMessage("✓ Documento salvo com sucesso!", 2500)

    def _filter_documents(self, text: str):
        query = text.strip().lower()
        for i in range(self.list_docs.count()):
            item = self.list_docs.item(i)
            item.setHidden(query not in item.text().lower())

    def _format_bold(self):
        cursor = self.editor.textCursor()
        fmt = QTextCharFormat()
        weight = QFont.Weight.Normal if cursor.charFormat().fontWeight() == QFont.Weight.Bold else QFont.Weight.Bold
        fmt.setFontWeight(weight)
        cursor.mergeCharFormat(fmt)

    def _format_italic(self):
        cursor = self.editor.textCursor()
        fmt = QTextCharFormat()
        fmt.setFontItalic(not cursor.charFormat().fontItalic())
        cursor.mergeCharFormat(fmt)

    def _format_underline(self):
        cursor = self.editor.textCursor()
        fmt = QTextCharFormat()
        fmt.setFontUnderline(not cursor.charFormat().fontUnderline())
        cursor.mergeCharFormat(fmt)

    def _format_color_selection(self):
        color = QColorDialog.getColor(title="Escolha a cor para o texto selecionado")
        if color.isValid():
            cursor = self.editor.textCursor()
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(color.name()))
            cursor.mergeCharFormat(fmt)

    def _on_font_size_changed(self, value: int):
        self.font_size = value
        self.service.set_setting("font_size", str(value))
        cursor = self.editor.textCursor()
        if cursor.hasSelection():
            fmt = QTextCharFormat()
            fmt.setFontPointSize(value)
            cursor.mergeCharFormat(fmt)
        else:
            self._refresh_views()

    def _show_document_context_menu(self, position: QPoint):
        item = self.list_docs.itemAt(position)
        if not item:
            return

        doc_id = item.data(Qt.ItemDataRole.UserRole)
        doc_title = item.text()

        menu = QMenu(self)
        action_rename = menu.addAction("✏️ Renomear")
        action_duplicate = menu.addAction("📄 Duplicar / Criar Cópia")
        menu.addSeparator()
        action_export_pdf = menu.addAction("📄 Exportar para PDF (.pdf)")
        action_export_json = menu.addAction("📦 Exportar Caderno (.json)")
        action_export_md = menu.addAction("📝 Exportar como Markdown (.md)")
        menu.addSeparator()
        action_delete = menu.addAction("🗑️ Excluir Documento")

        selected = menu.exec(self.list_docs.mapToGlobal(position))
        if selected == action_rename:
            new_title, ok = QInputDialog.getText(self, "Renomear Documento", "Novo título:", text=doc_title)
            if ok and new_title.strip() and new_title.strip() != doc_title:
                self.service.rename_document(doc_id, new_title.strip())
                item.setText(new_title.strip())
                if self.current_document_id == doc_id:
                    self.input_doc_title.setText(new_title.strip())
        elif selected == action_duplicate:
            new_doc = self.service.duplicate_document(doc_id)
            if new_doc:
                self._load_documents()
                self._select_document_by_id(new_doc.id)
        elif selected == action_export_pdf:
            self._export_document_pdf(doc_id)
        elif selected == action_export_json:
            self._export_document_json(doc_id)
        elif selected == action_export_md:
            self._export_document_md(doc_id)
        elif selected == action_delete:
            confirm = QMessageBox.question(
                self,
                "Confirmar Exclusão",
                f"Tem certeza que deseja excluir o documento:\n'{doc_title}'?\n\nTodas as notas vinculadas serão apagadas.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if confirm == QMessageBox.StandardButton.Yes:
                self.service.delete_document(doc_id)
                self._load_documents()

    def _select_document_by_id(self, doc_id: str):
        for i in range(self.list_docs.count()):
            if self.list_docs.item(i).data(Qt.ItemDataRole.UserRole) == doc_id:
                self.list_docs.setCurrentRow(i)
                self._load_document_data(doc_id)
                break

    def _toggle_theme(self):
        new_theme = "light" if self.current_theme == "dark" else "dark"
        self._apply_theme(new_theme)

        if new_theme == "light" and self.text_color == "#cdd6f4":
            self.text_color = "#1f2328"
            self.service.set_setting("text_color", self.text_color)
        elif new_theme == "dark" and self.text_color == "#1f2328":
            self.text_color = "#cdd6f4"
            self.service.set_setting("text_color", self.text_color)

        self.btn_theme.setText("☀️ Claro" if new_theme == "dark" else "🌙 Escuro")
        self._refresh_views()

    def _refresh_views(self):
        if not self.current_document_id:
            return
        doc = self.service.get_document(self.current_document_id)
        if doc:
            terms = self.service.list_terms_for_document(self.current_document_id)
            colors = {t.anchor_key: (getattr(t, 'color', None) or '#89b4fa') for t in terms}
            bg_color = "#181825" if self.current_theme == "dark" else "#ffffff"

            clean_content = TextParser.clean_legacy_tokens(doc.content, colors)
            styled_html = TextParser.wrap_in_page_style(
                clean_content,
                font_size=self.font_size,
                text_color=self.text_color,
                bg_color=bg_color
            )
            self.reader.setHtml(styled_html)

        self.txt_term_note.setStyleSheet(f"font-size: {self.font_size}px; color: {self.text_color};")
        self.btn_theme.setText("☀️ Claro" if self.current_theme == "dark" else "🌙 Escuro")

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
        else:
            self.current_document_id = None
            self.input_doc_title.clear()
            self.editor.clear()
            self.reader.clear()
            self.lbl_term_title.setText("<i>Nenhum documento aberto</i>")
            self.txt_term_note.clear()
            self.btn_save_note.setEnabled(False)
            self.btn_change_term_color.setEnabled(False)

    def _create_new_document(self):
        title, ok = QInputDialog.getText(self, "Novo Documento", "Título do documento:")
        if ok and title.strip():
            doc = self.service.create_document(title.strip(), "<p>Digite seu texto aqui...</p>")
            self._load_documents()
            self._select_document_by_id(doc.id)

    def _on_document_selected(self, item: QListWidgetItem):
        doc_id = item.data(Qt.ItemDataRole.UserRole)
        self._load_document_data(doc_id)

    def _load_document_data(self, doc_id: str):
        doc = self.service.get_document(doc_id)
        if not doc:
            return

        self.current_document_id = doc.id
        self.input_doc_title.setText(doc.title)

        terms = self.service.list_terms_for_document(self.current_document_id)
        colors = {t.anchor_key: (getattr(t, 'color', None) or '#89b4fa') for t in terms}
        clean_content = TextParser.clean_legacy_tokens(doc.content, colors)

        self.editor.setHtml(clean_content)
        self._refresh_views()

        self.lbl_term_title.setText("<i>Selecione um termo grifado</i>")
        self.txt_term_note.clear()
        self.btn_save_note.setEnabled(False)
        self.btn_change_term_color.setEnabled(False)

    def _toggle_mode(self):
        if not self.current_document_id:
            return

        if self.stack_center.currentIndex() == 0:
            self.stack_center.setCurrentIndex(1)
            self.btn_toggle_mode.setText("📖 Modo Leitura")
            self.btn_mark_term.setEnabled(True)
        else:
            new_content = self.editor.toHtml()
            new_title = self.input_doc_title.text().strip() or "Sem título"

            self.service.update_document(self.current_document_id, new_title, new_content)

            self.stack_center.setCurrentIndex(0)
            self.btn_toggle_mode.setText("✏️ Modo Edição")
            self.btn_mark_term.setEnabled(False)

            self._refresh_views()

            current_item = self.list_docs.currentItem()
            if current_item:
                current_item.setText(new_title)

    def _mark_selected_term(self):
        if not self.current_document_id:
            return

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

            html_link = (
                f'<a href="anchor:{anchor_key}" style="background-color: {highlight_color}; color: #11111b; '
                f'padding: 2px 6px; border-radius: 4px; text-decoration: none; font-weight: bold;">{selected_text}</a>'
            )
            cursor.insertHtml(html_link)

            # Ativa imediatamente o termo no painel lateral
            self._load_active_term(anchor_key)
            QMessageBox.information(self, "Sucesso", f"Termo '{selected_text}' marcado com sucesso!")

    def _on_anchor_clicked(self, url: QUrl):
        url_str = url.toString()
        if not url_str.startswith("anchor:"):
            return

        anchor_key = url_str.replace("anchor:", "")
        self._load_active_term(anchor_key)

    def _save_note_changes(self):
        if not self.current_anchor_key:
            return

        new_note = self.txt_term_note.toPlainText().strip()
        self.service.update_term_note(self.current_anchor_key, new_note)
        QMessageBox.information(self, "Salvo", "Nota atualizada com sucesso no banco de dados!")


def run_app():
    if sys.platform == "win32":
        try:
            myappid = "anote.desktop.app.1.0"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass

    app = QApplication(sys.argv)

    icon_path = Path(__file__).resolve().parent / "assets" / "icon.png"
    if icon_path.exists():
        app_icon = QIcon(str(icon_path))
        app.setWindowIcon(app_icon)

    window = MainWindow()
    if icon_path.exists():
        window.setWindowIcon(QIcon(str(icon_path)))

    theme_filter = WindowThemeFilter(window)
    app.installEventFilter(theme_filter)

    window.show()
    sys.exit(app.exec())