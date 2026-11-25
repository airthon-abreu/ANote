import sys
import ctypes
from ctypes import c_int, sizeof
from datetime import datetime
from typing import Tuple

from PySide6.QtCore import Qt, QObject, QEvent
from PySide6.QtGui import QColor, QIcon, QPixmap, QPainter
from PySide6.QtWidgets import QWidget

HIGHLIGHT_PRESETS = [
    ("#ffe066", "Amarelo"),
    ("#b7e4c7", "Verde Menta"),
    ("#a8dadc", "Azul Céu"),
    ("#ffcbf2", "Rosa"),
    ("#ffd1a9", "Laranja"),
    ("#e0c3fc", "Lilás"),
]

# Paleta estilo Google Keep: (chave, nome, fundo_claro, fundo_escuro)
KEEP_CARD_COLORS = [
    ("", "Padrão do Tema", "#ffffff", "#181825"),
    ("keep:coral", "Coral", "#faafa8", "#77172e"),
    ("keep:peach", "Pêssego", "#f39f76", "#692b17"),
    ("keep:sand", "Areia", "#fff8b8", "#7c4a03"),
    ("keep:mint", "Menta", "#e2f6d3", "#264d3b"),
    ("keep:sage", "Sálvia", "#b4ddd3", "#0c625d"),
    ("keep:fog", "Névoa", "#d4e4ed", "#256377"),
    ("keep:storm", "Tempestade", "#aeccdc", "#284255"),
    ("keep:dusk", "Crepúsculo", "#d3bfdb", "#472e5b"),
    ("keep:blossom", "Flor", "#f6e2dd", "#6c394f"),
    ("keep:clay", "Argila", "#e9e3d4", "#4b443a"),
]
KEEP_COLOR_MAP = {k: (name, light_hex, dark_hex) for k, name, light_hex, dark_hex in KEEP_CARD_COLORS}

DEFAULT_SHORTCUTS = {
    "save_doc": ("Ctrl+S", "Salvar Documento Atual"),
    "undo": ("Ctrl+Z", "Desfazer (Global)"),
    "redo": ("Ctrl+Shift+Z", "Refazer (Global)"),
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


def resolve_card_style(card_color: str, is_dark: bool) -> Tuple[str, str, str, str, str, bool]:
    """
    Retorna: (sheet_bg, canvas_bg, text_color, border_color, swatch_color, is_dark_surface)
    """
    canvas_bg = "#11111b" if is_dark else "#eef0f4"
    if not card_color:
        if is_dark:
            return ("#181825", canvas_bg, "#cdd6f4", "#313244", "#313244", True)
        return ("#ffffff", canvas_bg, "#1f2328", "#d0d7de", "#d0d7de", False)

    if card_color in KEEP_COLOR_MAP:
        _, light_hex, dark_hex = KEEP_COLOR_MAP[card_color]
        sheet_bg = dark_hex if is_dark else light_hex
        text_color = "#f1f5f9" if is_dark else "#1f2328"
        border_color = QColor(sheet_bg).lighter(135).name() if is_dark else QColor(sheet_bg).darker(118).name()
        return (sheet_bg, canvas_bg, text_color, border_color, sheet_bg, is_dark)

    c = QColor(card_color)
    if not c.isValid():
        return resolve_card_style("", is_dark)

    luminance = 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
    is_dark_surface = luminance < 140
    text_color = "#f8fafc" if is_dark_surface else "#1f2328"
    border_color = c.lighter(135).name() if is_dark_surface else c.darker(118).name()
    return (c.name(), canvas_bg, text_color, border_color, c.name(), is_dark_surface)


def make_color_dot_icon(hex_color: str, border_hex: str = "#666666", size: int = 14) -> QIcon:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QColor(border_hex))
    painter.setBrush(QColor(hex_color))
    painter.drawEllipse(1, 1, size - 2, size - 2)
    painter.end()
    return QIcon(pix)


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


def format_display_timestamp(raw_ts: str) -> str:
    try:
        return datetime.fromisoformat(raw_ts).strftime("%d/%m/%Y %H:%M:%S")
    except ValueError:
        return raw_ts


class WindowThemeFilter(QObject):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Show and isinstance(watched, QWidget) and watched.isWindow():
            is_dark = (self.main_window.current_theme == "dark")
            apply_windows_dark_titlebar(watched, is_dark)
        return super().eventFilter(watched, event)