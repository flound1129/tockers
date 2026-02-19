import re
from pathlib import Path

import cv2
import numpy as np

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QLineEdit, QPushButton, QLabel, QFrame, QComboBox,
    QSpinBox, QGridLayout, QCheckBox, QApplication,
    QSizePolicy, QScrollArea,
)
from PyQt6.QtCore import QThread, Qt, QRect, QTimer
from PyQt6.QtCore import pyqtSlot
from PyQt6.QtCore import pyqtSignal as Signal
from PyQt6.QtGui import QFont, QPainter, QPen, QColor, QImage, QPixmap, QBrush

from overlay.config import ScreenRegion, CALIBRATION_PATH
from overlay.vision import _load_champion_names, _ocr_text
from overlay.bridge import start_bridge, PROJECT_ROOT


# Which regions get live OCR preview, with their OCR parameters
OCR_CONFIGS = {
    "round_text":  {"scale": 3, "method": "threshold", "threshold_val": 140, "psm": 7},
    "gold_text":   {"scale": 5, "method": "threshold", "threshold_val": 140, "psm": 8, "whitelist": "0123456789"},
    "lives_text":  {"scale": 5, "method": "threshold", "threshold_val": 140, "psm": 7, "whitelist": "0123456789"},
    "level_text":  {"scale": 4, "method": "adaptive", "psm": 7},
    "rerolls_text": {"scale": 5, "method": "threshold", "threshold_val": 140, "psm": 8, "whitelist": "0123456789"},
    "ionia_trait_text": {"scale": 4, "method": "adaptive", "psm": 7},
    "dmg_amount":   {"scale": 5, "method": "threshold", "threshold_val": 140, "psm": 8, "whitelist": "0123456789"},
    "augment_name_0": {"scale": 3, "method": "adaptive", "psm": 7},
    "augment_name_1": {"scale": 3, "method": "adaptive", "psm": 7},
    "augment_name_2": {"scale": 3, "method": "adaptive", "psm": 7},
    "shop_card_0": {"scale": 4, "method": "adaptive", "psm": 11},
    "shop_card_1": {"scale": 4, "method": "adaptive", "psm": 11},
    "shop_card_2": {"scale": 4, "method": "adaptive", "psm": 11},
    "shop_card_3": {"scale": 4, "method": "adaptive", "psm": 11},
    "shop_card_4": {"scale": 4, "method": "adaptive", "psm": 11},
}

# Built-in region names (always present), alphabetized
BUILTIN_REGION_NAMES = sorted([
    "augment_icons", "augment_name_0", "augment_name_1", "augment_name_2",
    "augment_select", "board", "champion_bench",
    "dmg_amount", "dmg_bar", "dmg_champ", "dmg_stars",
    "gold_text", "ionia_trait_text", "item_bench", "level_text", "lives_text",
    "rerolls_text", "round_text", "score_display", "selected_augment_text",
    "shop_card_0", "shop_card_1", "shop_card_2", "shop_card_3", "shop_card_4",
    "trait_panel",
])

# ── Theme ─────────────────────────────────────────────────────────

DARK_THEME = """
    QWidget { background-color: #1a1a2e; color: #e0e0e0; }
    QFrame { background-color: #16213e; border: 1px solid #0f3460; border-radius: 6px; }
    QLabel { border: none; background: transparent; }
    QPushButton {
        background-color: #0f3460; color: #e0e0e0; border: 1px solid #533483;
        border-radius: 4px; padding: 4px 12px;
    }
    QPushButton:hover { background-color: #533483; }
    QPushButton:pressed { background-color: #7b2d8e; }
    QComboBox {
        background-color: #0f3460; color: #e0e0e0; border: 1px solid #533483;
        border-radius: 4px; padding: 2px 8px;
    }
    QComboBox QAbstractItemView {
        background-color: #000000; color: #e0e0e0;
        selection-background-color: #533483;
        border: 1px solid #533483;
    }
    QComboBox::drop-down {
        background-color: #0f3460; border: none;
    }
    QSpinBox {
        background-color: #0f3460; color: #e0e0e0; border: 1px solid #533483;
        border-radius: 4px; padding: 2px 4px;
    }
    QTextEdit {
        background-color: #0d1b2a; color: #e0e0e0; border: 1px solid #0f3460;
        border-radius: 4px;
    }
    QLineEdit {
        background-color: #0d1b2a; color: #e0e0e0; border: 1px solid #0f3460;
        border-radius: 4px; padding: 4px 8px;
    }
    QCheckBox { background: transparent; border: none; }
    QScrollArea { border: none; background: transparent; }
    QScrollBar:vertical {
        background: #0d1b2a; width: 8px; border-radius: 4px;
    }
    QScrollBar::handle:vertical {
        background: #533483; border-radius: 4px; min-height: 20px;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""

# Color constants
CLR_GOLD = "#FFD700"
CLR_RED = "#FF6B6B"
CLR_GREEN = "#69DB7C"
CLR_BLUE = "#74C0FC"
CLR_GRAY = "#868E96"
CLR_ORANGE = "#FFA94D"
CLR_PURPLE = "#B197FC"
CLR_DIMMED = "#495057"


# ── Score Breakdown Bar ──────────────────────────────────────────

class ScoreBreakdownBar(QWidget):
    """Horizontal bar showing score component proportions."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(14)
        self._segments: list[tuple[float, QColor, str]] = []  # (value, color, label)

    def set_segments(self, segments: list[tuple[float, str]]):
        """Set segments as [(value, hex_color), ...]."""
        total = sum(v for v, _ in segments)
        if total <= 0:
            self._segments = []
            self.update()
            return
        self._segments = [
            (v / total, QColor(c), "")
            for v, c in segments if v > 0
        ]
        self.update()

    def paintEvent(self, event):
        if not self._segments:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()
        x = 0.0
        for frac, color, _ in self._segments:
            seg_w = frac * w
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(int(x), 0, max(int(seg_w), 1), h, 3, 3)
            x += seg_w
        painter.end()


