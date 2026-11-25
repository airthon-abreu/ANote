import html
from typing import Dict, List

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QColorDialog, QDialog, QFrame, QGridLayout, QHBoxLayout,
    QHeaderView, QKeySequenceEdit, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QSplitter, QTableWidget,
    QTableWidgetItem, QTextBrowser, QVBoxLayout
)

from src.core.models import Term
from src.core.parser import TextParser
from src.core.services import NotebookService
from src.ui.components.theme_utils import (
    DEFAULT_SHORTCUTS,
    HIGHLIGHT_PRESETS,
    KEEP_CARD_COLORS,
    format_display_timestamp,
)


class ColorPickerPopup(QDialog):
    def __init__(self, parent=None, term_label: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Escolha a Cor")
        self.selected_color = "#ffe066"
        self.setFixedSize(310, 165)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.addWidget(QLabel(f"<b>Cor de destaque para:</b><br><i>{html.escape(term_label)}</i>"))

        box_colors = QHBoxLayout()
        box_colors.setSpacing(10)
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


class CardColorDialog(QDialog):
    """Seletor de cor e tema do card no estilo Google Keep."""

    def __init__(self, current_color: str, is_dark: bool, on_toggle_theme=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cor e Tema do Card - ANote")
        self.selected_color = current_color
        self.on_toggle_theme = on_toggle_theme
        self.setFixedSize(390, 265)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        layout.addWidget(QLabel("<b>Escolha a cor do card deste caderno:</b>"))

        grid = QGridLayout()
        grid.setSpacing(10)
        for idx, (key, name, light_hex, dark_hex) in enumerate(KEEP_CARD_COLORS):
            swatch = dark_hex if is_dark else light_hex
            is_active = (current_color == key)
            border = "#89b4fa" if is_active else ("#585b70" if is_dark else "#9ca3af")
            btn = QPushButton("✓" if is_active else ("∅" if key == "" else ""))
            btn.setFixedSize(42, 42)
            btn.setToolTip(name)
            text_c = "#f8fafc" if is_dark else "#1f2328"
            btn.setStyleSheet(
                f"background-color: {swatch}; color: {text_c}; font-weight: bold; "
                f"border-radius: 21px; border: {'3px' if is_active else '2px'} solid {border};"
            )
            btn.clicked.connect(lambda _, k=key: self._pick(k))
            grid.addWidget(btn, idx // 6, idx % 6)

        layout.addLayout(grid)

        row_actions = QHBoxLayout()
        btn_custom = QPushButton("🎨 Cor Personalizada...")
        btn_custom.clicked.connect(self._pick_custom)
        row_actions.addWidget(btn_custom)

        if self.on_toggle_theme:
            btn_theme = QPushButton("☀️ Mudar para Claro" if is_dark else "🌙 Mudar para Escuro")
            btn_theme.clicked.connect(self._toggle_theme_clicked)
            row_actions.addWidget(btn_theme)

        layout.addLayout(row_actions)

    def _pick(self, color_key: str):
        self.selected_color = color_key
        self.accept()

    def _pick_custom(self):
        c = QColorDialog.getColor(title="Escolha uma cor para o card", parent=self)
        if c.isValid():
            self.selected_color = c.name()
            self.accept()

    def _toggle_theme_clicked(self):
        if self.on_toggle_theme:
            self.on_toggle_theme()
        self.reject()


class HistoryDialog(QDialog):
    def __init__(self, service: NotebookService, doc_id: str, is_dark: bool = True, parent=None):
        super().__init__(parent)
        self.service = service
        self.doc_id = doc_id
        self.is_dark = is_dark
        self.restored_content = None

        self.setWindowTitle("Histórico de Modificações - ANote")
        self.resize(720, 500)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        layout.addWidget(QLabel("<b>Selecione uma versão anterior para restaurar:</b>"))

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(self.splitter, 1)

        self.list_history = QListWidget()
        self.list_history.itemClicked.connect(self._on_item_clicked)
        self.splitter.addWidget(self.list_history)

        self.preview = QTextBrowser()
        self.splitter.addWidget(self.preview)
        self.splitter.setSizes([260, 460])

        self.snapshots = self.service.list_history_snapshots(self.doc_id)
        for s in self.snapshots:
            display_dt = format_display_timestamp(s["saved_at"])
            item = QListWidgetItem(f"🕒 {display_dt}")
            item.setData(Qt.ItemDataRole.UserRole, s["id"])
            self.list_history.addItem(item)

        bar_actions = QHBoxLayout()
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.clicked.connect(self.reject)
        bar_actions.addWidget(btn_cancel)

        bar_actions.addStretch()

        self.btn_restore = QPushButton("Restaurar Esta Versão")
        self.btn_restore.setObjectName("btn_primary")
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
            safe_html = TextParser.sanitize_theme_colors(snap["content"], self.is_dark)
            self.preview.setHtml(safe_html)
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
        self.resize(550, 400)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        self.lbl_counter = QLabel()
        self.lbl_counter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_counter.setStyleSheet("font-weight: bold; font-size: 13px; color: #89b4fa;")
        layout.addWidget(self.lbl_counter)

        self.card_frame = QFrame()
        self.card_frame.setStyleSheet("""
            QFrame {
                border: 1px solid #313244;
                border-radius: 12px;
                padding: 24px;
            }
        """)
        card_layout = QVBoxLayout(self.card_frame)

        self.lbl_card_title = QLabel()
        self.lbl_card_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_card_title.setWordWrap(True)
        self.lbl_card_title.setStyleSheet("font-size: 22px; font-weight: bold; padding: 10px;")
        card_layout.addWidget(self.lbl_card_title)

        self.lbl_card_body = QLabel()
        self.lbl_card_body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_card_body.setWordWrap(True)
        self.lbl_card_body.setStyleSheet("font-size: 15px; line-height: 1.6; padding: 8px;")
        card_layout.addWidget(self.lbl_card_body)

        layout.addWidget(self.card_frame, 1)

        self.btn_flip = QPushButton("👀 Mostrar Anotação")
        self.btn_flip.setObjectName("btn_primary")
        self.btn_flip.setFixedHeight(44)
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

        badge_style = f"background-color: {t.color}; color: #111; padding: 4px 12px; border-radius: 6px;"
        self.lbl_card_title.setText(f'<span style="{badge_style}">{html.escape(t.term_text)}</span>')

        if self.showing_answer:
            formatted_note = html.escape(t.note_content).replace("\n", "<br>")
            self.lbl_card_body.setText(f"<div>{formatted_note}</div>")
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
        layout.setContentsMargins(16, 16, 16, 16)
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
        btn_save.setObjectName("btn_primary")
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