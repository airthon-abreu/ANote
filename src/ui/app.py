import sys
import uuid
import json
import re
import html
import ctypes
from ctypes import c_int, sizeof
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, List

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QListWidget, QListWidgetItem, QTextBrowser, QTextEdit,
    QLabel, QPushButton, QLineEdit, QMessageBox, QStackedWidget,
    QInputDialog, QSpinBox, QColorDialog, QMenu, QDialog,
    QTableWidget, QTableWidgetItem, QHeaderView, QKeySequenceEdit,
    QFrame, QFileDialog, QComboBox, QToolButton, QFontComboBox
)
from PySide6.QtCore import Qt, QUrl, QPoint, QObject, QEvent, QMarginsF
from PySide6.QtGui import (
    QTextCursor, QTextCharFormat, QFont, QColor, QKeySequence, 
    QShortcut, QIcon, QTextDocument, QPdfWriter, QPageSize, QPageLayout,
    QCloseEvent, QBrush, QTextFormat, QTextOption, QDesktopServices
)

from src.core.services import NotebookService
from src.core.parser import TextParser
from src.core.models import Term

HIGHLIGHT_PRESETS = [
    ("#ffe066", "Amarelo"),
    ("#b7e4c7", "Verde Menta"),
    ("#a8dadc", "Azul Céu"),
    ("#ffcbf2", "Rosa"),
    ("#ffd1a9", "Laranja"),
    ("#e0c3fc", "Lilás"),
]

DEFAULT_SHORTCUTS = {
    "save_doc": ("Ctrl+S", "Salvar Documento Atual"),
    "undo": ("Ctrl+Z", "Desfazer no Editor"),
    "redo": ("Ctrl+Shift+Z", "Refazer no Editor"),
    "toggle_mode": ("Ctrl+E", "Alternar Leitura / Edição"),
    "mark_term": ("Ctrl+M", "Marcar Termo Selecionado"),
    "flashcards": ("Ctrl+P", "Praticar Flashcards"),
    "new_doc": ("Ctrl+N", "Novo Caderno"),
    "import_doc": ("Ctrl+O", "Importar Caderno (.json)"),
    "export_doc": ("Ctrl+Shift+S", "Exportar Caderno"),
    "focus_search": ("Ctrl+F", "Pesquisar Cadernos"),
    "bold": ("Ctrl+B", "Negrito"),
    "italic": ("Ctrl+I", "Itálico"),
    "underline": ("Ctrl+U", "Sublinhado"),
    "zen_mode": ("F11", "Modo Leitura Sem Distrações"),
    "toggle_left": ("Ctrl+1", "Mostrar/Ocultar Cadernos"),
    "toggle_right": ("Ctrl+2", "Mostrar/Ocultar Notas"),
}

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


class ColorPickerPopup(QDialog):
    def __init__(self, parent=None, term_label: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Escolha a Cor")
        self.selected_color = "#ffe066"
        self.setFixedSize(300, 160)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"<b>Cor de destaque para:</b><br><i>{term_label}</i>"))

        box_colors = QHBoxLayout()
        for hex_code, name in HIGHLIGHT_PRESETS:
            btn = QPushButton()
            btn.setFixedSize(36, 36)
            btn.setToolTip(name)
            btn.setStyleSheet(f"background-color: {hex_code}; border-radius: 18px; border: 2px solid #555;")
            btn.clicked.connect(lambda _, c=hex_code: self._pick(c))
            box_colors.addWidget(btn)

        layout.addLayout(box_colors)

        btn_custom = QPushButton("🎨 Outra cor...")
        btn_custom.clicked.connect(self._pick_custom)
        layout.addWidget(btn_custom)

    def _pick(self, color_hex: str):
        self.selected_color = color_hex
        self.accept()

    def _pick_custom(self):
        c = QColorDialog.getColor(title="Escolha uma cor personalizada", parent=self)
        if c.isValid():
            self.selected_color = c.name()
            self.accept()


class HistoryDialog(QDialog):
    def __init__(self, service: NotebookService, doc_id: str, parent=None):
        super().__init__(parent)
        self.service = service
        self.doc_id = doc_id
        self.restored_content = None

        self.setWindowTitle("Histórico de Modificações - ANote")
        self.resize(700, 480)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        layout.addWidget(QLabel("<b>Selecione uma versão anterior para restaurar:</b>"))

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(self.splitter, 1)

        self.list_history = QListWidget()
        self.list_history.itemClicked.connect(self._on_item_clicked)
        self.splitter.addWidget(self.list_history)

        self.preview = QTextBrowser()
        self.splitter.addWidget(self.preview)
        self.splitter.setSizes([260, 440])

        self.snapshots = self.service.list_history_snapshots(self.doc_id)
        for s in self.snapshots:
            item = QListWidgetItem(f"🕒 {s['saved_at']}")
            item.setData(Qt.ItemDataRole.UserRole, s["id"])
            self.list_history.addItem(item)

        bar_actions = QHBoxLayout()
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.clicked.connect(self.reject)
        bar_actions.addWidget(btn_cancel)

        bar_actions.addStretch()

        self.btn_restore = QPushButton("Restaurar Esta Versão")
        self.btn_restore.setEnabled(False)
        self.btn_restore.clicked.connect(self._restore_selected)
        bar_actions.addWidget(self.btn_restore)

        layout.addLayout(bar_actions)

        if self.snapshots:
            self.list_history.setCurrentRow(0)
            self._on_item_clicked(self.list_history.item(0))

    def _on_item_clicked(self, item: QListWidgetItem):
        hid = item.data(Qt.ItemDataRole.UserRole)
        snap = self.service.get_history_snapshot(hid)
        if snap:
            self.preview.setHtml(snap["content"])
            self.btn_restore.setEnabled(True)

    def _restore_selected(self):
        item = self.list_history.currentItem()
        if not item:
            return
        hid = item.data(Qt.ItemDataRole.UserRole)
        snap = self.service.get_history_snapshot(hid)
        if snap:
            self.restored_content = snap["content"]
            self.accept()