# ── Collapsible Section ──────────────────────────────────────────

class CollapsibleSection(QFrame):
    """A frame with a clickable header that toggles content visibility."""

    def __init__(self, title: str, collapsed: bool = True, parent=None):
        super().__init__(parent)
        self._collapsed = collapsed
        self._title = title

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header button
        self._header = QPushButton()
        self._header.setStyleSheet(
            "QPushButton { text-align: left; padding: 6px 10px; "
            "font-family: Consolas; font-size: 12pt; font-weight: bold; "
            "background-color: #16213e; border: 1px solid #0f3460; border-radius: 4px; }"
            "QPushButton:hover { background-color: #1a2744; }"
        )
        self._header.clicked.connect(self.toggle)
        main_layout.addWidget(self._header)

        # Content container
        self._content = QFrame()
        self._content.setStyleSheet("QFrame { border: none; background: transparent; }")
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(6, 4, 6, 6)
        self._content_layout.setSpacing(4)
        main_layout.addWidget(self._content)

        self._update_header()
        self._content.setVisible(not collapsed)

    def _update_header(self):
        arrow = "\u25BC" if not self._collapsed else "\u25B6"
        self._header.setText(f"  {arrow}  {self._title}")

    def toggle(self):
        self._collapsed = not self._collapsed
        self._content.setVisible(not self._collapsed)
        self._update_header()

    def content_layout(self) -> QVBoxLayout:
        return self._content_layout

    def set_collapsed(self, collapsed: bool):
        if self._collapsed != collapsed:
            self.toggle()


# ── Helper widgets ───────────────────────────────────────────────

