import ctypes
import html
import json
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QEvent, QMarginsF, QObject, QPoint, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QBrush,
    QCloseEvent,
    QColor,
    QCursor,
    QDesktopServices,
    QFont,
    QIcon,
    QKeySequence,
    QPageLayout,
    QPageSize,
    QPdfWriter,
    QShortcut,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextFormat,
    QTextOption,
)
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QComboBox,
    QFileDialog,
    QFontComboBox,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTextBrowser,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from config import BACKUPS_DIR, RESOURCE_DIR
from src.core.parser import TextParser
from src.core.services import NotebookService, extract_anchors_from_html
from src.ui.components import (
    DEFAULT_SHORTCUTS,
    CardColorDialog,
    ColorPickerPopup,
    FlashcardDialog,
    HistoryDialog,
    SettingsDialog,
    WindowThemeFilter,
    apply_windows_dark_titlebar,
    make_color_dot_icon,
    resolve_card_style,
)

ASSETS_DIR = RESOURCE_DIR / "src" / "ui" / "assets"


@dataclass
class UndoEntry:
    kind: str  # "editor_text" | "term_and_text" | "card_color" | "doc_title" | "doc_category" | "term_note"
    doc_id: str
    before: Any = None
    after: Any = None
    extra: Any = None


class MainWindow(QMainWindow):
    MAX_PAGE_WIDTH = 840

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ANote - Caderno Interativo")
        self.resize(1320, 840)

        self.service = NotebookService()
        self.current_document_id: Optional[str] = None
        self.current_anchor_key: Optional[str] = None
        self.registered_shortcuts: List[QShortcut] = []
        self._is_loading = False
        self._is_zen_mode = False
        self._pre_zen_left_visible = True
        self._pre_zen_right_visible = True
        self._current_category_filter = "Todas"

        self._loaded_title: str = ""
        self._loaded_note_text: str = ""
        self._suppress_undo_capture = False
        self._undo_stack: List[UndoEntry] = []
        self._redo_stack: List[UndoEntry] = []

        self.document_cache: Dict[str, QTextDocument] = {}

        self.current_theme = self.service.get_theme("dark")
        self.font_size = self.service.get_font_size(15)
        default_color = "#cdd6f4" if self.current_theme == "dark" else "#1f2328"
        self.text_color = self.service.get_text_color(default_color)

        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.setInterval(250)
        self._status_timer.timeout.connect(self._update_status_bar)

        self._setup_ui()
        self._apply_theme(self.current_theme)
        self._bind_shortcuts()
        self._update_shortcut_tooltips()
        self._load_categories()
        self._load_documents()
        self._update_undo_redo_buttons()
        self._update_page_margins()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_page_margins()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        txt_note = getattr(self, "txt_term_note", None)
        reader = getattr(self, "reader", None)
        editor = getattr(self, "editor", None)

        if txt_note is not None and watched is txt_note and event.type() == QEvent.Type.FocusOut:
            self._auto_save_note_if_needed()
        elif watched is not None and watched in (reader, editor) and event.type() == QEvent.Type.Resize:
            self._update_page_margins()
        return super().eventFilter(watched, event)

    def _update_page_margins(self):
        for attr in ("reader", "editor"):
            view = getattr(self, attr, None)
            if view is None:
                continue
            w = view.width()
            side = (w - self.MAX_PAGE_WIDTH) // 2 if w > self.MAX_PAGE_WIDTH + 48 else 12
            view.setViewportMargins(side, 12, side, 12)

    def _apply_theme(self, theme_name: str):
        if theme_name not in {"dark", "light"}:
            theme_name = "dark"
        self.current_theme = theme_name
        qss_file = ASSETS_DIR / f"{theme_name}.qss"
        if qss_file.exists():
            self.setStyleSheet(qss_file.read_text(encoding="utf-8"))
        self.service.set_setting("theme", theme_name)
        apply_windows_dark_titlebar(self, dark=(theme_name == "dark"))

        if hasattr(self, "lbl_term_title"):
            accent_color = "#89b4fa" if theme_name == "dark" else "#0969da"
            self.lbl_term_title.setStyleSheet(f"font-weight: bold; font-size: 14px; color: {accent_color};")

        if hasattr(self, "editor"):
            self._apply_editor_card_appearance()

    def _get_current_card_color(self) -> str:
        if not self.current_document_id:
            return ""
        doc = self.service.get_document(self.current_document_id)
        return doc.card_color if doc else ""

    def _apply_editor_card_appearance(self):
        is_dark = (self.current_theme == "dark")
        card_color = self._get_current_card_color()
        sheet_bg, _, text_c, border_c, swatch_c, _ = resolve_card_style(card_color, is_dark)

        self.editor.setStyleSheet(
            f"QTextEdit#editor_canvas {{ background-color: {sheet_bg}; color: {text_c}; "
            f"border: 1px solid {border_c}; border-radius: 10px; padding: 22px; font-size: {self.font_size}px; }}"
        )
        f = self.editor.font()
        f.setPointSize(self.font_size)
        self.editor.setFont(f)
        if self.editor.document():
            self.editor.document().setDefaultFont(f)

        if hasattr(self, "btn_card_color"):
            self.btn_card_color.setIcon(make_color_dot_icon(swatch_c, border_c, size=14))

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
            "undo": self._shortcut_undo,
            "redo": self._shortcut_redo,
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

        used_seqs = set()
        for action_key, handler in actions_map.items():
            key_seq = self._get_shortcut(action_key)
            if key_seq.strip():
                used_seqs.add(key_seq.strip().lower())
                shortcut = QShortcut(QKeySequence(key_seq), self)
                shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
                shortcut.activated.connect(handler)
                self.registered_shortcuts.append(shortcut)

        if "ctrl+y" not in used_seqs:
            redo_alt = QShortcut(QKeySequence("Ctrl+Y"), self)
            redo_alt.setContext(Qt.ShortcutContext.WindowShortcut)
            redo_alt.activated.connect(self._shortcut_redo)
            self.registered_shortcuts.append(redo_alt)

        esc_shortcut = QShortcut(QKeySequence("Esc"), self)
        esc_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        esc_shortcut.activated.connect(self._exit_zen_mode)
        self.registered_shortcuts.append(esc_shortcut)

    def _update_shortcut_tooltips(self):
        self.btn_undo.setToolTip(f"Desfazer ({self._get_shortcut('undo')})")
        self.btn_redo.setToolTip(f"Refazer ({self._get_shortcut('redo')})")
        self.btn_save_doc.setToolTip(f"Salvar alterações ({self._get_shortcut('save_doc')})")
        self.btn_toggle_mode.setToolTip(f"Alternar Modo Leitura / Edição ({self._get_shortcut('toggle_mode')})")
        self.btn_mark_term.setToolTip(f"Marcar termo selecionado ({self._get_shortcut('mark_term')})")
        self.btn_flashcards.setToolTip(f"Praticar Flashcards ({self._get_shortcut('flashcards')})")
        self.btn_bold.setToolTip(f"Negrito ({self._get_shortcut('bold')})")
        self.btn_italic.setToolTip(f"Itálico ({self._get_shortcut('italic')})")
        self.btn_underline.setToolTip(f"Sublinhado ({self._get_shortcut('underline')})")
        self.btn_zen.setToolTip(f"Modo Foco sem distrações ({self._get_shortcut('zen_mode')})")
        self.btn_collapse_left.setToolTip(f"Recolher Cadernos ({self._get_shortcut('toggle_left')})")
        self.btn_expand_left.setToolTip(f"Expandir Cadernos ({self._get_shortcut('toggle_left')})")
        self.btn_collapse_right.setToolTip(f"Recolher Notas ({self._get_shortcut('toggle_right')})")
        self.btn_expand_right.setToolTip(f"Expandir Notas ({self._get_shortcut('toggle_right')})")

    # ---------------- Sistema Global de Desfazer / Refazer ----------------

    def _push_undo_entry(self, entry: UndoEntry):
        self._undo_stack.append(entry)
        self._redo_stack.clear()
        self._update_undo_redo_buttons()

    def _prune_doc_text_undo(self, doc_id: str):
        self._undo_stack = [
            e for e in self._undo_stack if not (e.doc_id == doc_id and e.kind in ("editor_text", "term_and_text"))
        ]
        self._redo_stack = [
            e for e in self._redo_stack if not (e.doc_id == doc_id and e.kind in ("editor_text", "term_and_text"))
        ]
        self._update_undo_redo_buttons()

    def _on_qdoc_undo_added(self, doc_id: str):
        if self._suppress_undo_capture:
            return
        self._push_undo_entry(UndoEntry(kind="editor_text", doc_id=doc_id))

    def _update_undo_redo_buttons(self):
        if hasattr(self, "btn_undo"):
            self.btn_undo.setEnabled(len(self._undo_stack) > 0)
        if hasattr(self, "btn_redo"):
            self.btn_redo.setEnabled(len(self._redo_stack) > 0)

    def _shortcut_undo(self):
        fw = QApplication.focusWidget()
        if fw is self.txt_term_note and self.txt_term_note.document().isUndoAvailable():
            self.txt_term_note.undo()
            return
        if isinstance(fw, QLineEdit) and fw in (self.input_doc_title, self.input_search) and fw.isUndoAvailable():
            fw.undo()
            return
        self._global_undo()

    def _shortcut_redo(self):
        fw = QApplication.focusWidget()
        if fw is self.txt_term_note and self.txt_term_note.document().isRedoAvailable():
            self.txt_term_note.redo()
            return
        if isinstance(fw, QLineEdit) and fw in (self.input_doc_title, self.input_search) and fw.isRedoAvailable():
            fw.redo()
            return
        self._global_redo()

    def _persist_qdoc_silently(self, doc_id: str):
        qdoc = self.document_cache.get(doc_id)
        doc = self.service.get_document(doc_id)
        if not qdoc or not doc:
            return
        self.service.update_document(
            doc_id,
            doc.title,
            qdoc.toHtml(),
            doc.category,
            save_snapshot=False,
            clean_orphans=False,
        )
        qdoc.setModified(False)

    def _ensure_doc_active_for_undo(self, doc_id: str) -> bool:
        doc = self.service.get_document(doc_id)
        if not doc:
            return False
        if self.current_document_id != doc_id:
            self._select_document_by_id(doc_id, prompt_save=False)
        return self.current_document_id == doc_id

    def _global_undo(self):
        while self._undo_stack:
            entry = self._undo_stack.pop()
            if not self._ensure_doc_active_for_undo(entry.doc_id):
                continue

            qdoc = self.document_cache.get(entry.doc_id)
            if entry.kind == "editor_text":
                if not qdoc or not qdoc.isUndoAvailable():
                    continue
                self._suppress_undo_capture = True
                qdoc.undo()
                self._suppress_undo_capture = False
                if self.stack_center.currentIndex() == 0:
                    self._persist_qdoc_silently(entry.doc_id)
                self._redo_stack.append(entry)
                self._refresh_views()
                self._refresh_doc_terms_list()
                self.statusBar().showMessage("↩️ Ação desfeita.", 2000)
                break

            elif entry.kind == "term_and_text":
                self.service.restore_terms_snapshot(entry.doc_id, entry.before)
                if qdoc and qdoc.isUndoAvailable():
                    self._suppress_undo_capture = True
                    qdoc.undo()
                    self._suppress_undo_capture = False
                self._persist_qdoc_silently(entry.doc_id)
                self._redo_stack.append(entry)
                self._refresh_views()
                self._refresh_doc_terms_list()
                self._clear_active_term()
                self.statusBar().showMessage("↩️ Marcação desfeita.", 2000)
                break

            elif entry.kind == "card_color":
                self.service.update_document_card_color(entry.doc_id, entry.before)
                self._redo_stack.append(entry)
                self._apply_editor_card_appearance()
                self._refresh_views()
                self._refresh_sidebar_item_appearance(entry.doc_id)
                self.statusBar().showMessage("↩️ Cor do card desfeita.", 2000)
                break

            elif entry.kind == "doc_title":
                self.service.rename_document(entry.doc_id, entry.before)
                self._loaded_title = entry.before
                self.input_doc_title.setText(entry.before)
                self._refresh_sidebar_item_appearance(entry.doc_id)
                self._redo_stack.append(entry)
                self.statusBar().showMessage("↩️ Título restaurado.", 2000)
                break

            elif entry.kind == "doc_category":
                self.service.update_document_category(entry.doc_id, entry.before)
                self.lbl_category_badge.setText(f"📁 {entry.before}")
                self._load_categories()
                self._load_documents()
                self._select_document_by_id(entry.doc_id, prompt_save=False)
                self._redo_stack.append(entry)
                self.statusBar().showMessage("↩️ Categoria restaurada.", 2000)
                break

            elif entry.kind == "term_note":
                anchor_key = entry.extra
                self.service.update_term_note(anchor_key, entry.before)
                if self.current_anchor_key == anchor_key:
                    self._loaded_note_text = entry.before
                    self.txt_term_note.blockSignals(True)
                    self.txt_term_note.setPlainText(entry.before)
                    self.txt_term_note.document().setModified(False)
                    self.txt_term_note.blockSignals(False)
                    self._update_note_save_button(False)
                self._redo_stack.append(entry)
                self.statusBar().showMessage("↩️ Nota restaurada.", 2000)
                break

        self._update_undo_redo_buttons()
        self._on_modification_changed(self.editor.document().isModified() if self.editor.document() else False)

    def _global_redo(self):
        while self._redo_stack:
            entry = self._redo_stack.pop()
            if not self._ensure_doc_active_for_undo(entry.doc_id):
                continue

            qdoc = self.document_cache.get(entry.doc_id)
            if entry.kind == "editor_text":
                if not qdoc or not qdoc.isRedoAvailable():
                    continue
                self._suppress_undo_capture = True
                qdoc.redo()
                self._suppress_undo_capture = False
                if self.stack_center.currentIndex() == 0:
                    self._persist_qdoc_silently(entry.doc_id)
                self._undo_stack.append(entry)
                self._refresh_views()
                self._refresh_doc_terms_list()
                self.statusBar().showMessage("↪️ Ação refeita.", 2000)
                break

            elif entry.kind == "term_and_text":
                self.service.restore_terms_snapshot(entry.doc_id, entry.after)
                if qdoc and qdoc.isRedoAvailable():
                    self._suppress_undo_capture = True
                    qdoc.redo()
                    self._suppress_undo_capture = False
                self._persist_qdoc_silently(entry.doc_id)
                self._undo_stack.append(entry)
                self._refresh_views()
                self._refresh_doc_terms_list()
                self._clear_active_term()
                self.statusBar().showMessage("↪️ Marcação refeita.", 2000)
                break

            elif entry.kind == "card_color":
                self.service.update_document_card_color(entry.doc_id, entry.after)
                self._undo_stack.append(entry)
                self._apply_editor_card_appearance()
                self._refresh_views()
                self._refresh_sidebar_item_appearance(entry.doc_id)
                self.statusBar().showMessage("↪️ Cor do card refeita.", 2000)
                break

            elif entry.kind == "doc_title":
                self.service.rename_document(entry.doc_id, entry.after)
                self._loaded_title = entry.after
                self.input_doc_title.setText(entry.after)
                self._refresh_sidebar_item_appearance(entry.doc_id)
                self._undo_stack.append(entry)
                self.statusBar().showMessage("↪️ Título refeito.", 2000)
                break

            elif entry.kind == "doc_category":
                self.service.update_document_category(entry.doc_id, entry.after)
                self.lbl_category_badge.setText(f"📁 {entry.after}")
                self._load_categories()
                self._load_documents()
                self._select_document_by_id(entry.doc_id, prompt_save=False)
                self._undo_stack.append(entry)
                self.statusBar().showMessage("↪️ Categoria refeita.", 2000)
                break

            elif entry.kind == "term_note":
                anchor_key = entry.extra
                self.service.update_term_note(anchor_key, entry.after)
                if self.current_anchor_key == anchor_key:
                    self._loaded_note_text = entry.after
                    self.txt_term_note.blockSignals(True)
                    self.txt_term_note.setPlainText(entry.after)
                    self.txt_term_note.document().setModified(False)
                    self.txt_term_note.blockSignals(False)
                    self._update_note_save_button(False)
                self._undo_stack.append(entry)
                self.statusBar().showMessage("↪️ Nota refeita.", 2000)
                break

        self._update_undo_redo_buttons()
        self._on_modification_changed(self.editor.document().isModified() if self.editor.document() else False)

    # ---------------- Construção da Interface ----------------

    def _setup_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(6, 4, 6, 4)
        main_layout.setSpacing(6)

        self.reader = QTextBrowser()
        self.reader.setObjectName("reader_canvas")
        self.reader.setOpenLinks(False)
        self.reader.anchorClicked.connect(self._on_anchor_clicked)
        self.reader.setLineWrapMode(QTextBrowser.LineWrapMode.WidgetWidth)
        self.reader.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.reader.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.reader.installEventFilter(self)

        self.editor = QTextEdit()
        self.editor.setObjectName("editor_canvas")
        self.editor.cursorPositionChanged.connect(self._on_editor_cursor_moved)
        self.editor.textChanged.connect(self._schedule_status_update)
        self.editor.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.editor.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.editor.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.editor.installEventFilter(self)

        # Estado Vazio (Empty State)
        self.empty_state_widget = QWidget()
        empty_outer = QVBoxLayout(self.empty_state_widget)
        empty_outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        empty_card = QFrame()
        empty_card.setObjectName("empty_state_card")
        empty_card.setMaximumWidth(460)
        empty_card_layout = QVBoxLayout(empty_card)
        empty_card_layout.setSpacing(14)
        empty_card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lbl_empty_icon = QLabel("📓")
        lbl_empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_empty_icon.setStyleSheet("font-size: 46px;")
        empty_card_layout.addWidget(lbl_empty_icon)

        lbl_empty_title = QLabel("<b>Nenhum caderno aberto</b>")
        lbl_empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_empty_title.setStyleSheet("font-size: 18px;")
        empty_card_layout.addWidget(lbl_empty_title)

        lbl_empty_sub = QLabel(
            "Crie um novo caderno de estudos ou importe um arquivo .json para começar."
        )
        lbl_empty_sub.setWordWrap(True)
        lbl_empty_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_card_layout.addWidget(lbl_empty_sub)

        empty_btns = QHBoxLayout()
        btn_empty_new = QPushButton("➕ Criar Primeiro Caderno")
        btn_empty_new.setObjectName("btn_primary")
        btn_empty_new.clicked.connect(self._create_new_document)
        empty_btns.addWidget(btn_empty_new)

        btn_empty_import = QPushButton("📥 Importar (.json)")
        btn_empty_import.clicked.connect(self._import_document)
        empty_btns.addWidget(btn_empty_import)
        empty_card_layout.addLayout(empty_btns)
        empty_outer.addWidget(empty_card)

        self.stack_center = QStackedWidget()
        self.stack_center.addWidget(self.reader)              # 0: Leitura
        self.stack_center.addWidget(self.editor)              # 1: Edição
        self.stack_center.addWidget(self.empty_state_widget)  # 2: Vazio

        # ---------------- Barra Superior ----------------
        self.top_toolbar = QWidget()
        self.top_toolbar.setObjectName("top_toolbar")
        self.top_toolbar.setFixedHeight(48)
        layout_toolbar = QHBoxLayout(self.top_toolbar)
        layout_toolbar.setContentsMargins(6, 2, 6, 2)
        layout_toolbar.setSpacing(6)

        self.btn_menu_file = QToolButton()
        self.btn_menu_file.setText("📁 Arquivo ▾")
        self.btn_menu_file.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu_file = QMenu(self)
        menu_file.addAction("📄 Novo Caderno", self._create_new_document)
        menu_file.addAction("💾 Salvar Alterações", self._save_current_document)
        menu_file.addSeparator()
        menu_file.addAction("🕒 Histórico de Versões", lambda: self._open_history_dialog())
        menu_file.addSeparator()
        menu_file.addAction("🛡️ Fazer Backup dos Dados...", self._backup_database)
        menu_file.addAction("🔄 Restaurar Backup (.db)...", self._restore_database)
        menu_file.addSeparator()
        menu_file.addAction("📥 Importar Caderno (.json)", self._import_document)
        menu_file.addAction("📤 Exportar para PDF / Markdown", self._export_current_document)
        self.btn_menu_file.setMenu(menu_file)
        layout_toolbar.addWidget(self.btn_menu_file)

        self.btn_undo = QPushButton("↩️")
        self.btn_undo.setFixedWidth(36)
        self.btn_undo.clicked.connect(self._global_undo)
        layout_toolbar.addWidget(self.btn_undo)

        self.btn_redo = QPushButton("↪️")
        self.btn_redo.setFixedWidth(36)
        self.btn_redo.clicked.connect(self._global_redo)
        layout_toolbar.addWidget(self.btn_redo)

        layout_toolbar.addWidget(self._create_separator())

        self.btn_toggle_mode = QPushButton("✏️ Modo Edição")
        self.btn_toggle_mode.clicked.connect(self._toggle_mode)
        layout_toolbar.addWidget(self.btn_toggle_mode)

        self.btn_flashcards = QPushButton("🃏 Praticar")
        self.btn_flashcards.clicked.connect(self._open_flashcards)
        layout_toolbar.addWidget(self.btn_flashcards)

        # Grupo contextual de edição (visível apenas no Modo Edição)
        self.edit_toolbar_group = QWidget()
        self.edit_toolbar_group.setObjectName("edit_toolbar_group")
        edit_group_layout = QHBoxLayout(self.edit_toolbar_group)
        edit_group_layout.setContentsMargins(0, 0, 0, 0)
        edit_group_layout.setSpacing(5)

        edit_group_layout.addWidget(self._create_separator())

        self.btn_mark_term = QPushButton("★ Marcar Termo")
        self.btn_mark_term.setObjectName("btn_primary")
        self.btn_mark_term.clicked.connect(self._mark_selected_term)
        edit_group_layout.addWidget(self.btn_mark_term)

        self.btn_bold = QPushButton("B")
        self.btn_bold.setObjectName("format_btn")
        self.btn_bold.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.btn_bold.clicked.connect(self._format_bold)
        edit_group_layout.addWidget(self.btn_bold)

        self.btn_italic = QPushButton("I")
        self.btn_italic.setObjectName("format_btn")
        f_it = QFont("Segoe UI", 11)
        f_it.setItalic(True)
        self.btn_italic.setFont(f_it)
        self.btn_italic.clicked.connect(self._format_italic)
        edit_group_layout.addWidget(self.btn_italic)

        self.btn_underline = QPushButton("U")
        self.btn_underline.setObjectName("format_btn")
        f_und = QFont("Segoe UI", 11)
        f_und.setUnderline(True)
        self.btn_underline.setFont(f_und)
        self.btn_underline.clicked.connect(self._format_underline)
        edit_group_layout.addWidget(self.btn_underline)

        self.btn_font_color = QPushButton("🎨 Cor")
        self.btn_font_color.setToolTip("Alterar cor das letras")
        self.btn_font_color.clicked.connect(self._format_font_color)
        edit_group_layout.addWidget(self.btn_font_color)

        self.btn_clear_bg = QPushButton("🧹 Limpar")
        self.btn_clear_bg.setToolTip("Remove o destaque da seleção")
        self.btn_clear_bg.clicked.connect(self._clear_selection_highlight)
        edit_group_layout.addWidget(self.btn_clear_bg)

        self.combo_font_family = QFontComboBox()
        self.combo_font_family.setToolTip("Escolha a fonte do texto")
        self.combo_font_family.setFixedWidth(125)
        self.combo_font_family.setCurrentFont(QFont("Segoe UI"))
        self.combo_font_family.currentFontChanged.connect(self._on_font_family_changed)
        edit_group_layout.addWidget(self.combo_font_family)

        self.edit_toolbar_group.setVisible(False)
        layout_toolbar.addWidget(self.edit_toolbar_group)

        layout_toolbar.addWidget(self._create_separator())

        self.spin_font_size = QSpinBox()
        self.spin_font_size.setRange(11, 40)
        self.spin_font_size.setValue(self.font_size)
        self.spin_font_size.setToolTip("Tamanho da fonte")
        self.spin_font_size.valueChanged.connect(self._on_font_size_changed)
        layout_toolbar.addWidget(self.spin_font_size)

        layout_toolbar.addStretch()

        self.lbl_unsaved_badge = QLabel("● Não salvo")
        self.lbl_unsaved_badge.setObjectName("unsaved_badge")
        self.lbl_unsaved_badge.setVisible(False)
        layout_toolbar.addWidget(self.lbl_unsaved_badge)

        self.btn_save_doc = QPushButton("💾 Salvar")
        self.btn_save_doc.setEnabled(False)
        self.btn_save_doc.clicked.connect(self._save_current_document)
        layout_toolbar.addWidget(self.btn_save_doc)

        self.btn_zen = QPushButton("🔲 Foco")
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
        self.btn_new_sidebar = QPushButton("➕")
        self.btn_new_sidebar.setToolTip("Novo Caderno (Ctrl+N)")
        self.btn_new_sidebar.setFixedSize(30, 28)
        self.btn_new_sidebar.clicked.connect(self._create_new_document)
        header_left.addWidget(self.btn_new_sidebar)

        self.btn_collapse_left = QPushButton("❮")
        self.btn_collapse_left.setObjectName("panel_toggle_btn")
        self.btn_collapse_left.setFixedSize(30, 28)
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
        layout_center.setContentsMargins(4, 2, 4, 2)
        layout_center.setSpacing(6)

        box_header = QHBoxLayout()

        self.btn_expand_left = QPushButton("❯ Cadernos")
        self.btn_expand_left.setObjectName("panel_toggle_btn")
        self.btn_expand_left.setVisible(False)
        self.btn_expand_left.clicked.connect(self._toggle_left_panel)
        box_header.addWidget(self.btn_expand_left)

        self.input_doc_title = QLineEdit()
        self.input_doc_title.setPlaceholderText("Título do caderno...")
        self.input_doc_title.setStyleSheet("font-size: 16px; font-weight: bold; padding: 6px;")
        self.input_doc_title.editingFinished.connect(self._on_title_editing_finished)
        box_header.addWidget(self.input_doc_title, 1)

        self.btn_card_color = QPushButton(" Card")
        self.btn_card_color.setToolTip("Mudar cor do card ou tema (estilo Keep)")
        self.btn_card_color.clicked.connect(lambda: self._change_document_card_color())
        box_header.addWidget(self.btn_card_color)

        self.lbl_category_badge = QPushButton("📁 Geral")
        self.lbl_category_badge.setToolTip("Alterar a pasta/categoria deste caderno")
        self.lbl_category_badge.clicked.connect(lambda: self._change_document_category())
        box_header.addWidget(self.lbl_category_badge)

        self.btn_expand_right = QPushButton("Notas ❮")
        self.btn_expand_right.setObjectName("panel_toggle_btn")
        self.btn_expand_right.setVisible(False)
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
        self.btn_collapse_right.setObjectName("panel_toggle_btn")
        self.btn_collapse_right.setFixedSize(30, 28)
        self.btn_collapse_right.clicked.connect(self._toggle_right_panel)
        header_right.addWidget(self.btn_collapse_right)
        layout_side.addLayout(header_right)

        terms_header = QHBoxLayout()
        self.lbl_doc_terms_count = QLabel("<b>Termos do caderno (0)</b>")
        terms_header.addWidget(self.lbl_doc_terms_count)
        self.btn_toggle_terms_list = QPushButton("▾")
        self.btn_toggle_terms_list.setFixedSize(26, 24)
        self.btn_toggle_terms_list.setToolTip("Mostrar/Ocultar índice de termos")
        self.btn_toggle_terms_list.clicked.connect(self._toggle_doc_terms_list)
        terms_header.addWidget(self.btn_toggle_terms_list)
        layout_side.addLayout(terms_header)

        self.list_doc_terms = QListWidget()
        self.list_doc_terms.setMaximumHeight(135)
        self.list_doc_terms.itemClicked.connect(self._on_term_list_clicked)
        layout_side.addWidget(self.list_doc_terms)

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
        self.txt_term_note.installEventFilter(self)
        self.txt_term_note.textChanged.connect(self._on_note_text_changed)
        layout_side.addWidget(self.txt_term_note)

        self.btn_save_note = QPushButton("Salvar Alteração na Nota")
        self.btn_save_note.setObjectName("btn_primary")
        self.btn_save_note.setEnabled(False)
        self.btn_save_note.clicked.connect(self._save_note_changes)
        layout_side.addWidget(self.btn_save_note)

        self.splitter.addWidget(self.col_side)

        self.splitter.setCollapsible(0, True)
        self.splitter.setCollapsible(1, False)
        self.splitter.setCollapsible(2, True)
        self.splitter.setSizes([240, 740, 290])

        self.statusBar().showMessage("Pronto para estudar!")

    def _toggle_doc_terms_list(self):
        visible = not self.list_doc_terms.isVisible()
        self.list_doc_terms.setVisible(visible)
        self.btn_toggle_terms_list.setText("▾" if visible else "▸")

    def _refresh_doc_terms_list(self):
        self.list_doc_terms.clear()
        if not self.current_document_id:
            self.lbl_doc_terms_count.setText("<b>Termos do caderno (0)</b>")
            return

        active_anchors = extract_anchors_from_html(self.editor.toHtml())
        terms = [
            t
            for t in self.service.list_terms_for_document(self.current_document_id, clean_orphans=False)
            if t.anchor_key in active_anchors
        ]
        self.lbl_doc_terms_count.setText(f"<b>Termos do caderno ({len(terms)})</b>")
        for t in terms:
            item = QListWidgetItem(t.term_text)
            item.setData(Qt.ItemDataRole.UserRole, t.anchor_key)
            item.setIcon(make_color_dot_icon(t.color or "#ffe066", "#555555", size=12))
            self.list_doc_terms.addItem(item)
            if t.anchor_key == self.current_anchor_key:
                self.list_doc_terms.setCurrentItem(item)

    def _on_term_list_clicked(self, item: QListWidgetItem):
        anchor_key = item.data(Qt.ItemDataRole.UserRole)
        if not anchor_key:
            return
        self._load_active_term(anchor_key)
        self._scroll_to_anchor(anchor_key)

    def _scroll_to_anchor(self, anchor_key: str):
        target_href = f"anchor:{anchor_key}"
        view = self.editor if self.stack_center.currentIndex() == 1 else self.reader
        doc = view.document()
        block = doc.begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid() and frag.charFormat().anchorHref() == target_href:
                    cur = QTextCursor(doc)
                    cur.setPosition(frag.position())
                    cur.setPosition(frag.position() + frag.length(), QTextCursor.MoveMode.KeepAnchor)
                    view.setTextCursor(cur)
                    view.ensureCursorVisible()
                    return
                it += 1
            block = block.next()

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
            self._pre_zen_left_visible = self.col_docs.isVisible()
            self._pre_zen_right_visible = self.col_side.isVisible()
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
            self.col_docs.setVisible(self._pre_zen_left_visible)
            self.col_side.setVisible(self._pre_zen_right_visible)
            self.top_toolbar.setVisible(True)
            self.btn_expand_left.setVisible(not self._pre_zen_left_visible)
            self.btn_expand_right.setVisible(not self._pre_zen_right_visible)
            self.showNormal()
            self.statusBar().showMessage("Modo Foco finalizado.", 2000)

    def _schedule_status_update(self):
        if not self._is_loading:
            self._status_timer.start()

    def _update_status_bar(self):
        if not self.current_document_id:
            self.statusBar().showMessage("Pronto para estudar!")
            return
        text = self.editor.toPlainText().strip()
        word_count = len(text.split()) if text else 0
        term_count = len(extract_anchors_from_html(self.editor.toHtml()))
        self.statusBar().showMessage(f"📝 {word_count} palavras  •  🏷️ {term_count} conceitos destacados")

    def _on_modification_changed(self, modified: bool):
        has_doc = self.current_document_id is not None
        self.lbl_unsaved_badge.setVisible(has_doc and modified)
        self.btn_save_doc.setEnabled(has_doc and modified)
        self.btn_save_doc.setObjectName("btn_primary" if (has_doc and modified) else "")
        self.btn_save_doc.style().unpolish(self.btn_save_doc)
        self.btn_save_doc.style().polish(self.btn_save_doc)

    def _load_categories(self):
        current_selection = self.combo_categories.currentText() or self._current_category_filter
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
        self._current_category_filter = self.combo_categories.currentText()
        self.combo_categories.blockSignals(False)

    def _on_category_filter_changed(self, new_cat: str):
        self._auto_save_note_if_needed()
        if not self._check_and_prompt_save_changes():
            self.combo_categories.blockSignals(True)
            self.combo_categories.setCurrentText(self._current_category_filter)
            self.combo_categories.blockSignals(False)
            return
        self._current_category_filter = new_cat
        self._load_documents()

    def _change_document_category(self, target_doc_id: Optional[str] = None):
        doc_id = target_doc_id or self.current_document_id
        if not doc_id:
            return
        doc = self.service.get_document(doc_id)
        if not doc:
            return

        new_cat, ok = QInputDialog.getText(
            self, "Categoria do Caderno", "Digite o nome da pasta/categoria:", text=doc.category
        )
        if ok and new_cat.strip() and new_cat.strip() != doc.category:
            old_cat = doc.category
            cat = new_cat.strip()
            self.service.update_document_category(doc_id, cat)
            self._push_undo_entry(UndoEntry(kind="doc_category", doc_id=doc_id, before=old_cat, after=cat))
            if doc_id == self.current_document_id:
                self.lbl_category_badge.setText(f"📁 {cat}")
            if self._current_category_filter not in ("Todas", cat):
                self._current_category_filter = cat
            self._load_categories()
            self._load_documents()
            self._select_document_by_id(doc_id, prompt_save=False)

    def _change_document_card_color(self, target_doc_id: Optional[str] = None):
        doc_id = target_doc_id or self.current_document_id
        if not doc_id:
            return
        doc = self.service.get_document(doc_id)
        if not doc:
            return

        is_dark = (self.current_theme == "dark")
        dlg = CardColorDialog(
            current_color=doc.card_color,
            is_dark=is_dark,
            on_toggle_theme=self._toggle_theme,
            parent=self,
        )
        if dlg.exec():
            new_color = dlg.selected_color
            if new_color != doc.card_color:
                old_color = doc.card_color
                self.service.update_document_card_color(doc_id, new_color)
                self._push_undo_entry(UndoEntry(kind="card_color", doc_id=doc_id, before=old_color, after=new_color))
                self._refresh_sidebar_item_appearance(doc_id)
                if doc_id == self.current_document_id:
                    self._apply_editor_card_appearance()
                    self._refresh_views()
                self.statusBar().showMessage("🎨 Cor do card atualizada!", 2500)

    def _refresh_sidebar_item_appearance(self, doc_id: str):
        doc = self.service.get_document(doc_id)
        if not doc:
            return
        is_dark = (self.current_theme == "dark")
        for i in range(self.list_docs.count()):
            item = self.list_docs.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == doc_id:
                item.setText(doc.title)
                self._style_sidebar_item(item, doc.card_color, is_dark)
                break

    def _style_sidebar_item(self, item: QListWidgetItem, card_color: str, is_dark: bool):
        if not card_color:
            item.setIcon(QIcon())
            item.setBackground(QBrush(Qt.BrushStyle.NoBrush))
            item.setForeground(QBrush(Qt.BrushStyle.NoBrush))
            return

        sheet_bg, _, text_c, border_c, swatch_c, _ = resolve_card_style(card_color, is_dark)
        item.setIcon(make_color_dot_icon(swatch_c, border_c, size=14))
        tint = QColor(sheet_bg)
        tint.setAlpha(140 if is_dark else 190)
        item.setBackground(QBrush(tint))
        item.setForeground(QBrush(QColor(text_c)))

    def _backup_database(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"notebook_backup_{timestamp}.db"

        BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
        default_target = str(BACKUPS_DIR / default_name)

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar Cópia de Segurança (Backup)",
            default_target,
            "Banco de Dados SQLite (*.db)",
        )
        if not file_path:
            return

        try:
            self._auto_save_note_if_needed()
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
            "Banco de Dados SQLite (*.db)",
        )
        if not file_path:
            return

        confirm = QMessageBox.warning(
            self,
            "Confirmar Restauração",
            "<b>ATENÇÃO:</b> Restaurar um backup substituirá todos os cadernos e anotações atuais pelos dados do arquivo selecionado.<br><br>Deseja continuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            success = self.service.restore_database_backup(Path(file_path))
            if success:
                self.document_cache.clear()
                self._undo_stack.clear()
                self._redo_stack.clear()
                self._update_undo_redo_buttons()
                self._load_categories()
                self._load_documents()
                QMessageBox.information(self, "Sucesso", "Banco de dados restaurado com sucesso!")
            else:
                QMessageBox.warning(self, "Arquivo Inválido", "O arquivo selecionado não é um backup compatível do ANote.")
        except Exception as e:
            QMessageBox.critical(self, "Erro na Restauração", f"Falha ao restaurar banco de dados:\n{e}")

    def _open_history_dialog(self, target_doc_id: Optional[str] = None):
        doc_id = target_doc_id or self.current_document_id
        if not doc_id:
            QMessageBox.information(self, "Aviso", "Selecione um caderno para ver seu histórico de versões.")
            return

        is_dark = (self.current_theme == "dark")
        dlg = HistoryDialog(self.service, doc_id, is_dark=is_dark, parent=self)
        if dlg.exec() and dlg.restored_content:
            if doc_id != self.current_document_id:
                self._select_document_by_id(doc_id)
            if self.stack_center.currentIndex() != 1:
                self._set_center_mode(edit_mode=True)
            self._prune_doc_text_undo(doc_id)
            self._suppress_undo_capture = True
            self.editor.setHtml(
                TextParser.sanitize_theme_colors(dlg.restored_content, is_dark, strip_theme_defaults=True)
            )
            self._suppress_undo_capture = False
            self._save_current_document()
            QMessageBox.information(self, "Versão Restaurada", "O conteúdo da versão anterior foi restaurado com sucesso!")

    def _open_flashcards(self):
        if not self.current_document_id:
            QMessageBox.information(self, "Aviso", "Abra um caderno para praticar seus flashcards.")
            return

        self._auto_save_note_if_needed()
        content = self.editor.toHtml()
        active_anchors = extract_anchors_from_html(content)
        all_terms = self.service.list_terms_for_document(self.current_document_id, clean_orphans=False)
        terms = [t for t in all_terms if t.anchor_key in active_anchors]

        if not terms:
            QMessageBox.information(
                self,
                "Nenhum termo marcado",
                "Você ainda não grifou termos neste caderno!\n\nSelecione qualquer palavra no texto e clique em '★ Marcar Termo' para criar seu primeiro cartão de estudo.",
            )
            return

        doc = self.service.get_document(self.current_document_id)
        dlg = FlashcardDialog(terms, doc.title if doc else "Caderno", self)
        dlg.exec()

    def _mark_selected_term(self):
        if not self.current_document_id or self.stack_center.currentIndex() != 1:
            return

        cursor = self.editor.textCursor()
        selected_text = cursor.selectedText().replace("\u2029", " ").strip()

        if not selected_text:
            QMessageBox.warning(self, "Aviso", "Selecione uma palavra ou trecho no texto com o mouse para grifar.")
            return

        note_content, ok = QInputDialog.getMultiLineText(
            self, f"Anotação para: '{selected_text}'", "O que você quer lembrar sobre este termo?"
        )
        if ok and note_content.strip():
            picker = ColorPickerPopup(self, term_label=selected_text)
            highlight_color = picker.selected_color if picker.exec() else "#ffe066"

            doc_id = self.current_document_id
            before_terms = self.service.list_terms_for_document(doc_id, clean_orphans=False)
            anchor_key = f"anc_{uuid.uuid4().hex[:8]}"

            self._suppress_undo_capture = True
            cursor.beginEditBlock()
            fmt = QTextCharFormat()
            fmt.setAnchor(True)
            fmt.setAnchorHref(f"anchor:{anchor_key}")
            fmt.setBackground(QColor(highlight_color))
            fmt.setForeground(QColor("#1e1e2e"))
            cursor.mergeCharFormat(fmt)
            cursor.clearSelection()
            cursor.endEditBlock()
            self.editor.setTextCursor(cursor)
            self._suppress_undo_capture = False

            self.service.add_term_note(
                document_id=doc_id,
                term_text=selected_text,
                anchor_key=anchor_key,
                note_content=note_content.strip(),
                color=highlight_color,
            )
            after_terms = self.service.list_terms_for_document(doc_id, clean_orphans=False)
            self._push_undo_entry(
                UndoEntry(kind="term_and_text", doc_id=doc_id, before=before_terms, after=after_terms)
            )

            self._save_current_document()
            self._load_active_term(anchor_key)
            self._refresh_doc_terms_list()

    def _collect_anchor_ranges(self, target_href: str) -> List[tuple]:
        doc = self.editor.document()
        ranges = []
        block = doc.begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid():
                    fmt = frag.charFormat()
                    if fmt.anchorHref() == target_href:
                        ranges.append((frag.position(), frag.position() + frag.length(), fmt))
                it += 1
            block = block.next()
        return ranges

    def _change_active_term_color(self):
        if not self.current_anchor_key or not self.current_document_id:
            return

        doc_id = self.current_document_id
        term = self.service.get_note_by_anchor(self.current_anchor_key)
        if not term:
            return

        picker = ColorPickerPopup(self, term_label=term.term_text)
        if picker.exec():
            new_color = picker.selected_color
            before_terms = self.service.list_terms_for_document(doc_id, clean_orphans=False)
            self.service.update_term_color(doc_id, self.current_anchor_key, new_color)
            after_terms = self.service.list_terms_for_document(doc_id, clean_orphans=False)

            qdoc = self.editor.document()
            target_href = f"anchor:{self.current_anchor_key}"
            ranges = self._collect_anchor_ranges(target_href)

            self._suppress_undo_capture = True
            edit_cur = QTextCursor(qdoc)
            edit_cur.beginEditBlock()
            for start, end, _ in reversed(ranges):
                edit_cur.setPosition(start)
                edit_cur.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
                fmt = QTextCharFormat()
                fmt.setBackground(QColor(new_color))
                edit_cur.mergeCharFormat(fmt)
            edit_cur.endEditBlock()
            self._suppress_undo_capture = False

            self._push_undo_entry(
                UndoEntry(kind="term_and_text", doc_id=doc_id, before=before_terms, after=after_terms)
            )

            self._save_current_document()
            self._refresh_doc_terms_list()
            self.statusBar().showMessage(f"Cor de '{term.term_text}' atualizada!", 2500)

    def _delete_active_term(self):
        if not self.current_anchor_key or not self.current_document_id:
            return

        doc_id = self.current_document_id
        term = self.service.get_note_by_anchor(self.current_anchor_key)
        if not term:
            return

        confirm = QMessageBox.question(
            self,
            "Desmarcar Termo",
            f"Deseja remover o destaque e a anotação de '{term.term_text}'?\nO texto continuará na folha.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        before_terms = self.service.list_terms_for_document(doc_id, clean_orphans=False)
        qdoc = self.editor.document()
        target_href = f"anchor:{self.current_anchor_key}"
        ranges = self._collect_anchor_ranges(target_href)

        self._suppress_undo_capture = True
        edit_cur = QTextCursor(qdoc)
        edit_cur.beginEditBlock()
        for start, end, fmt in reversed(ranges):
            edit_cur.setPosition(start)
            edit_cur.setPosition(end, QTextCursor.MoveMode.KeepAnchor)

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
            clean_fmt.clearProperty(QTextFormat.Property.ForegroundBrush)
            edit_cur.setCharFormat(clean_fmt)
        edit_cur.endEditBlock()
        self._suppress_undo_capture = False

        self.service.delete_term(doc_id, self.current_anchor_key)
        after_terms = self.service.list_terms_for_document(doc_id, clean_orphans=False)
        self._push_undo_entry(
            UndoEntry(kind="term_and_text", doc_id=doc_id, before=before_terms, after=after_terms)
        )

        self._save_current_document()
        self._clear_active_term()
        self._refresh_doc_terms_list()
        self._update_status_bar()
        self.statusBar().showMessage("Termo desmarcado com sucesso!", 2500)

    def _clear_selection_highlight(self):
        if self.stack_center.currentIndex() != 1:
            self._toggle_mode()

        cursor = self.editor.textCursor()
        if not cursor.hasSelection():
            QMessageBox.information(self, "Aviso", "Selecione o trecho do texto com o mouse para limpar a cor de fundo.")
            return

        fmt = QTextCharFormat()
        fmt.setBackground(QBrush(Qt.BrushStyle.NoBrush))
        fmt.setAnchor(False)
        fmt.clearProperty(QTextFormat.Property.AnchorHref)
        fmt.clearProperty(QTextFormat.Property.ForegroundBrush)
        cursor.mergeCharFormat(fmt)

        self._save_current_document()
        self._refresh_doc_terms_list()
        self.statusBar().showMessage("Cor de fundo removida da seleção!", 2500)

    def _on_editor_cursor_moved(self):
        if self.stack_center.currentIndex() != 1:
            return
        cursor = self.editor.textCursor()
        href = cursor.charFormat().anchorHref()
        if href and href.startswith("anchor:"):
            self._load_active_term(href.replace("anchor:", ""))

    def _load_active_term(self, anchor_key: str):
        if self.current_anchor_key and self.current_anchor_key != anchor_key:
            self._auto_save_note_if_needed()

        term = self.service.get_note_by_anchor(anchor_key)
        if term:
            if not self.col_side.isVisible() and not self._is_zen_mode:
                self._toggle_right_panel()

            self.current_anchor_key = term.anchor_key
            self._loaded_note_text = term.note_content
            self.lbl_term_title.setText(f"Termo: {term.term_text}")
            self.txt_term_note.blockSignals(True)
            self.txt_term_note.setPlainText(term.note_content)
            self.txt_term_note.document().setModified(False)
            self.txt_term_note.blockSignals(False)
            self._update_note_save_button(False)
            self.btn_change_term_color.setEnabled(True)
            self.btn_delete_term.setEnabled(True)

            for i in range(self.list_doc_terms.count()):
                it = self.list_doc_terms.item(i)
                if it.data(Qt.ItemDataRole.UserRole) == anchor_key:
                    self.list_doc_terms.setCurrentItem(it)
                    break

    def _clear_active_term(self):
        self.current_anchor_key = None
        self._loaded_note_text = ""
        self.lbl_term_title.setText("<i>Nenhum termo ativo</i>")
        self.txt_term_note.blockSignals(True)
        self.txt_term_note.clear()
        self.txt_term_note.document().setModified(False)
        self.txt_term_note.blockSignals(False)
        self.btn_save_note.setText("Salvar Alteração na Nota")
        self.btn_save_note.setEnabled(False)
        self.btn_change_term_color.setEnabled(False)
        self.btn_delete_term.setEnabled(False)

    def _on_note_text_changed(self):
        if not self.current_anchor_key:
            return
        changed = self.txt_term_note.toPlainText().strip() != self._loaded_note_text.strip()
        self._update_note_save_button(changed)

    def _update_note_save_button(self, dirty: bool):
        if not self.current_anchor_key:
            self.btn_save_note.setEnabled(False)
            self.btn_save_note.setText("Salvar Alteração na Nota")
            return
        self.btn_save_note.setEnabled(True)
        self.btn_save_note.setText("💾 Salvar Alteração na Nota *" if dirty else "✓ Nota Salva")

    def _auto_save_note_if_needed(self):
        if not self.current_anchor_key or not self.current_document_id:
            return
        new_text = self.txt_term_note.toPlainText().strip()
        if new_text != self._loaded_note_text.strip():
            old_text = self._loaded_note_text
            self.service.update_term_note(self.current_anchor_key, new_text)
            self._loaded_note_text = new_text
            self.txt_term_note.document().setModified(False)
            self._update_note_save_button(False)
            self._push_undo_entry(
                UndoEntry(
                    kind="term_note",
                    doc_id=self.current_document_id,
                    before=old_text,
                    after=new_text,
                    extra=self.current_anchor_key,
                )
            )
            self.statusBar().showMessage("✓ Nota salva automaticamente!", 2000)

    def _on_title_editing_finished(self):
        if not self.current_document_id:
            return
        new_title = self.input_doc_title.text().strip() or "Sem título"
        if new_title != self._loaded_title:
            old_title = self._loaded_title
            self.service.rename_document(self.current_document_id, new_title)
            self._loaded_title = new_title
            self.input_doc_title.setText(new_title)
            self._refresh_sidebar_item_appearance(self.current_document_id)
            self._push_undo_entry(
                UndoEntry(kind="doc_title", doc_id=self.current_document_id, before=old_title, after=new_title)
            )
            self.statusBar().showMessage("✓ Título atualizado!", 2000)

    def _check_and_prompt_save_changes(self) -> bool:
        self._auto_save_note_if_needed()
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
                    is_dark = (self.current_theme == "dark")
                    _, _, _, _, _, is_dark_surface = resolve_card_style(doc.card_color, is_dark)
                    self._suppress_undo_capture = True
                    self.editor.setHtml(
                        TextParser.sanitize_theme_colors(doc.content, is_dark_surface, strip_theme_defaults=True)
                    )
                    self.editor.document().setModified(False)
                    self._suppress_undo_capture = False
                    self._prune_doc_text_undo(doc.id)
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
            self._select_document_by_id(self.current_document_id, prompt_save=False)
            return
        self._load_document_data(doc_id)

    def _save_current_document(self):
        if not self.current_document_id:
            return
        self._auto_save_note_if_needed()
        new_title = self.input_doc_title.text().strip() or "Sem título"
        doc = self.service.get_document(self.current_document_id)
        cat = doc.category if doc else "Geral"

        new_content = self.editor.toHtml()
        self.service.update_document(self.current_document_id, new_title, new_content, cat)
        self.editor.document().setModified(False)
        self._loaded_title = new_title

        self._refresh_sidebar_item_appearance(self.current_document_id)
        self._refresh_views()
        self._refresh_doc_terms_list()
        self.statusBar().showMessage("✓ Caderno salvo com sucesso!", 2500)

    def _filter_documents(self, text: str):
        query = text.strip().lower()
        for i in range(self.list_docs.count()):
            item = self.list_docs.item(i)
            item.setHidden(query not in item.text().lower())

    def _format_bold(self):
        if self.stack_center.currentIndex() != 1:
            return
        c = self.editor.textCursor()
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Weight.Normal if c.charFormat().fontWeight() == QFont.Weight.Bold else QFont.Weight.Bold)
        c.mergeCharFormat(fmt)

    def _format_italic(self):
        if self.stack_center.currentIndex() != 1:
            return
        c = self.editor.textCursor()
        fmt = QTextCharFormat()
        fmt.setFontItalic(not c.charFormat().fontItalic())
        c.mergeCharFormat(fmt)

    def _format_underline(self):
        if self.stack_center.currentIndex() != 1:
            return
        c = self.editor.textCursor()
        fmt = QTextCharFormat()
        fmt.setFontUnderline(not c.charFormat().fontUnderline())
        c.mergeCharFormat(fmt)

    def _format_font_color(self):
        if self.stack_center.currentIndex() != 1:
            return
        color = QColorDialog.getColor(title="Escolha a cor para as letras", parent=self)
        if color.isValid():
            c = self.editor.textCursor()
            fmt = QTextCharFormat()
            fmt.setForeground(color)
            c.mergeCharFormat(fmt)

    def _on_font_family_changed(self, font: QFont):
        family = font.family()
        c = self.editor.textCursor()
        if self.stack_center.currentIndex() == 1 and c.hasSelection():
            fmt = QTextCharFormat()
            fmt.setFontFamilies([family])
            c.mergeCharFormat(fmt)
        else:
            self.editor.setFontFamily(family)

    def _on_font_size_changed(self, value: int):
        self.font_size = value
        self.service.set_setting("font_size", str(value))
        c = self.editor.textCursor()
        if self.stack_center.currentIndex() == 1 and c.hasSelection():
            fmt = QTextCharFormat()
            fmt.setFontPointSize(value)
            c.mergeCharFormat(fmt)
        else:
            self._apply_editor_card_appearance()
            self._refresh_views()

    def _show_document_context_menu(self, position: QPoint):
        item = self.list_docs.itemAt(position)
        if not item:
            return

        doc_id = item.data(Qt.ItemDataRole.UserRole)
        doc_title = item.text()

        menu = QMenu(self)
        menu.addAction("✏️ Renomear", lambda: self._rename_document_dialog(doc_id, doc_title, item))
        menu.addAction("🎨 Cor do Card / Tema", lambda: self._change_document_card_color(doc_id))
        menu.addAction("📁 Mudar Categoria", lambda: self._change_document_category(doc_id))
        menu.addAction("🕒 Histórico de Versões", lambda: self._open_history_dialog(doc_id))
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
            clean = new_title.strip()
            self.service.rename_document(doc_id, clean)
            item.setText(clean)
            if self.current_document_id == doc_id:
                self._loaded_title = clean
                self.input_doc_title.setText(clean)
            self._push_undo_entry(UndoEntry(kind="doc_title", doc_id=doc_id, before=old_title, after=clean))

    def _duplicate_document_action(self, doc_id: str):
        if not self._check_and_prompt_save_changes():
            return
        new_doc = self.service.duplicate_document(doc_id)
        if new_doc:
            self._load_documents()
            self._select_document_by_id(new_doc.id, prompt_save=False)

    def _delete_document_action(self, doc_id: str, title: str):
        res = QMessageBox.question(
            self,
            "Excluir",
            f"Deseja excluir o caderno '{title}'?\nTodas as anotações dele serão apagadas.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if res == QMessageBox.StandardButton.Yes:
            if doc_id in self.document_cache:
                del self.document_cache[doc_id]
            self._undo_stack = [e for e in self._undo_stack if e.doc_id != doc_id]
            self._redo_stack = [e for e in self._redo_stack if e.doc_id != doc_id]
            self._update_undo_redo_buttons()
            self.service.delete_document(doc_id)
            if self.current_document_id == doc_id:
                self.current_document_id = None
            self._load_documents()

    def _select_document_by_id(self, doc_id: Optional[str], prompt_save: bool = True):
        if not doc_id:
            return
        if prompt_save and not self._check_and_prompt_save_changes():
            return
        for i in range(self.list_docs.count()):
            if self.list_docs.item(i).data(Qt.ItemDataRole.UserRole) == doc_id:
                self.list_docs.setCurrentRow(i)
                self._load_document_data(doc_id)
                break

    def _toggle_theme(self):
        new_theme = "light" if self.current_theme == "dark" else "dark"
        self._apply_theme(new_theme)

        is_dark = (new_theme == "dark")
        self.text_color = "#cdd6f4" if is_dark else "#1f2328"
        self.service.set_setting("text_color", self.text_color)

        for i in range(self.list_docs.count()):
            item = self.list_docs.item(i)
            doc_id = item.data(Qt.ItemDataRole.UserRole)
            doc = self.service.get_document(doc_id)
            if doc:
                self._style_sidebar_item(item, doc.card_color, is_dark)

        self.btn_theme.setText("☀️ Claro" if new_theme == "dark" else "🌙 Escuro")
        self._refresh_views()

    def _refresh_views(self):
        if not self.current_document_id:
            return
        doc = self.service.get_document(self.current_document_id)
        if doc:
            is_dark = (self.current_theme == "dark")
            sheet_bg, canvas_bg, text_c, border_c, _, is_dark_surface = resolve_card_style(doc.card_color, is_dark)

            terms = self.service.list_terms_for_document(self.current_document_id, clean_orphans=False)
            colors = {t.anchor_key: (getattr(t, "color", None) or "#ffe066") for t in terms}

            raw_source = self.editor.toHtml() if self.editor.document().isModified() else doc.content
            clean_content = TextParser.clean_legacy_tokens(raw_source, colors)
            styled_html = TextParser.wrap_in_page_style(
                clean_content,
                font_size=self.font_size,
                text_color=text_c,
                bg_color=sheet_bg,
                canvas_bg=canvas_bg,
                border_color=border_c,
                is_dark_surface=is_dark_surface,
            )
            self.reader.setHtml(styled_html)
            self._apply_editor_card_appearance()

        self.txt_term_note.setStyleSheet(f"font-size: {self.font_size}px; color: {self.text_color};")
        self._update_status_bar()

    def _set_center_mode(self, edit_mode: bool):
        if not self.current_document_id:
            self.stack_center.setCurrentIndex(2)
            self.edit_toolbar_group.setVisible(False)
            self.btn_toggle_mode.setEnabled(False)
            self.btn_flashcards.setEnabled(False)
            self.btn_card_color.setEnabled(False)
            self.lbl_category_badge.setEnabled(False)
            self.input_doc_title.setEnabled(False)
            return

        self.btn_toggle_mode.setEnabled(True)
        self.btn_flashcards.setEnabled(True)
        self.btn_card_color.setEnabled(True)
        self.lbl_category_badge.setEnabled(True)
        self.input_doc_title.setEnabled(True)

        if edit_mode:
            self.stack_center.setCurrentIndex(1)
            self.btn_toggle_mode.setText("📖 Modo Leitura")
            self.edit_toolbar_group.setVisible(True)
        else:
            self.stack_center.setCurrentIndex(0)
            self.btn_toggle_mode.setText("✏️ Modo Edição")
            self.edit_toolbar_group.setVisible(False)

    def _load_documents(self):
        self._is_loading = True
        self.list_docs.clear()
        selected_cat = self.combo_categories.currentText()
        docs = self.service.list_documents(category_filter=selected_cat)
        is_dark = (self.current_theme == "dark")

        for doc in docs:
            item = QListWidgetItem(doc.title)
            item.setData(Qt.ItemDataRole.UserRole, doc.id)
            self._style_sidebar_item(item, doc.card_color, is_dark)
            self.list_docs.addItem(item)
        self._is_loading = False

        if docs:
            self.list_docs.setCurrentRow(0)
            self._load_document_data(docs[0].id)
            self._set_center_mode(edit_mode=(self.stack_center.currentIndex() == 1))
        else:
            self.current_document_id = None
            self._loaded_title = ""
            self.input_doc_title.clear()
            self.lbl_category_badge.setText("📁 Geral")
            self._suppress_undo_capture = True
            self.editor.clear()
            self.reader.clear()
            self._suppress_undo_capture = False
            self._clear_active_term()
            self._refresh_doc_terms_list()
            self._on_modification_changed(False)
            self._set_center_mode(edit_mode=False)
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
            if self.current_document_id != doc.id:
                self._select_document_by_id(doc.id, prompt_save=False)

    def _load_document_data(self, doc_id: str):
        doc = self.service.get_document(doc_id)
        if not doc:
            return

        self._auto_save_note_if_needed()
        self.current_document_id = doc.id
        self._loaded_title = doc.title
        self.input_doc_title.setText(doc.title)
        self.lbl_category_badge.setText(f"📁 {doc.category}")

        is_dark = (self.current_theme == "dark")
        _, _, _, _, _, is_dark_surface = resolve_card_style(doc.card_color, is_dark)

        if doc_id not in self.document_cache:
            clean_content = TextParser.clean_legacy_tokens(doc.content)
            normalized_content = TextParser.sanitize_theme_colors(
                clean_content,
                is_dark_surface,
                strip_theme_defaults=True,
            )
            qdoc = QTextDocument(self)
            opt = QTextOption()
            opt.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
            qdoc.setDefaultTextOption(opt)
            self._suppress_undo_capture = True
            qdoc.setHtml(normalized_content)
            qdoc.setModified(False)
            self._suppress_undo_capture = False
            qdoc.undoCommandAdded.connect(lambda did=doc_id: self._on_qdoc_undo_added(did))
            qdoc.modificationChanged.connect(
                lambda mod, did=doc_id: self._on_modification_changed(mod) if did == self.current_document_id else None
            )
            self.document_cache[doc_id] = qdoc

        self.editor.setDocument(self.document_cache[doc_id])
        self._on_modification_changed(self.document_cache[doc_id].isModified())
        self._set_center_mode(edit_mode=(self.stack_center.currentIndex() == 1))
        self._refresh_views()
        self._clear_active_term()
        self._refresh_doc_terms_list()
        self._update_status_bar()
        self._update_page_margins()

    def _toggle_mode(self):
        if not self.current_document_id:
            return

        if self.stack_center.currentIndex() == 0:
            self._set_center_mode(edit_mode=True)
        else:
            if not self._check_and_prompt_save_changes():
                return
            self._set_center_mode(edit_mode=False)
            self._refresh_views()

    def _on_anchor_clicked(self, url: QUrl):
        u = url.toString()
        if u.startswith("anchor:"):
            self._load_active_term(u.replace("anchor:", ""))

    def _save_note_changes(self):
        if not self.current_anchor_key or not self.current_document_id:
            return
        new_text = self.txt_term_note.toPlainText().strip()
        old_text = self._loaded_note_text
        self.service.update_term_note(self.current_anchor_key, new_text)
        self._loaded_note_text = new_text
        self.txt_term_note.document().setModified(False)
        self._update_note_save_button(False)
        if new_text != old_text.strip():
            self._push_undo_entry(
                UndoEntry(
                    kind="term_note",
                    doc_id=self.current_document_id,
                    before=old_text,
                    after=new_text,
                    extra=self.current_anchor_key,
                )
            )
        self.statusBar().showMessage("✓ Anotação atualizada!", 2500)

    def _open_settings_dialog(self):
        dlg = SettingsDialog(self.service, self)
        if dlg.exec():
            self._bind_shortcuts()
            self._update_shortcut_tooltips()
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
                self._select_document_by_id(new_doc.id, prompt_save=False)
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
        pos = (
            self.btn_menu_file.mapToGlobal(QPoint(0, self.btn_menu_file.height()))
            if self.top_toolbar.isVisible()
            else QCursor.pos()
        )
        menu.exec(pos)

    def _export_document_pdf(self, doc_id: str):
        if self.stack_center.currentIndex() == 1 and doc_id == self.current_document_id:
            self._save_current_document()
        doc = self.service.get_document(doc_id)
        if not doc:
            return

        safe_title = "".join(c for c in doc.title if c.isalnum() or c in (" ", "_", "-")).strip() or "documento"
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
        safe_title = "".join(c for c in doc.title if c.isalnum() or c in (" ", "_", "-")).strip() or "caderno"
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
        safe_title = "".join(c for c in doc.title if c.isalnum() or c in (" ", "_", "-")).strip() or "caderno"
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
    icon_path = ASSETS_DIR / "icon.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    window = MainWindow()
    if icon_path.exists():
        window.setWindowIcon(QIcon(str(icon_path)))

    theme_filter = WindowThemeFilter(window)
    app.installEventFilter(theme_filter)

    window.show()
    sys.exit(app.exec())