class FlashcardDialog(QDialog):
    def __init__(self, terms: List[Term], doc_title: str, parent=None):
        super().__init__(parent)
        self.terms = terms
        self.doc_title = doc_title
        self.current_idx = 0
        self.showing_answer = False

        self.setWindowTitle("Praticar Flashcards - ANote")
        self.resize(540, 390)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        self.lbl_counter = QLabel()
        self.lbl_counter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_counter.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(self.lbl_counter)

        self.card_frame = QFrame()
        self.card_frame.setStyleSheet("""
            QFrame {
                border: 2px solid #313244;
                border-radius: 12px;
                padding: 20px;
            }
        """)
        card_layout = QVBoxLayout(self.card_frame)

        self.lbl_card_title = QLabel()
        self.lbl_card_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_card_title.setWordWrap(True)
        self.lbl_card_title.setStyleSheet("font-size: 20px; font-weight: bold; padding: 10px;")
        card_layout.addWidget(self.lbl_card_title)

        self.lbl_card_body = QLabel()
        self.lbl_card_body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_card_body.setWordWrap(True)
        self.lbl_card_body.setStyleSheet("font-size: 15px; line-height: 1.5; padding: 8px;")
        card_layout.addWidget(self.lbl_card_body)

        layout.addWidget(self.card_frame, 1)

        self.btn_flip = QPushButton("👀 Mostrar Anotação")
        self.btn_flip.setFixedHeight(42)
        self.btn_flip.setStyleSheet("font-size: 14px; font-weight: bold;")
        self.btn_flip.clicked.connect(self._toggle_flip)
        layout.addWidget(self.btn_flip)

        nav_layout = QHBoxLayout()
        self.btn_prev = QPushButton("← Anterior")
        self.btn_prev.clicked.connect(self._prev_card)
        nav_layout.addWidget(self.btn_prev)

        self.btn_next = QPushButton("Próximo →")
        self.btn_next.clicked.connect(self._next_card)
        nav_layout.addWidget(self.btn_next)

        layout.addLayout(nav_layout)
        self._update_card()

    def _update_card(self):
        if not self.terms:
            return
        t = self.terms[self.current_idx]
        self.lbl_counter.setText(f"Cartão {self.current_idx + 1} de {len(self.terms)}  •  {self.doc_title}")

        badge_style = f"background-color: {t.color}; color: #111; padding: 4px 10px; border-radius: 6px;"
        self.lbl_card_title.setText(f'<span style="{badge_style}">{html.escape(t.term_text)}</span>')

        if self.showing_answer:
            self.lbl_card_body.setText(html.escape(t.note_content))
            self.btn_flip.setText("🙈 Ocultar Anotação")
        else:
            self.lbl_card_body.setText("<i>(Pense no significado e clique para conferir)</i>")
            self.btn_flip.setText("👀 Mostrar Anotação")

        self.btn_prev.setEnabled(self.current_idx > 0)
        self.btn_next.setEnabled(self.current_idx < len(self.terms) - 1)

    def _toggle_flip(self):
        self.showing_answer = not self.showing_answer
        self._update_card()

    def _prev_card(self):
        if self.current_idx > 0:
            self.current_idx -= 1
            self.showing_answer = False
            self._update_card()

    def _next_card(self):
        if self.current_idx < len(self.terms) - 1:
            self.current_idx += 1
            self.showing_answer = False
            self._update_card()


class SettingsDialog(QDialog):
    def __init__(self, service: NotebookService, parent=None):
        super().__init__(parent)
        self.service = service
        self.setWindowTitle("Configurações - Atalhos de Teclado")
        self.resize(680, 580)
        self.editor_widgets: Dict[str, QKeySequenceEdit] = {}

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        lbl = QLabel("<b>Personalize seus atalhos:</b> Clique no campo e aperte as teclas desejadas.")
        layout.addWidget(lbl)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Ação", "Atalho", ""])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 180)
        self.table.setColumnWidth(2, 90)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        layout.addWidget(self.table)

        self._populate_table()

        bar = QHBoxLayout()
        btn_reset = QPushButton("Restaurar Padrões")
        btn_reset.clicked.connect(self._reset_defaults)
        bar.addWidget(btn_reset)
        bar.addStretch()
        btn_save = QPushButton("Salvar Configurações")
        btn_save.clicked.connect(self._save_and_close)
        bar.addWidget(btn_save)
        layout.addLayout(bar)

    def _populate_table(self):
        self.table.setRowCount(len(DEFAULT_SHORTCUTS))
        for row, (key, (default_seq, desc)) in enumerate(DEFAULT_SHORTCUTS.items()):
            item_desc = QTableWidgetItem(f"  {desc}")
            item_desc.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.table.setItem(row, 0, item_desc)

            current_seq = self.service.get_setting(f"shortcut_{key}", default_seq)
            kedit = QKeySequenceEdit(QKeySequence(current_seq))
            kedit.setFixedHeight(30)
            self.editor_widgets[key] = kedit
            self.table.setCellWidget(row, 1, kedit)

            b_clear = QPushButton("Limpar")
            b_clear.setFixedHeight(28)
            b_clear.clicked.connect(lambda _, ke=kedit: ke.clear())
            self.table.setCellWidget(row, 2, b_clear)

    def _reset_defaults(self):
        for k, (d_seq, _) in DEFAULT_SHORTCUTS.items():
            if k in self.editor_widgets:
                self.editor_widgets[k].setKeySequence(QKeySequence(d_seq))

    def _save_and_close(self):
        for k, ke in self.editor_widgets.items():
            self.service.set_setting(f"shortcut_{k}", ke.keySequence().toString())
        self.accept()