class RegionOverlay(QWidget):
    """Transparent full-screen overlay that draws red rectangles on regions."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Region Debug")
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._regions: list[tuple[QRect, str]] = []  # (rect, label)

    def set_regions(self, regions: list[tuple[QRect, str]]):
        self._regions = regions
        self.update()

    def paintEvent(self, event):
        if not self._regions:
            return
        painter = QPainter(self)
        pen = QPen(QColor(255, 0, 0), 2)
        painter.setPen(pen)
        font = painter.font()
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)
        for rect, label in self._regions:
            painter.drawRect(rect)
            if label:
                painter.drawText(rect.x() + 4, rect.y() - 4, label)
        painter.end()


class _AiWorker(QThread):
    finished = Signal(str, str)  # (response_text, original_question)
    error = Signal(str)

    def __init__(self, engine, game_state_text: str, question: str,
                 history: list[dict]):
        super().__init__()
        self.engine = engine
        self.game_state_text = game_state_text
        self.question = question
        self.history = history

    def run(self):
        try:
            response = self.engine.ask_claude(
                self.game_state_text, self.question, history=self.history
            )
            self.finished.emit(str(response), self.question)
        except Exception as e:
            self.error.emit(str(e))


class _OcrWorker(QThread):
    """Run OCR on a crop image in a background thread."""
    finished = Signal(str)  # ocr result text

    def __init__(self, crop: np.ndarray, ocr_config: dict):
        super().__init__()
        self._crop = crop
        self._config = ocr_config

    def run(self):
        try:
            text = _ocr_text(
                self._crop,
                scale=self._config.get("scale", 4),
                method=self._config.get("method", "threshold"),
                threshold_val=self._config.get("threshold_val", 140),
                psm=self._config.get("psm", 7),
                whitelist=self._config.get("whitelist", ""),
            )
            self.finished.emit(text)
        except Exception as e:
            self.finished.emit(f"[error: {e}]")


# ── Status Card ──────────────────────────────────────────────────

def _make_status_card(label_text: str, value_text: str, value_color: str,
                      parent=None) -> tuple[QFrame, QLabel]:
    """Create a mini status card with a dim label and prominent value."""
    card = QFrame(parent)
    card.setStyleSheet(
        f"QFrame {{ background-color: #0d1b2a; border: 1px solid #0f3460; "
        f"border-radius: 4px; padding: 2px; }}"
    )
    card_layout = QVBoxLayout(card)
    card_layout.setContentsMargins(6, 2, 6, 2)
    card_layout.setSpacing(0)

    lbl = QLabel(label_text)
    lbl.setFont(QFont("Consolas", 8))
    lbl.setStyleSheet(f"color: {CLR_GRAY};")
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    card_layout.addWidget(lbl)

    val = QLabel(value_text)
    val.setFont(QFont("Consolas", 14, QFont.Weight.Bold))
    val.setStyleSheet(f"color: {value_color};")
    val.setAlignment(Qt.AlignmentFlag.AlignCenter)
    card_layout.addWidget(val)

    return card, val


# ── Main Companion Window ────────────────────────────────────────

class CompanionWindow(QWidget):
    def __init__(self, engine, layout=None, parent=None):
        super().__init__(parent)
        self.engine = engine
        self._layout = layout
        self._history: list[dict] = []
        self._current_game_state_text = ""
        self._worker: _AiWorker | None = None
        self._ocr_worker: _OcrWorker | None = None
        self._last_frame: np.ndarray | None = None
        self._ionia_path: str | None = None
        self._ionia_locked: bool = False
        self._picked_augments: list[str] = []  # confirmed picks (up to 3)
        self._all_seen_augments: set[str] = set()  # all unique names seen this augment round
        self._current_augment_round: str | None = None  # "1-5", "2-5", or "3-5"
        self._current_choices: list[str] = []  # current 3 detected augment names
        self._augment_scores: dict[str, float] = {}
        self._reader: object | None = None  # set externally for right-click scan
        try:
            self._augment_scores = engine.get_augment_scores()
        except Exception:
            pass
        self._champ_names: list[str] = _load_champion_names()
        self._region_overlay = RegionOverlay()
        self._bridge_server = start_bridge()
        self._ocr_debounce = QTimer()
        self._ocr_debounce.setSingleShot(True)
        self._ocr_debounce.setInterval(500)
        self._ocr_debounce.timeout.connect(self._run_ocr_preview)
        self.setWindowTitle("Tocker's Companion")
        self.resize(525, 900)
        self.move(50, 50)
        self.setStyleSheet(DARK_THEME)
        self._init_ui()

    def closeEvent(self, event):
        if self._worker is not None and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(2000)
        if self._ocr_worker is not None and self._ocr_worker.isRunning():
            self._ocr_worker.quit()
            self._ocr_worker.wait(1000)
        self._region_overlay.close()
        if self._bridge_server is not None:
            self._bridge_server.close()
        super().closeEvent(event)

    def __del__(self):
        if self._worker is not None and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(2000)

    # ── UI setup ──────────────────────────────────────────────────────

    def _init_ui(self):
        root = QVBoxLayout()
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        # Scrollable content area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_widget = QWidget()
        layout = QVBoxLayout(scroll_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # 1. Score Dashboard
        self.game_info_panel = self._build_score_dashboard()
        layout.addWidget(self.game_info_panel)

        # 2. Status Bar
        status_bar = self._build_status_bar()
        layout.addLayout(status_bar)

        # 3. Strategy Section (Ionia + Augments)
        strategy = self._build_strategy_section()
        layout.addWidget(strategy)

        # 4. Collapsible: Board & Bench
        self._board_section = CollapsibleSection("Board & Bench", collapsed=True)
        self._board_label = QLabel("\u2014")
        self._board_label.setFont(QFont("Consolas", 11))
        self._board_label.setWordWrap(True)
        self._board_label.setStyleSheet(f"color: {CLR_BLUE};")
        self._bench_label = QLabel("\u2014")
        self._bench_label.setFont(QFont("Consolas", 11))
        self._bench_label.setWordWrap(True)
        self._bench_label.setStyleSheet(f"color: {CLR_GRAY};")
        self._board_section.content_layout().addWidget(self._board_label)
        self._board_section.content_layout().addWidget(self._bench_label)
        layout.addWidget(self._board_section)

        # 5. Collapsible: Shop
        self._shop_section = CollapsibleSection("Shop", collapsed=True)
        self._shop_label = QLabel("\u2014")
        self._shop_label.setFont(QFont("Consolas", 11))
        self._shop_label.setWordWrap(True)
        self._shop_section.content_layout().addWidget(self._shop_label)
        layout.addWidget(self._shop_section)

        # 6. Collapsible: Calibration
        self._cal_section = CollapsibleSection("Calibration", collapsed=True)
        self._build_calibration_content(self._cal_section.content_layout())
        self.calibration_panel = self._cal_section
        layout.addWidget(self._cal_section)

        # 7. Collapsible: Chat (expanded)
        self._chat_section = CollapsibleSection("Chat", collapsed=False)
        self._build_chat_content(self._chat_section.content_layout())
        self.chat_panel = self._chat_section
        layout.addWidget(self._chat_section)

        layout.addStretch()
        scroll.setWidget(scroll_widget)
        root.addWidget(scroll, stretch=1)

        # Input bar always visible at bottom
        self.input_bar = self._build_input()
        root.addWidget(self.input_bar, stretch=0)

        self.setLayout(root)

    def _build_score_dashboard(self) -> QFrame:
        frame = QFrame()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        # Projected score - large gold text
        score_row = QHBoxLayout()
        score_label = QLabel("PROJECTED SCORE")
        score_label.setFont(QFont("Consolas", 8))
        score_label.setStyleSheet(f"color: {CLR_GRAY};")
        score_row.addWidget(score_label)
        score_row.addStretch()
        layout.addLayout(score_row)

        self._score_value = QLabel("0")
        self._score_value.setFont(QFont("Consolas", 22, QFont.Weight.Bold))
        self._score_value.setStyleSheet(f"color: {CLR_GOLD};")
        self._score_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._score_value)

        # Score breakdown bar
        self._score_bar = ScoreBreakdownBar()
        layout.addWidget(self._score_bar)

        # Legend row for breakdown bar
        legend = QHBoxLayout()
        legend.setSpacing(12)
        for label, color in [("Components", CLR_RED), ("Interest", CLR_GREEN),
                              ("Survival", CLR_BLUE), ("Time", CLR_GRAY)]:
            dot = QLabel("\u25CF")
            dot.setFont(QFont("Consolas", 8))
            dot.setStyleSheet(f"color: {color};")
            dot.setFixedWidth(10)
            txt = QLabel(label)
            txt.setFont(QFont("Consolas", 8))
            txt.setStyleSheet(f"color: {CLR_DIMMED};")
            legend.addWidget(dot)
            legend.addWidget(txt)
        legend.addStretch()
        layout.addLayout(legend)

        # Components card - prominent
        comp_row = QHBoxLayout()
        comp_icon = QLabel("\u2692")  # hammer and pick
        comp_icon.setFont(QFont("Consolas", 16))
        comp_icon.setStyleSheet(f"color: {CLR_ORANGE};")
        comp_icon.setFixedWidth(24)
        comp_row.addWidget(comp_icon)

        self._components_value = QLabel("0")
        self._components_value.setFont(QFont("Consolas", 16, QFont.Weight.Bold))
        self._components_value.setStyleSheet(f"color: {CLR_ORANGE};")
        comp_row.addWidget(self._components_value)

        comp_lbl = QLabel("components on bench")
        comp_lbl.setFont(QFont("Consolas", 10))
        comp_lbl.setStyleSheet(f"color: {CLR_GRAY};")
        comp_row.addWidget(comp_lbl)
        comp_row.addStretch()

        self._components_detail = QLabel("+0 pts")
        self._components_detail.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        self._components_detail.setStyleSheet(f"color: {CLR_RED};")
        comp_row.addWidget(self._components_detail)

        layout.addLayout(comp_row)

        return frame

    def _build_status_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.setSpacing(4)

        # Round card
        round_card, self._round_value = _make_status_card("ROUND", "--/30", CLR_BLUE)
        bar.addWidget(round_card)

        # Gold card
        gold_card, self._gold_value = _make_status_card("GOLD", "--", CLR_GOLD)
        bar.addWidget(gold_card)

        # Level card
        level_card, self._level_value = _make_status_card("LEVEL", "--", "#e0e0e0")
        bar.addWidget(level_card)

        # Lives card
        lives_card, self._lives_value = _make_status_card("LIVES", "--", CLR_RED)
        bar.addWidget(lives_card)

        return bar

    def _build_strategy_section(self) -> QFrame:
        frame = QFrame()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(4)

        header = QLabel("STRATEGY")
        header.setFont(QFont("Consolas", 8))
        header.setStyleSheet(f"color: {CLR_GRAY};")
        layout.addWidget(header)

        # Ionia path row
        ionia_row = QHBoxLayout()
        ionia_icon = QLabel("\u2694")  # crossed swords
        ionia_icon.setFont(QFont("Consolas", 14))
        ionia_icon.setStyleSheet(f"color: {CLR_PURPLE};")
        ionia_icon.setFixedWidth(20)
        ionia_row.addWidget(ionia_icon)
        self._ionia_label = QLabel("Ionia: --")
        self._ionia_label.setFont(QFont("Consolas", 12))
        self._ionia_label.setStyleSheet(f"color: {CLR_PURPLE};")
        self._ionia_unlock_btn = QPushButton("Unlock")
        self._ionia_unlock_btn.setFixedWidth(70)
        self._ionia_unlock_btn.clicked.connect(self._on_ionia_unlock)
        self._ionia_unlock_btn.setEnabled(False)
        ionia_row.addWidget(self._ionia_label, stretch=1)
        ionia_row.addWidget(self._ionia_unlock_btn, stretch=0)
        layout.addLayout(ionia_row)

        # Augments display
        self._augment_label = QLabel("Augments: --")
        self._augment_label.setFont(QFont("Consolas", 11))
        self._augment_label.setWordWrap(True)
        self._augment_label.setStyleSheet(f"color: {CLR_GOLD};")
        layout.addWidget(self._augment_label)

        # Augment recommendations (ranked by AI score)
        self._augment_rec_label = QLabel("")
        self._augment_rec_label.setFont(QFont("Consolas", 11))
        self._augment_rec_label.setWordWrap(True)
        self._augment_rec_label.setStyleSheet(f"color: {CLR_GRAY};")
        layout.addWidget(self._augment_rec_label)

        # Right-click hint
        hint = QLabel("Right-click to scan picked augment")
        hint.setFont(QFont("Consolas", 8))
        hint.setStyleSheet(f"color: {CLR_DIMMED};")
        layout.addWidget(hint)

        return frame

    def _build_calibration_content(self, v: QVBoxLayout):
        # Region selector
        self._region_combo = QComboBox()
        self._region_combo.addItems(BUILTIN_REGION_NAMES)
        self._region_combo.currentTextChanged.connect(self._on_region_changed)
        v.addWidget(self._region_combo)

        # Spin boxes in 2x2 grid
        grid = QGridLayout()
        grid.setSpacing(4)
        self._spin_x = self._make_spin("X:", 0, 2560)
        self._spin_y = self._make_spin("Y:", 0, 1440)
        self._spin_w = self._make_spin("W:", 1, 2560)
        self._spin_h = self._make_spin("H:", 1, 1440)
        grid.addWidget(QLabel("X:"), 0, 0)
        grid.addWidget(self._spin_x, 0, 1)
        grid.addWidget(QLabel("Y:"), 0, 2)
        grid.addWidget(self._spin_y, 0, 3)
        grid.addWidget(QLabel("W:"), 1, 0)
        grid.addWidget(self._spin_w, 1, 1)
        grid.addWidget(QLabel("H:"), 1, 2)
        grid.addWidget(self._spin_h, 1, 3)
        v.addLayout(grid)

        # Link shop cards checkbox
        self._link_cards_cb = QCheckBox("Link shop cards (Y/H)")
        self._link_cards_cb.setChecked(True)
        v.addWidget(self._link_cards_cb)

        # Crop preview
        self._crop_preview = QLabel()
        self._crop_preview.setFixedHeight(80)
        self._crop_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._crop_preview.setStyleSheet("background: #0d1b2a; border: 1px solid #0f3460;")
        v.addWidget(self._crop_preview)

        # OCR result
        self._ocr_label = QLabel("")
        self._ocr_label.setFont(QFont("Consolas", 11))
        self._ocr_label.setWordWrap(True)
        self._ocr_label.setStyleSheet(f"color: {CLR_GREEN};")
        v.addWidget(self._ocr_label)

        # Buttons row
        btn_row = QHBoxLayout()
        self._save_btn = QPushButton("Save")
        self._save_btn.clicked.connect(self._on_save_calibration)
        self._show_all_btn = QPushButton("Show All")
        self._show_all_btn.clicked.connect(self._on_show_all_regions)
        self._debug_btn = QPushButton("Debug")
        self._debug_btn.clicked.connect(self._on_debug_region)
        btn_row.addWidget(self._save_btn)
        btn_row.addWidget(self._show_all_btn)
        btn_row.addWidget(self._debug_btn)
        v.addLayout(btn_row)

        # Load initial region values
        self._loading_region = False
        self._on_region_changed(self._region_combo.currentText())

    def _make_spin(self, label: str, min_val: int, max_val: int) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(min_val, max_val)
        spin.setSingleStep(1)
        spin.setFont(QFont("Consolas", 11))
        spin.valueChanged.connect(self._on_spin_changed)
        return spin

    def _build_chat_content(self, v: QVBoxLayout):
        self._chat_display = QTextEdit()
        self._chat_display.setReadOnly(True)
        self._chat_display.setFont(QFont("Consolas", 11))
        self._chat_display.setMinimumHeight(120)
        v.addWidget(self._chat_display)

    def _build_input(self) -> QFrame:
        frame = QFrame()
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(6, 4, 6, 4)
        self._input_field = QLineEdit()
        self._input_field.setPlaceholderText("Ask a strategy question...")
        self._input_field.setFont(QFont("Consolas", 11))
        self._send_button = QPushButton("Send \u23ce")
        self._send_button.clicked.connect(self._on_send)
        self._input_field.returnPressed.connect(self._on_send)
        layout.addWidget(self._input_field, stretch=4)
        layout.addWidget(self._send_button, stretch=1)
        return frame

    # ── Calibration logic ─────────────────────────────────────────────

    def _get_region(self, name: str) -> ScreenRegion | None:
        if self._layout is None:
            return None
        if name.startswith("shop_card_"):
            idx = int(name.split("_")[-1])
            return self._layout.shop_card_names[idx]
        return getattr(self._layout, name, None)

    def _set_region(self, name: str, region: ScreenRegion):
        if self._layout is None:
            return
        if name.startswith("shop_card_"):
            idx = int(name.split("_")[-1])
            self._layout.shop_card_names[idx] = region
        else:
            setattr(self._layout, name, region)

    def _on_region_changed(self, name: str):
        region = self._get_region(name)
        if region is None:
            return
        self._loading_region = True
        self._spin_x.setValue(region.x)
        self._spin_y.setValue(region.y)
        self._spin_w.setValue(region.w)
        self._spin_h.setValue(region.h)
        self._loading_region = False
        self._update_preview()
        self._update_overlay_rect()

    def _on_spin_changed(self):
        if self._loading_region or self._layout is None:
            return
        name = self._region_combo.currentText()
        new_region = ScreenRegion(
            self._spin_x.value(), self._spin_y.value(),
            self._spin_w.value(), self._spin_h.value(),
        )
        self._set_region(name, new_region)

        # Link shop cards Y/H when checkbox is checked
        if (name.startswith("shop_card_") and self._link_cards_cb.isChecked()):
            for i in range(5):
                card_name = f"shop_card_{i}"
                if card_name != name:
                    old = self._get_region(card_name)
                    if old is not None:
                        self._set_region(card_name, ScreenRegion(
                            old.x, new_region.y, old.w, new_region.h,
                        ))

        self._update_preview()
        self._update_overlay_rect()
        # Debounce OCR
        self._ocr_debounce.start()

    def _update_preview(self):
        """Show the current crop from the live frame in the preview label."""
        if self._last_frame is None:
            self._crop_preview.setText("No frame")
            return
        name = self._region_combo.currentText()
        region = self._get_region(name)
        if region is None:
            return

        frame = self._last_frame
        fh, fw = frame.shape[:2]
        # Clamp to frame bounds
        x1 = max(0, min(region.x, fw - 1))
        y1 = max(0, min(region.y, fh - 1))
        x2 = max(x1 + 1, min(region.x + region.w, fw))
        y2 = max(y1 + 1, min(region.y + region.h, fh))
        crop = frame[y1:y2, x1:x2]

        # Convert BGR -> RGB -> QPixmap, scaled to fit
        rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, w * ch, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg)
        scaled = pixmap.scaled(
            self._crop_preview.width(), self._crop_preview.height(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._crop_preview.setPixmap(scaled)

    def _run_ocr_preview(self):
        """Run OCR on the current crop (called after debounce timer fires)."""
        name = self._region_combo.currentText()
        if name not in OCR_CONFIGS or self._last_frame is None:
            self._ocr_label.setText("")
            return

        region = self._get_region(name)
        if region is None:
            return

        frame = self._last_frame
        fh, fw = frame.shape[:2]
        x1 = max(0, min(region.x, fw - 1))
        y1 = max(0, min(region.y, fh - 1))
        x2 = max(x1 + 1, min(region.x + region.w, fw))
        y2 = max(y1 + 1, min(region.y + region.h, fh))
        crop = frame[y1:y2, x1:x2]

        # Run OCR in background thread
        if self._ocr_worker is not None and self._ocr_worker.isRunning():
            return
        self._ocr_worker = _OcrWorker(crop.copy(), OCR_CONFIGS[name])
        self._ocr_worker.finished.connect(
            self._on_ocr_result, Qt.ConnectionType.QueuedConnection
        )
        self._ocr_worker.start()

    @pyqtSlot(str)
    def _on_ocr_result(self, text: str):
        self._ocr_label.setText(f"OCR: {text}")

    def _update_overlay_rect(self):
        """Show a red rectangle on the game screen for the selected region."""
        if self._layout is None:
            return
        name = self._region_combo.currentText()
        region = self._get_region(name)
        if region is None:
            self._region_overlay.set_regions([])
            return

        screen = QApplication.primaryScreen()
        screen_w = screen.geometry().width()
        screen_h = screen.geometry().height()
        game_w, game_h = self._layout.resolution
        gx = max(0, (screen_w - game_w) // 2)
        gy = max(0, (screen_h - game_h) // 2)

        qt_rect = QRect(gx + region.x, gy + region.y, region.w, region.h)
        self._region_overlay.set_regions([(qt_rect, name)])
        self._region_overlay.setGeometry(0, 0, screen_w, screen_h)
        self._region_overlay.show()

    def _on_ionia_unlock(self):
        self._ionia_path = None
        self._ionia_locked = False
        self._ionia_label.setText("Ionia: --")
        self._ionia_unlock_btn.setEnabled(False)

    def _update_augment_display(self):
        if self._picked_augments:
            display = ", ".join(self._picked_augments)
            count = len(self._picked_augments)
            self._augment_label.setText(f"Augments ({count}/3): {display}")
        else:
            self._augment_label.setText("Augments: --")

    def _update_augment_recommendations(self):
        """Update the recommendation label with scored augments."""
        if not self._current_choices:
            self._augment_rec_label.setText("")
            return
        scored = []
        for name in self._current_choices:
            score = self._augment_scores.get(name)
            scored.append((name, score))
        # Sort by score descending (None last)
        scored.sort(key=lambda x: x[1] if x[1] is not None else -1, reverse=True)
        lines = []
        for i, (name, score) in enumerate(scored):
            score_str = f" (score: {score:.0f})" if score is not None else " (unscored)"
            if i == 0:
                lines.append(f'<span style="color: {CLR_GOLD};">\u2605 {name}{score_str}</span>')
            else:
                lines.append(f'<span style="color: {CLR_GRAY};">  {name}{score_str}</span>')
        self._augment_rec_label.setText("<br>".join(lines))

    def contextMenuEvent(self, event):
        """Right-click to scan the picked augment from the game screen."""
        if self._reader is None or self._last_frame is None:
            return
        name = self._reader.read_selected_augment(self._last_frame)
        if name and len(self._picked_augments) < 3:
            self._picked_augments.append(name)
            self._update_augment_display()
            self._append_message("Scan", f"Detected augment: {name}")

    def _on_save_calibration(self):
        if self._layout is None:
            return
        from overlay.calibration import save_calibration
        save_calibration(CALIBRATION_PATH, self._layout)
        self._append_message("Cal", f"Saved to {CALIBRATION_PATH}")

    def _on_show_all_regions(self):
        """Show all regions with labels on the game overlay for 10 seconds."""
        if self._layout is None:
            return

        screen = QApplication.primaryScreen()
        screen_w = screen.geometry().width()
        screen_h = screen.geometry().height()
        game_w, game_h = self._layout.resolution
        gx = max(0, (screen_w - game_w) // 2)
        gy = max(0, (screen_h - game_h) // 2)

        qt_regions = []
        for name in BUILTIN_REGION_NAMES:
            region = self._get_region(name)
            if region:
                qt_regions.append((
                    QRect(gx + region.x, gy + region.y, region.w, region.h),
                    name,
                ))

        self._region_overlay.set_regions(qt_regions)
        self._region_overlay.setGeometry(0, 0, screen_w, screen_h)
        self._region_overlay.show()

        # Auto-hide after 10 seconds
        QTimer.singleShot(10000, self._region_overlay.hide)

    def _on_debug_region(self):
        """Save a screenshot crop of the current region to debug_crops/."""
        if self._last_frame is None:
            self._append_message("Debug", "No frame available")
            return
        name = self._region_combo.currentText()
        region = self._get_region(name)
        if region is None:
            return

        frame = self._last_frame
        fh, fw = frame.shape[:2]
        x1 = max(0, min(region.x, fw - 1))
        y1 = max(0, min(region.y, fh - 1))
        x2 = max(x1 + 1, min(region.x + region.w, fw))
        y2 = max(y1 + 1, min(region.y + region.h, fh))
        crop = frame[y1:y2, x1:x2]

        out_dir = PROJECT_ROOT / "debug_crops"
        out_dir.mkdir(exist_ok=True)
        out_path = out_dir / f"{name}.png"
        cv2.imwrite(str(out_path), crop)
        self._append_message("Debug", f"Saved {name}.png ({crop.shape[1]}x{crop.shape[0]})")

    # ── Chat / AI ─────────────────────────────────────────────────────

    def _on_send(self):
        text = self._input_field.text().strip()
        if not text:
            return
        if self._worker is not None and self._worker.isRunning():
            return
        self._input_field.clear()
        self._send_button.setEnabled(False)
        self._input_field.setEnabled(False)
        self._append_message("You", text)
        self._append_message("AI", "thinking...")
        self._current_game_state_text = self._build_game_state_text()
        self._start_ai_request(text)

    def _build_game_state_text(self) -> str:
        """Build a text summary of the current game state for AI context."""
        parts = [
            f"Score: {self._score_value.text()}",
            f"Round: {self._round_value.text()}",
            f"Gold: {self._gold_value.text()}",
            f"Level: {self._level_value.text()}",
            f"Lives: {self._lives_value.text()}",
            f"Components: {self._components_value.text()}",
            f"Board: {self._board_label.text()}",
            f"Bench: {self._bench_label.text()}",
            f"Shop: {self._shop_label.text()}",
            f"Ionia: {self._ionia_label.text()}",
            f"Augments: {self._augment_label.text()}",
        ]
        return "\n".join(parts)

    def _append_message(self, sender: str, text: str):
        self._chat_display.append(f"[{sender}]  {text}\n")
        sb = self._chat_display.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _start_ai_request(self, question: str):
        self._worker = _AiWorker(
            self.engine,
            self._current_game_state_text,
            question,
            list(self._history),
        )
        self._worker.finished.connect(self._on_ai_response,
                                      Qt.ConnectionType.QueuedConnection)
        self._worker.error.connect(self._on_ai_error,
                                   Qt.ConnectionType.QueuedConnection)
        self._worker.start()

    @pyqtSlot(str, str)
    def _on_ai_response(self, response: str, question: str):
        self._send_button.setEnabled(True)
        self._input_field.setEnabled(True)
        text = self._chat_display.toPlainText()
        text = text.replace("[AI]  thinking...\n\n", "").replace("[AI]  thinking...\n", "")
        self._chat_display.setPlainText(text)
        self._append_message("AI", response)
        self._history.append({
            "role": "user",
            "content": f"Game state:\n{self._worker.game_state_text}\n\nQuestion: {question}",
        })
        self._history.append({"role": "assistant", "content": response})
        self._history = self._history[-20:]

    @pyqtSlot(str)
    def _on_ai_error(self, error: str):
        self._send_button.setEnabled(True)
        self._input_field.setEnabled(True)
        text = self._chat_display.toPlainText()
        text = text.replace("[AI]  thinking...\n\n", "").replace("[AI]  thinking...\n", "")
        self._chat_display.setPlainText(text)
        self._append_message("AI", f"Error: {error}")

    # ── Frame + game state ────────────────────────────────────────────

    def set_frame(self, frame: np.ndarray) -> None:
        """Store the latest captured frame and refresh calibration preview."""
        self._last_frame = frame
        self._update_preview()

    @staticmethod
    def _format_champions(champions: list) -> str:
        if not champions:
            return "\u2014"
        star_char = "\u2605"
        parts = []
        for m in champions:
            stars = star_char * m.stars if m.stars > 0 else ""
            parts.append(f"{m.name}{stars}")
        return ", ".join(parts)

    def update_game_state(self, state, projected_score: int = 0):
        # Reset on new game
        if state.round_number == "1-1":
            self._ionia_path = None
            self._ionia_locked = False
            self._ionia_unlock_btn.setEnabled(False)
            self._picked_augments = []
            self._all_seen_augments = set()
            self._current_augment_round = None
            self._current_choices = []
            self._update_augment_display()
            self._augment_rec_label.setText("")

        # Lock Ionia path once read
        if not self._ionia_locked and state.ionia_path:
            self._ionia_path = state.ionia_path
            self._ionia_locked = True
            self._ionia_unlock_btn.setEnabled(True)

        ionia_display = self._ionia_path or "--"
        locked_indicator = " [locked]" if self._ionia_locked else ""
        self._ionia_label.setText(f"Ionia: {ionia_display}{locked_indicator}")

        # Smart augment tracking — only process on actual augment rounds
        _AUGMENT_ROUNDS = {"1-5", "2-5", "3-5"}
        is_augment_round = state.round_number in _AUGMENT_ROUNDS
        if state.augment_choices and is_augment_round:
            # Detect new augment round (reset for each of 1-5, 2-5, 3-5)
            if state.round_number != self._current_augment_round:
                self._current_augment_round = state.round_number
                self._all_seen_augments = set()

            # Track all unique names seen (initial 3 + rerolled 3 = 6 max)
            for name in state.augment_choices:
                self._all_seen_augments.add(name)

            # Update recommendations when choices change
            new_set = set(state.augment_choices)
            old_set = set(self._current_choices)
            if new_set != old_set:
                self._current_choices = list(state.augment_choices)
                self._update_augment_recommendations()

        # Update score dashboard
        self._score_value.setText(f"{projected_score:,}")

        items_count = len(state.items_on_bench)
        items_value = items_count * 2500 * 30
        self._components_value.setText(str(items_count))
        self._components_detail.setText(f"+{items_value:,} pts")

        # Estimate score breakdown for the bar
        # Components (biggest driver), interest, survival, time
        interest_pts = 0
        if state.gold is not None:
            interest_per_round = min(state.gold // 10, 5) * 1000
            abs_round = self._round_to_int(state.round_number)
            remaining = max(0, 30 - abs_round)
            interest_pts = interest_per_round * remaining
        survival_pts = len(state.my_board) * 250 * 30
        time_pts = 2750 * 30
        self._score_bar.set_segments([
            (items_value, CLR_RED),
            (interest_pts, CLR_GREEN),
            (survival_pts, CLR_BLUE),
            (time_pts, CLR_GRAY),
        ])

        # Update status cards
        abs_round = self._round_to_int(state.round_number)
        self._round_value.setText(f"{abs_round}/30" if abs_round > 0 else "--/30")
        self._gold_value.setText(str(state.gold) if state.gold is not None else "--")
        self._level_value.setText(str(state.level) if state.level is not None else "--")

        hearts = "\u2665" * (state.lives or 0) if state.lives else "--"
        self._lives_value.setText(hearts)

        # Update board & bench
        board_str = self._format_champions(state.my_board)
        bench_str = self._format_champions(state.my_bench)
        self._board_label.setText(f"Board ({len(state.my_board)}): {board_str}")
        self._bench_label.setText(f"Bench ({len(state.my_bench)}): {bench_str}")

        # Update shop
        slots = state.shop or []
        shop_parts = []
        for i, name in enumerate(slots):
            shop_parts.append(f"{i+1}:{name}" if name else f"{i+1}:\u2014")
        self._shop_label.setText("  ".join(shop_parts) or "\u2014")

    def _round_to_int(self, round_str: str | None) -> int:
        if not round_str or "-" not in round_str:
            return 0
        try:
            stage, rnd = round_str.split("-")
            return (int(stage) - 1) * 10 + int(rnd)
        except ValueError:
            return 0