# =========================================================================
# Janela Principal
# =========================================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ANote - Caderno Interativo")
        self.resize(1300, 820)

        self.service = NotebookService()
        self.current_document_id: Optional[str] = None
        self.current_anchor_key: Optional[str] = None
        self.registered_shortcuts = []
        self._is_loading = False
        self._is_zen_mode = False

        self.document_cache: Dict[str, QTextDocument] = {}

        self.current_theme = self.service.get_theme("dark")
        self.font_size = self.service.get_font_size(15)
        default_color = "#cdd6f4" if self.current_theme == "dark" else "#1f2328"
        self.text_color = self.service.get_text_color(default_color)

        # 1. Constrói primeiro todos os componentes na tela
        self._setup_ui()

        # 2. Agora aplica temas, atalhos e carrega os cadernos
        self._apply_theme(self.current_theme)
        self._bind_shortcuts()
        self._load_categories()
        self._load_documents()

    def _apply_theme(self, theme_name: str):
        if theme_name not in {"dark", "light"}:
            theme_name = "dark"
        self.current_theme = theme_name
        qss_file = Path(__file__).resolve().parent / "assets" / f"{theme_name}.qss"
        if qss_file.exists():
            self.setStyleSheet(qss_file.read_text(encoding="utf-8"))
        self.service.set_setting("theme", theme_name)
        apply_windows_dark_titlebar(self, dark=(theme_name == "dark"))

        if hasattr(self, "lbl_term_title"):
            accent_color = "#89b4fa" if theme_name == "dark" else "#0969da"
            self.lbl_term_title.setStyleSheet(f"font-weight: bold; font-size: 14px; color: {accent_color};")

    def _create_separator(self):
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setFixedHeight(22)
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
            "flashcards": self._open_flashcards,
            "new_doc": self._create_new_document,
            "import_doc": self._import_document,
            "export_doc": self._export_current_document,
            "focus_search": self.input_search.setFocus,
            "bold": self._format_bold,
            "italic": self._format_italic,
            "underline": self._format_underline,
            "zen_mode": self._toggle_zen_mode,
            "toggle_left": self._toggle_left_panel,
            "toggle_right": self._toggle_right_panel,
        }

        for action_key, handler in actions_map.items():
            key_seq = self._get_shortcut(action_key)
            if key_seq.strip():
                shortcut = QShortcut(QKeySequence(key_seq), self)
                shortcut.activated.connect(handler)
                self.registered_shortcuts.append(shortcut)

        esc_shortcut = QShortcut(QKeySequence("Esc"), self)
        esc_shortcut.activated.connect(self._exit_zen_mode)
        self.registered_shortcuts.append(esc_shortcut)

    def _setup_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(6, 4, 6, 4)
        main_layout.setSpacing(6)

        # Leitor e Editor com Quebra Automática Obrigatória
        self.reader = QTextBrowser()
        self.reader.setOpenLinks(False)
        self.reader.anchorClicked.connect(self._on_anchor_clicked)
        self.reader.setLineWrapMode(QTextBrowser.LineWrapMode.WidgetWidth)
        self.reader.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.reader.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.editor = QTextEdit()
        self.editor.cursorPositionChanged.connect(self._on_editor_cursor_moved)
        self.editor.textChanged.connect(self._update_status_bar)
        self.editor.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.editor.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.editor.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.stack_center = QStackedWidget()
        self.stack_center.addWidget(self.reader)
        self.stack_center.addWidget(self.editor)

        # ---------------- Barra Superior Limpa ----------------
        self.top_toolbar = QWidget()
        self.top_toolbar.setFixedHeight(46)
        layout_toolbar = QHBoxLayout(self.top_toolbar)
        layout_toolbar.setContentsMargins(4, 2, 4, 2)
        layout_toolbar.setSpacing(6)

        self.btn_menu_file = QToolButton()
        self.btn_menu_file.setText("📁 Arquivo ▾")
        self.btn_menu_file.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu_file = QMenu(self)
        menu_file.addAction("📄 Novo Caderno", self._create_new_document)
        menu_file.addAction("💾 Salvar Alterações", self._save_current_document)
        menu_file.addSeparator()
        menu_file.addAction("🕒 Histórico de Versões", self._open_history_dialog)
        menu_file.addSeparator()
        menu_file.addAction("🛡️ Fazer Backup dos Dados...", self._backup_database)
        menu_file.addAction("🔄 Restaurar Backup (.db)...", self._restore_database)
        menu_file.addSeparator()
        menu_file.addAction("📥 Importar Caderno (.json)", self._import_document)
        menu_file.addAction("📤 Exportar para PDF / Markdown", self._export_current_document)
        self.btn_menu_file.setMenu(menu_file)
        layout_toolbar.addWidget(self.btn_menu_file)

        layout_toolbar.addWidget(self._create_separator())

        self.btn_toggle_mode = QPushButton("✏️ Modo Edição")
        self.btn_toggle_mode.clicked.connect(self._toggle_mode)
        layout_toolbar.addWidget(self.btn_toggle_mode)

        self.btn_mark_term = QPushButton("★ Marcar Termo")
        self.btn_mark_term.setEnabled(False)
        self.btn_mark_term.clicked.connect(self._mark_selected_term)
        layout_toolbar.addWidget(self.btn_mark_term)

        self.btn_flashcards = QPushButton("🃏 Praticar")
        self.btn_flashcards.clicked.connect(self._open_flashcards)
        layout_toolbar.addWidget(self.btn_flashcards)

        layout_toolbar.addWidget(self._create_separator())

        btn_format_css = "min-width: 30px; max-width: 30px; min-height: 28px; max-height: 28px; padding: 0px;"
        
        self.btn_bold = QPushButton("B")
        self.btn_bold.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.btn_bold.setStyleSheet(btn_format_css)
        self.btn_bold.clicked.connect(self._format_bold)
        layout_toolbar.addWidget(self.btn_bold)

        self.btn_italic = QPushButton("I")
        f_it = QFont("Segoe UI", 11)
        f_it.setItalic(True)
        self.btn_italic.setFont(f_it)
        self.btn_italic.setStyleSheet(btn_format_css)
        self.btn_italic.clicked.connect(self._format_italic)
        layout_toolbar.addWidget(self.btn_italic)

        self.btn_underline = QPushButton("U")
        f_und = QFont("Segoe UI", 11)
        f_und.setUnderline(True)
        self.btn_underline.setFont(f_und)
        self.btn_underline.setStyleSheet(btn_format_css)
        self.btn_underline.clicked.connect(self._format_underline)
        layout_toolbar.addWidget(self.btn_underline)

        self.btn_font_color = QPushButton("🎨 Cor")
        self.btn_font_color.setToolTip("Alterar cor das letras")
        self.btn_font_color.clicked.connect(self._format_font_color)
        layout_toolbar.addWidget(self.btn_font_color)

        self.btn_clear_bg = QPushButton("🧹 Limpar Fundo")
        self.btn_clear_bg.setToolTip("Remove a cor de fundo e restaura a letra natural da seleção")
        self.btn_clear_bg.clicked.connect(self._clear_selection_highlight)
        layout_toolbar.addWidget(self.btn_clear_bg)

        self.combo_font_family = QFontComboBox()
        self.combo_font_family.setToolTip("Escolha a fonte do texto")
        self.combo_font_family.setFixedWidth(140)
        self.combo_font_family.setCurrentFont(QFont("Segoe UI"))
        self.combo_font_family.currentFontChanged.connect(self._on_font_family_changed)
        layout_toolbar.addWidget(self.combo_font_family)

        self.spin_font_size = QSpinBox()
        self.spin_font_size.setRange(11, 40)
        self.spin_font_size.setValue(self.font_size)
        self.spin_font_size.setToolTip("Tamanho da fonte")
        self.spin_font_size.valueChanged.connect(self._on_font_size_changed)
        layout_toolbar.addWidget(self.spin_font_size)

        layout_toolbar.addStretch()

        self.btn_zen = QPushButton("🔲 Foco (F11)")
        self.btn_zen.clicked.connect(self._toggle_zen_mode)
        layout_toolbar.addWidget(self.btn_zen)

        self.btn_theme = QPushButton("☀️ Claro" if self.current_theme == "dark" else "🌙 Escuro")
        self.btn_theme.clicked.connect(self._toggle_theme)
        layout_toolbar.addWidget(self.btn_theme)

        self.btn_settings = QPushButton("⚙️ Atalhos")
        self.btn_settings.clicked.connect(self._open_settings_dialog)
        layout_toolbar.addWidget(self.btn_settings)

        main_layout.addWidget(self.top_toolbar, 0)

        # ---------------- Área Principal ----------------
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.splitter, 1)

        # Coluna Esquerda
        self.col_docs = QWidget()
        layout_docs = QVBoxLayout(self.col_docs)
        layout_docs.setContentsMargins(2, 2, 2, 2)
        layout_docs.setSpacing(6)

        header_left = QHBoxLayout()
        header_left.addWidget(QLabel("<b>Cadernos de Estudo</b>"))
        self.btn_collapse_left = QPushButton("❮")
        self.btn_collapse_left.setToolTip("Recolher Cadernos (Ctrl+1)")
        self.btn_collapse_left.setStyleSheet("font-size: 14px; font-weight: bold; min-width: 32px; max-width: 32px; min-height: 28px; max-height: 28px; padding: 0;")
        self.btn_collapse_left.clicked.connect(self._toggle_left_panel)
        header_left.addWidget(self.btn_collapse_left)
        layout_docs.addLayout(header_left)

        box_cat = QHBoxLayout()
        box_cat.addWidget(QLabel("Pasta:"))
        self.combo_categories = QComboBox()
        self.combo_categories.currentTextChanged.connect(self._on_category_filter_changed)
        box_cat.addWidget(self.combo_categories, 1)
        layout_docs.addLayout(box_cat)

        self.input_search = QLineEdit()
        self.input_search.setPlaceholderText("🔍 Pesquisar cadernos (Ctrl+F)...")
        self.input_search.textChanged.connect(self._filter_documents)
        layout_docs.addWidget(self.input_search)

        self.list_docs = QListWidget()
        self.list_docs.itemClicked.connect(self._on_document_selected)
        self.list_docs.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_docs.customContextMenuRequested.connect(self._show_document_context_menu)
        layout_docs.addWidget(self.list_docs)

        self.splitter.addWidget(self.col_docs)

        # Coluna Central
        self.col_center = QWidget()
        layout_center = QVBoxLayout(self.col_center)
        layout_center.setContentsMargins(2, 2, 2, 2)
        layout_center.setSpacing(6)

        box_header = QHBoxLayout()

        self.btn_expand_left = QPushButton("❯ Cadernos")
        self.btn_expand_left.setToolTip("Expandir Cadernos (Ctrl+1)")
        self.btn_expand_left.setVisible(False)
        self.btn_expand_left.setStyleSheet("font-weight: bold; padding: 4px 8px;")
        self.btn_expand_left.clicked.connect(self._toggle_left_panel)
        box_header.addWidget(self.btn_expand_left)

        self.input_doc_title = QLineEdit()
        self.input_doc_title.setPlaceholderText("Título do caderno...")
        self.input_doc_title.setStyleSheet("font-size: 16px; font-weight: bold; padding: 6px;")
        self.input_doc_title.returnPressed.connect(self._save_current_document)
        box_header.addWidget(self.input_doc_title, 1)

        self.lbl_category_badge = QPushButton("📁 Geral")
        self.lbl_category_badge.setToolTip("Alterar a pasta/categoria deste caderno")
        self.lbl_category_badge.clicked.connect(self._change_document_category)
        box_header.addWidget(self.lbl_category_badge)

        self.btn_expand_right = QPushButton("Notas ❮")
        self.btn_expand_right.setToolTip("Expandir Notas (Ctrl+2)")
        self.btn_expand_right.setVisible(False)
        self.btn_expand_right.setStyleSheet("font-weight: bold; padding: 4px 8px;")
        self.btn_expand_right.clicked.connect(self._toggle_right_panel)
        box_header.addWidget(self.btn_expand_right)

        layout_center.addLayout(box_header)
        layout_center.addWidget(self.stack_center)
        self.splitter.addWidget(self.col_center)

        # Coluna Direita
        self.col_side = QWidget()
        layout_side = QVBoxLayout(self.col_side)
        layout_side.setContentsMargins(2, 2, 2, 2)
        layout_side.setSpacing(6)

        header_right = QHBoxLayout()
        header_right.addWidget(QLabel("<b>Anotação de Contexto</b>"))
        self.btn_collapse_right = QPushButton("❯")
        self.btn_collapse_right.setToolTip("Recolher Notas (Ctrl+2)")
        self.btn_collapse_right.setStyleSheet("font-size: 14px; font-weight: bold; min-width: 32px; max-width: 32px; min-height: 28px; max-height: 28px; padding: 0;")
        self.btn_collapse_right.clicked.connect(self._toggle_right_panel)
        header_right.addWidget(self.btn_collapse_right)
        layout_side.addLayout(header_right)

        self.lbl_term_title = QLabel("<i>Nenhum termo ativo</i>")
        self.lbl_term_title.setWordWrap(True)
        layout_side.addWidget(self.lbl_term_title)

        box_actions = QHBoxLayout()
        self.btn_change_term_color = QPushButton("🎨 Caneta")
        self.btn_change_term_color.setEnabled(False)
        self.btn_change_term_color.clicked.connect(self._change_active_term_color)
        box_actions.addWidget(self.btn_change_term_color)

        self.btn_delete_term = QPushButton("🗑️ Desmarcar")
        self.btn_delete_term.setEnabled(False)
        self.btn_delete_term.setStyleSheet("color: #d20f39; font-weight: bold;")
        self.btn_delete_term.clicked.connect(self._delete_active_term)
        box_actions.addWidget(self.btn_delete_term)
        layout_side.addLayout(box_actions)

        self.txt_term_note = QTextEdit()
        self.txt_term_note.setPlaceholderText("A anotação do termo aparecerá aqui ao clicar...")
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

        self.statusBar().showMessage("Pronto para estudar!")

    def _toggle_left_panel(self):
        visible = not self.col_docs.isVisible()
        self.col_docs.setVisible(visible)
        self.btn_expand_left.setVisible(not visible)

    def _toggle_right_panel(self):
        visible = not self.col_side.isVisible()
        self.col_side.setVisible(visible)
        self.btn_expand_right.setVisible(not visible)

    def _toggle_zen_mode(self):
        self._is_zen_mode = not self._is_zen_mode
        if self._is_zen_mode:
            self.col_docs.setVisible(False)
            self.col_side.setVisible(False)
            self.top_toolbar.setVisible(False)
            self.btn_expand_left.setVisible(False)
            self.btn_expand_right.setVisible(False)
            self.showFullScreen()
            self.statusBar().showMessage("Modo Foco Ativado! Pressione F11 ou Esc para sair.", 4000)
        else:
            self._exit_zen_mode()

    def _exit_zen_mode(self):
        if self._is_zen_mode:
            self._is_zen_mode = False
            self.col_docs.setVisible(True)
            self.col_side.setVisible(True)
            self.top_toolbar.setVisible(True)
            self.btn_expand_left.setVisible(False)
            self.btn_expand_right.setVisible(False)
            self.showNormal()
            self.statusBar().showMessage("Modo Foco finalizado.", 2000)

    def _update_status_bar(self):
        if not self.current_document_id:
            return
        text = self.editor.toPlainText().strip()
        word_count = len(text.split()) if text else 0
        content = self.editor.toHtml()
        term_count = self.service.count_terms(self.current_document_id, content)
        self.statusBar().showMessage(f"📝 {word_count} palavras  •  🏷️ {term_count} conceitos destacados")

    def _load_categories(self):
        current_selection = self.combo_categories.currentText()
        self.combo_categories.blockSignals(True)
        self.combo_categories.clear()
        self.combo_categories.addItem("Todas")

        cats = self.service.list_categories()
        for c in cats:
            self.combo_categories.addItem(c)

        if current_selection in cats or current_selection == "Todas":
            self.combo_categories.setCurrentText(current_selection)
        else:
            self.combo_categories.setCurrentText("Todas")
        self.combo_categories.blockSignals(False)

    def _on_category_filter_changed(self):
        self._load_documents()

    def _change_document_category(self):
        if not self.current_document_id:
            return
        doc = self.service.get_document(self.current_document_id)
        if not doc:
            return

        new_cat, ok = QInputDialog.getText(
            self, "Categoria do Caderno", "Digite o nome da pasta/categoria:", text=doc.category
        )
        if ok and new_cat.strip():
            cat = new_cat.strip()
            self.service.update_document_category(self.current_document_id, cat)
            self.lbl_category_badge.setText(f"📁 {cat}")
            self._load_categories()
            self._load_documents()

    def _backup_database(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"notebook_backup_{timestamp}.db"

        backups_dir = Path(__file__).resolve().parent.parent.parent / "backups"
        backups_dir.mkdir(parents=True, exist_ok=True)
        default_target = str(backups_dir / default_name)

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar Cópia de Segurança (Backup)",
            default_target,
            "Banco de Dados SQLite (*.db)"
        )
        if not file_path:
            return

        try:
            if self.current_document_id and self.editor.document().isModified():
                self._save_current_document()

            saved_path = self.service.create_database_backup(Path(file_path))

            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Backup Concluído")
            msg_box.setText(f"<b>Cópia de segurança criada com sucesso!</b><br><br>Salvo em:<br><small>{saved_path}</small>")
            msg_box.setIcon(QMessageBox.Icon.Information)

            btn_open_folder = msg_box.addButton("Abrir Pasta", QMessageBox.ButtonRole.ActionRole)
            msg_box.addButton("OK", QMessageBox.ButtonRole.AcceptRole)

            msg_box.exec()
            if msg_box.clickedButton() == btn_open_folder:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(saved_path.parent)))

        except Exception as e:
            QMessageBox.critical(self, "Erro no Backup", f"Não foi possível gerar a cópia de segurança:\n{e}")

    def _restore_database(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Selecionar Arquivo de Backup para Restaurar",
            "",
            "Banco de Dados SQLite (*.db)"
        )
        if not file_path:
            return

        confirm = QMessageBox.warning(
            self,
            "Confirmar Restauração",
            "<b>ATENÇÃO:</b> Restaurar um backup substituirá todos os cadernos e anotações atuais pelos dados do arquivo selecionado.<br><br>Deseja continuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            success = self.service.restore_database_backup(Path(file_path))
            if success:
                self.document_cache.clear()
                self._load_categories()
                self._load_documents()
                QMessageBox.information(self, "Sucesso", "Banco de dados restaurado com sucesso!")
            else:
                QMessageBox.warning(self, "Arquivo Inválido", "O arquivo selecionado não é um backup compatível do ANote.")
        except Exception as e:
            QMessageBox.critical(self, "Erro na Restauração", f"Falha ao restaurar banco de dados:\n{e}")

    def _open_history_dialog(self):
        if not self.current_document_id:
            QMessageBox.information(self, "Aviso", "Selecione um caderno para ver seu histórico de versões.")
            return

        dlg = HistoryDialog(self.service, self.current_document_id, self)
        if dlg.exec() and dlg.restored_content:
            self.editor.setHtml(dlg.restored_content)
            self._save_current_document()
            QMessageBox.information(self, "Versão Restaurada", "O conteúdo da versão anterior foi restaurado com sucesso!")

    def _open_flashcards(self):
        if not self.current_document_id:
            QMessageBox.information(self, "Aviso", "Abra um caderno para praticar seus flashcards.")
            return

        content = self.editor.toHtml()
        self.service.clean_orphaned_terms(self.current_document_id, content)
        terms = self.service.list_terms_for_document(self.current_document_id)
        if not terms:
            QMessageBox.information(
                self, 
                "Nenhum termo marcado", 
                "Você ainda não grifou termos neste caderno!\n\nSelecione qualquer palavra no texto e clique em '★ Marcar Termo' para criar seu primeiro cartão de estudo."
            )
            return

        doc = self.service.get_document(self.current_document_id)
        dlg = FlashcardDialog(terms, doc.title if doc else "Caderno", self)
        dlg.exec()

    # ==========================================
    # Marcação Sem Alterar Família/Tamanho
    # ==========================================

    def _mark_selected_term(self):
        if not self.current_document_id:
            return

        cursor = self.editor.textCursor()
        selected_text = cursor.selectedText()

        if not selected_text.strip():
            QMessageBox.warning(self, "Aviso", "Selecione uma palavra ou trecho no texto com o mouse para grifar.")
            return

        clean_word = selected_text.strip()
        note_content, ok = QInputDialog.getMultiLineText(
            self, f"Anotação para: '{clean_word}'", "O que você quer lembrar sobre este termo?"
        )
        if ok and note_content.strip():
            picker = ColorPickerPopup(self, term_label=clean_word)
            if picker.exec():
                highlight_color = picker.selected_color
            else:
                highlight_color = "#ffe066"

            anchor_key = f"anc_{uuid.uuid4().hex[:8]}"
            self.service.add_term_note(
                document_id=self.current_document_id,
                term_text=clean_word,
                anchor_key=anchor_key,
                note_content=note_content.strip(),
                color=highlight_color
            )

            fmt = QTextCharFormat()
            fmt.setAnchor(True)
            fmt.setAnchorHref(f"anchor:{anchor_key}")
            fmt.setBackground(QColor(highlight_color))
            fmt.setForeground(QColor("#1e1e2e"))

            cursor.mergeCharFormat(fmt)
            cursor.clearSelection()
            self.editor.setTextCursor(cursor)

            self._save_current_document()
            self._load_active_term(anchor_key)

    def _change_active_term_color(self):
        if not self.current_anchor_key or not self.current_document_id:
            return

        term = self.service.get_note_by_anchor(self.current_anchor_key)
        if not term:
            return

        picker = ColorPickerPopup(self, term_label=term.term_text)
        if picker.exec():
            new_color = picker.selected_color
            self.service.update_term_color(self.current_document_id, self.current_anchor_key, new_color)

            doc = self.editor.document()
            block = doc.begin()
            target_href = f"anchor:{self.current_anchor_key}"
            while block.isValid():
                it = block.begin()
                while not it.atEnd():
                    frag = it.fragment()
                    if frag.isValid() and frag.charFormat().anchorHref() == target_href:
                        cur = QTextCursor(doc)
                        cur.setPosition(frag.position())
                        cur.setPosition(frag.position() + frag.length(), QTextCursor.MoveMode.KeepAnchor)
                        fmt = QTextCharFormat()
                        fmt.setBackground(QColor(new_color))
                        cur.mergeCharFormat(fmt)
                    it += 1
                block = block.next()

            self._save_current_document()
            self.statusBar().showMessage(f"Cor de '{term.term_text}' atualizada!", 2500)

    # ==========================================
    # Desmarcação Atômica sem Falhas
    # ==========================================

    def _delete_active_term(self):
        if not self.current_anchor_key or not self.current_document_id:
            return

        term = self.service.get_note_by_anchor(self.current_anchor_key)
        if not term:
            return

        confirm = QMessageBox.question(
            self,
            "Desmarcar Termo",
            f"Deseja remover o destaque e a anotação de '{term.term_text}'?\nO texto continuará na folha.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        doc = self.editor.document()
        block = doc.begin()
        target_href = f"anchor:{self.current_anchor_key}"
        default_color = QColor("#cdd6f4" if self.current_theme == "dark" else "#1f2328")

        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid():
                    fmt = frag.charFormat()
                    if fmt.isAnchor() and fmt.anchorHref() == target_href:
                        cur = QTextCursor(doc)
                        cur.setPosition(frag.position())
                        cur.setPosition(frag.position() + frag.length(), QTextCursor.MoveMode.KeepAnchor)

                        clean_fmt = QTextCharFormat()
                        clean_fmt.setFontWeight(fmt.fontWeight())
                        clean_fmt.setFontItalic(fmt.fontItalic())
                        clean_fmt.setFontUnderline(fmt.fontUnderline())
                        clean_fmt.setFontFamilies(fmt.fontFamilies())
                        if fmt.fontPointSize() > 0:
                            clean_fmt.setFontPointSize(fmt.fontPointSize())

                        clean_fmt.setAnchor(False)
                        clean_fmt.clearProperty(QTextFormat.Property.AnchorHref)
                        clean_fmt.setBackground(QBrush(Qt.BrushStyle.NoBrush))
                        clean_fmt.setForeground(default_color)

                        cur.setCharFormat(clean_fmt)
                it += 1
            block = block.next()

        self.service.delete_term(self.current_document_id, self.current_anchor_key)

        self._save_current_document()
        self._clear_active_term()
        self._update_status_bar()
        self.statusBar().showMessage("Termo desmarcado com sucesso!", 2500)

    def _clear_selection_highlight(self):
        if self.stack_center.currentIndex() != 1:
            self._toggle_mode()

        cursor = self.editor.textCursor()
        if not cursor.hasSelection():
            QMessageBox.information(self, "Aviso", "Selecione o trecho do texto com o mouse para limpar a cor de fundo.")
            return

        default_color = QColor("#cdd6f4" if self.current_theme == "dark" else "#1f2328")
        fmt = QTextCharFormat()
        fmt.setBackground(QBrush(Qt.BrushStyle.NoBrush))
        fmt.setAnchor(False)
        fmt.clearProperty(QTextFormat.Property.AnchorHref)
        fmt.setForeground(default_color)
        cursor.mergeCharFormat(fmt)

        self._save_current_document()
        self.statusBar().showMessage("Cor de fundo removida da seleção!", 2500)

    def _on_editor_cursor_moved(self):
        if self.stack_center.currentIndex() != 1:
            return
        cursor = self.editor.textCursor()
        href = cursor.charFormat().anchorHref()
        if href and href.startswith("anchor:"):
            self._load_active_term(href.replace("anchor:", ""))

    def _load_active_term(self, anchor_key: str):
        term = self.service.get_note_by_anchor(anchor_key)
        if term:
            if not self.col_side.isVisible():
                self._toggle_right_panel()

            self.current_anchor_key = term.anchor_key
            self.lbl_term_title.setText(f"Termo: {term.term_text}")
            self.txt_term_note.setPlainText(term.note_content)
            self.btn_save_note.setEnabled(True)
            self.btn_change_term_color.setEnabled(True)
            self.btn_delete_term.setEnabled(True)

    def _clear_active_term(self):
        self.current_anchor_key = None
        self.lbl_term_title.setText("<i>Nenhum termo ativo</i>")
        self.txt_term_note.clear()
        self.btn_save_note.setEnabled(False)
        self.btn_change_term_color.setEnabled(False)
        self.btn_delete_term.setEnabled(False)

    def _check_and_prompt_save_changes(self) -> bool:
        if self.stack_center.currentIndex() == 1 and self.editor.document().isModified() and self.current_document_id:
            doc = self.service.get_document(self.current_document_id)
            title = doc.title if doc else "Atual"

            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Alterações não salvas")
            msg_box.setText(f"Você fez alterações no caderno '<b>{html.escape(title)}</b>'.<br>Deseja salvá-las agora?")
            msg_box.setIcon(QMessageBox.Icon.Question)

            btn_save = msg_box.addButton("Salvar", QMessageBox.ButtonRole.AcceptRole)
            btn_discard = msg_box.addButton("Descartar", QMessageBox.ButtonRole.DestructiveRole)
            btn_cancel = msg_box.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
            msg_box.setDefaultButton(btn_save)

            msg_box.exec()
            clicked = msg_box.clickedButton()

            if clicked == btn_save:
                self._save_current_document()
                return True
            elif clicked == btn_discard:
                if doc:
                    self.editor.setHtml(doc.content)
                    self.editor.document().setModified(False)
                return True
            else:
                return False
        return True

    def closeEvent(self, event: QCloseEvent):
        if not self._check_and_prompt_save_changes():
            event.ignore()
        else:
            event.accept()

    def _on_document_selected(self, item: QListWidgetItem):
        if self._is_loading:
            return
        doc_id = item.data(Qt.ItemDataRole.UserRole)
        if doc_id == self.current_document_id:
            return
        if not self._check_and_prompt_save_changes():
            self._select_document_by_id(self.current_document_id)
            return
        self._load_document_data(doc_id)

    def _save_current_document(self):
        if not self.current_document_id:
            return
        new_title = self.input_doc_title.text().strip() or "Sem título"
        doc = self.service.get_document(self.current_document_id)
        cat = doc.category if doc else "Geral"

        new_content = self.editor.toHtml()

        self.service.update_document(self.current_document_id, new_title, new_content, cat)
        self.editor.document().setModified(False)

        current_item = self.list_docs.currentItem()
        if current_item:
            current_item.setText(new_title)

        self._refresh_views()
        self.statusBar().showMessage("✓ Caderno salvo com sucesso!", 2500)

    def _filter_documents(self, text: str):
        query = text.strip().lower()
        for i in range(self.list_docs.count()):
            item = self.list_docs.item(i)
            item.setHidden(query not in item.text().lower())

    def _format_bold(self):
        c = self.editor.textCursor()
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Weight.Normal if c.charFormat().fontWeight() == QFont.Weight.Bold else QFont.Weight.Bold)
        c.mergeCharFormat(fmt)

    def _format_italic(self):
        c = self.editor.textCursor()
        fmt = QTextCharFormat()
        fmt.setFontItalic(not c.charFormat().fontItalic())
        c.mergeCharFormat(fmt)

    def _format_underline(self):
        c = self.editor.textCursor()
        fmt = QTextCharFormat()
        fmt.setFontUnderline(not c.charFormat().fontUnderline())
        c.mergeCharFormat(fmt)

    def _format_font_color(self):
        color = QColorDialog.getColor(title="Escolha a cor para as letras", parent=self)
        if color.isValid():
            c = self.editor.textCursor()
            fmt = QTextCharFormat()
            fmt.setForeground(color)
            c.mergeCharFormat(fmt)

    def _on_font_family_changed(self, font: QFont):
        family = font.family()
        c = self.editor.textCursor()
        if c.hasSelection():
            fmt = QTextCharFormat()
            fmt.setFontFamilies([family])
            c.mergeCharFormat(fmt)
        else:
            self.editor.setFontFamily(family)

    def _on_font_size_changed(self, value: int):
        self.font_size = value
        self.service.set_setting("font_size", str(value))
        c = self.editor.textCursor()
        if c.hasSelection():
            fmt = QTextCharFormat()
            fmt.setFontPointSize(value)
            c.mergeCharFormat(fmt)
        else:
            f = self.editor.font()
            f.setPointSize(value)
            self.editor.setFont(f)
            self._refresh_views()

    def _show_document_context_menu(self, position: QPoint):
        item = self.list_docs.itemAt(position)
        if not item:
            return

        doc_id = item.data(Qt.ItemDataRole.UserRole)
        doc_title = item.text()

        menu = QMenu(self)
        menu.addAction("✏️ Renomear", lambda: self._rename_document_dialog(doc_id, doc_title, item))
        menu.addAction("📁 Mudar Categoria", self._change_document_category)
        menu.addAction("🕒 Histórico de Versões", self._open_history_dialog)
        menu.addAction("📄 Duplicar", lambda: self._duplicate_document_action(doc_id))
        menu.addSeparator()
        menu.addAction("📄 Exportar PDF", lambda: self._export_document_pdf(doc_id))
        menu.addAction("📝 Exportar Markdown", lambda: self._export_document_md(doc_id))
        menu.addSeparator()
        menu.addAction("🗑️ Excluir", lambda: self._delete_document_action(doc_id, doc_title))
        menu.exec(self.list_docs.mapToGlobal(position))

    def _rename_document_dialog(self, doc_id: str, old_title: str, item: QListWidgetItem):
        new_title, ok = QInputDialog.getText(self, "Renomear", "Novo título:", text=old_title)
        if ok and new_title.strip() and new_title.strip() != old_title:
            self.service.rename_document(doc_id, new_title.strip())
            item.setText(new_title.strip())
            if self.current_document_id == doc_id:
                self.input_doc_title.setText(new_title.strip())

    def _duplicate_document_action(self, doc_id: str):
        if not self._check_and_prompt_save_changes():
            return
        new_doc = self.service.duplicate_document(doc_id)
        if new_doc:
            self._load_documents()
            self._select_document_by_id(new_doc.id)

    def _delete_document_action(self, doc_id: str, title: str):
        res = QMessageBox.question(
            self, "Excluir", f"Deseja excluir o caderno '{title}'?\nTodas as anotações dele serão apagadas.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
        )
        if res == QMessageBox.StandardButton.Yes:
            if doc_id in self.document_cache:
                del self.document_cache[doc_id]
            self.service.delete_document(doc_id)
            if self.current_document_id == doc_id:
                self.current_document_id = None
            self._load_documents()

    def _select_document_by_id(self, doc_id: Optional[str]):
        if not doc_id:
            return
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
            colors = {t.anchor_key: (getattr(t, 'color', None) or '#ffe066') for t in terms}
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
        self._update_status_bar()

    def _load_documents(self):
        self._is_loading = True
        self.list_docs.clear()
        selected_cat = self.combo_categories.currentText()
        docs = self.service.list_documents(category_filter=selected_cat)

        for doc in docs:
            item = QListWidgetItem(doc.title)
            item.setData(Qt.ItemDataRole.UserRole, doc.id)
            self.list_docs.addItem(item)
        self._is_loading = False

        if docs:
            self.list_docs.setCurrentRow(0)
            self._load_document_data(docs[0].id)
        else:
            self.current_document_id = None
            self.input_doc_title.clear()
            self.lbl_category_badge.setText("📁 Geral")
            self.editor.clear()
            self.reader.clear()
            self._clear_active_term()
            self._update_status_bar()

    def _create_new_document(self):
        if not self._check_and_prompt_save_changes():
            return
        title, ok = QInputDialog.getText(self, "Novo Caderno", "Nome do caderno de estudo:")
        if ok and title.strip():
            cat = self.combo_categories.currentText()
            cat = "Geral" if cat == "Todas" else cat
            doc = self.service.create_document(title.strip(), "<p>Digite seu texto aqui...</p>", cat)
            self.input_search.clear()
            self._load_documents()
            self._select_document_by_id(doc.id)

    def _load_document_data(self, doc_id: str):
        doc = self.service.get_document(doc_id)
        if not doc:
            return

        self.current_document_id = doc.id
        self.input_doc_title.setText(doc.title)
        self.lbl_category_badge.setText(f"📁 {doc.category}")

        self.service.clean_orphaned_terms(doc_id, doc.content)

        if doc_id not in self.document_cache:
            qdoc = QTextDocument(self)
            opt = QTextOption()
            opt.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
            qdoc.setDefaultTextOption(opt)
            qdoc.setHtml(doc.content)
            qdoc.setModified(False)
            self.document_cache[doc_id] = qdoc
        else:
            opt = QTextOption()
            opt.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
            self.document_cache[doc_id].setDefaultTextOption(opt)

        self.editor.setDocument(self.document_cache[doc_id])
        self._refresh_views()
        self._clear_active_term()
        self._update_status_bar()

    def _toggle_mode(self):
        if not self.current_document_id:
            return

        if self.stack_center.currentIndex() == 0:
            self.stack_center.setCurrentIndex(1)
            self.btn_toggle_mode.setText("📖 Modo Leitura")
            self.btn_mark_term.setEnabled(True)
        else:
            if not self._check_and_prompt_save_changes():
                return
            self.stack_center.setCurrentIndex(0)
            self.btn_toggle_mode.setText("✏️ Modo Edição")
            self.btn_mark_term.setEnabled(False)
            self._refresh_views()

    def _on_anchor_clicked(self, url: QUrl):
        u = url.toString()
        if u.startswith("anchor:"):
            self._load_active_term(u.replace("anchor:", ""))

    def _save_note_changes(self):
        if not self.current_anchor_key:
            return
        self.service.update_term_note(self.current_anchor_key, self.txt_term_note.toPlainText().strip())
        self.statusBar().showMessage("✓ Anotação atualizada!", 2500)

    def _open_settings_dialog(self):
        dlg = SettingsDialog(self.service, self)
        if dlg.exec():
            self._bind_shortcuts()
            self.statusBar().showMessage("Atalhos atualizados com sucesso!", 3000)

    def _import_document(self):
        if not self._check_and_prompt_save_changes():
            return
        fpath, _ = QFileDialog.getOpenFileName(self, "Importar Caderno", "", "Caderno Interativo (*.json)")
        if not fpath:
            return
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            new_doc = self.service.import_document_data(data)
            if new_doc:
                self._load_categories()
                self._load_documents()
                self._select_document_by_id(new_doc.id)
                QMessageBox.information(self, "Sucesso", f"Caderno '{new_doc.title}' importado!")
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Falha ao importar caderno:\n{e}")

    def _export_current_document(self):
        if not self.current_document_id:
            QMessageBox.warning(self, "Aviso", "Selecione um caderno para exportar.")
            return

        menu = QMenu(self)
        menu.addAction("📄 Documento Formatado em PDF (.pdf)", lambda: self._export_document_pdf(self.current_document_id))
        menu.addAction("📦 Pacote Completo do Caderno (.json)", lambda: self._export_document_json(self.current_document_id))
        menu.addAction("📝 Documento Markdown com Glossário (.md)", lambda: self._export_document_md(self.current_document_id))
        menu.exec(self.btn_menu_file.mapToGlobal(QPoint(0, self.btn_menu_file.height())))

    def _export_document_pdf(self, doc_id: str):
        if self.stack_center.currentIndex() == 1:
            self._save_current_document()
        doc = self.service.get_document(doc_id)
        if not doc:
            return

        safe_title = "".join(c for c in doc.title if c.isalnum() or c in (' ', '_', '-')).strip() or "documento"
        fpath, _ = QFileDialog.getSaveFileName(self, "Exportar para PDF", f"{safe_title}.pdf", "Documento PDF (*.pdf)")
        if not fpath:
            return

        try:
            printable_html = self.service.export_to_printable_html(doc_id)
            if not printable_html:
                return

            writer = QPdfWriter(fpath)
            writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
            writer.setResolution(96)
            writer.setPageMargins(QMarginsF(18, 18, 18, 18), QPageLayout.Unit.Millimeter)

            pdf_doc = QTextDocument()
            page_rect = writer.pageLayout().paintRectPixels(writer.resolution())
            pdf_doc.setTextWidth(page_rect.width())
            pdf_doc.setHtml(printable_html)

            if hasattr(pdf_doc, "print"):
                pdf_doc.print(writer)
            else:
                pdf_doc.print_(writer)

            QMessageBox.information(self, "Sucesso", "Documento PDF gerado com sucesso!")
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Falha ao exportar PDF:\n{e}")

    def _export_document_json(self, doc_id: str):
        doc = self.service.get_document(doc_id)
        if not doc:
            return
        safe_title = "".join(c for c in doc.title if c.isalnum() or c in (' ', '_', '-')).strip() or "caderno"
        fpath, _ = QFileDialog.getSaveFileName(self, "Exportar Caderno", f"{safe_title}.json", "Caderno Interativo (*.json)")
        if fpath:
            data = self.service.export_document_data(doc_id)
            if data:
                Path(fpath).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
                QMessageBox.information(self, "Sucesso", "Pacote do caderno exportado!")

    def _export_document_md(self, doc_id: str):
        doc = self.service.get_document(doc_id)
        if not doc:
            return
        safe_title = "".join(c for c in doc.title if c.isalnum() or c in (' ', '_', '-')).strip() or "caderno"
        fpath, _ = QFileDialog.getSaveFileName(self, "Exportar Markdown", f"{safe_title}.md", "Markdown (*.md)")
        if fpath:
            content = self.service.export_to_markdown(doc_id)
            if content:
                Path(fpath).write_text(content, encoding="utf-8")
                QMessageBox.information(self, "Sucesso", "Documento Markdown exportado!")


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
        app.setWindowIcon(QIcon(str(icon_path)))

    window = MainWindow()
    if icon_path.exists():
        window.setWindowIcon(QIcon(str(icon_path)))

    theme_filter = WindowThemeFilter(window)
    app.installEventFilter(theme_filter)

    window.show()
    sys.exit(app.exec())