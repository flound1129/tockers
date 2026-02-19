import re
from pathlib import Path

import cv2
import numpy as np

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QLineEdit, QPushButton, QLabel, QFrame, QComboBox,
    QSpinBox, QGridLayout, QCheckBox, QApplication,
)
from PyQt6.QtCore import QThread, Qt, QRect, QTimer
from PyQt6.QtCore import pyqtSlot
from PyQt6.QtCore import pyqtSignal as Signal
from PyQt6.QtGui import QFont, QPainter, QPen, QColor, QImage, QPixmap

from overlay.config import ScreenRegion, CALIBRATION_PATH
from overlay.vision import _load_champion_names, _ocr_text


# Which regions get live OCR preview, with their OCR parameters
OCR_CONFIGS = {
    "round_text":  {"scale": 3, "method": "threshold", "threshold_val": 140, "psm": 7},
    "gold_text":   {"scale": 5, "method": "threshold", "threshold_val": 140, "psm": 8, "whitelist": "0123456789"},
    "lives_text":  {"scale": 5, "method": "threshold", "threshold_val": 140, "psm": 7, "whitelist": "0123456789"},
    "level_text":  {"scale": 4, "method": "adaptive", "psm": 7},
    "rerolls_text": {"scale": 5, "method": "threshold", "threshold_val": 140, "psm": 8, "whitelist": "0123456789"},
    "dmg_amount":   {"scale": 5, "method": "threshold", "threshold_val": 140, "psm": 8, "whitelist": "0123456789"},
    "shop_card_0": {"scale": 4, "method": "adaptive", "psm": 11},
    "shop_card_1": {"scale": 4, "method": "adaptive", "psm": 11},
    "shop_card_2": {"scale": 4, "method": "adaptive", "psm": 11},
    "shop_card_3": {"scale": 4, "method": "adaptive", "psm": 11},
    "shop_card_4": {"scale": 4, "method": "adaptive", "psm": 11},
}

# Built-in region names (always present), alphabetized
BUILTIN_REGION_NAMES = sorted([
    "augment_select", "board", "champion_bench",
    "dmg_amount", "dmg_bar", "dmg_champ", "dmg_stars",
    "gold_text", "item_bench", "level_text", "lives_text",
    "rerolls_text", "round_text", "score_display",
    "shop_card_0", "shop_card_1", "shop_card_2", "shop_card_3", "shop_card_4",
    "trait_panel",
])


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
        self._champ_names: list[str] = _load_champion_names()
        self._region_overlay = RegionOverlay()
        self._ocr_debounce = QTimer()
        self._ocr_debounce.setSingleShot(True)
        self._ocr_debounce.setInterval(500)
        self._ocr_debounce.timeout.connect(self._run_ocr_preview)
        self.setWindowTitle("Tocker's Companion")
        self.resize(420, 800)
        self.move(50, 50)
        self._init_ui()

    def closeEvent(self, event):
        if self._worker is not None and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(2000)
        if self._ocr_worker is not None and self._ocr_worker.isRunning():
            self._ocr_worker.quit()
            self._ocr_worker.wait(1000)
        self._region_overlay.close()
        super().closeEvent(event)

    def __del__(self):
        if self._worker is not None and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(2000)

    # ── UI setup ──────────────────────────────────────────────────────

    def _init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.game_info_panel = self._build_game_info()
        self.calibration_panel = self._build_calibration()
        self.chat_panel = self._build_chat()
        self.input_bar = self._build_input()

        layout.addWidget(self.game_info_panel, stretch=2)
        layout.addWidget(self.calibration_panel, stretch=3)
        layout.addWidget(self.chat_panel, stretch=4)
        layout.addWidget(self.input_bar, stretch=0)
        self.setLayout(layout)

    def _build_game_info(self) -> QFrame:
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(6, 6, 6, 6)
        self._info_label = QLabel("Waiting for game state...")
        self._info_label.setWordWrap(True)
        self._info_label.setFont(QFont("Consolas", 13))
        layout.addWidget(self._info_label)
        return frame

    def _build_calibration(self) -> QFrame:
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        v = QVBoxLayout(frame)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(4)

        # Header
        header = QLabel("Calibration")
        header.setFont(QFont("Consolas", 13, QFont.Weight.Bold))
        v.addWidget(header)

        # Region selector (built-in + any extra from calibration.json, all sorted)
        self._region_combo = QComboBox()
        all_names = list(BUILTIN_REGION_NAMES)
        if self._layout and self._layout.extra_regions:
            all_names.extend(self._layout.extra_regions.keys())
            all_names.sort()
        self._region_combo.addItems(all_names)
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
        self._crop_preview.setStyleSheet("background: #222; border: 1px solid #555;")
        v.addWidget(self._crop_preview)

        # OCR result
        self._ocr_label = QLabel("")
        self._ocr_label.setFont(QFont("Consolas", 12))
        self._ocr_label.setWordWrap(True)
        self._ocr_label.setStyleSheet("color: #0f0;")
        v.addWidget(self._ocr_label)

        # Buttons row
        btn_row = QHBoxLayout()
        self._save_btn = QPushButton("Save")
        self._save_btn.clicked.connect(self._on_save_calibration)
        self._show_all_btn = QPushButton("Show All")
        self._show_all_btn.clicked.connect(self._on_show_all_regions)
        btn_row.addWidget(self._save_btn)
        btn_row.addWidget(self._show_all_btn)
        v.addLayout(btn_row)

        # Load initial region values
        self._loading_region = False
        self._on_region_changed(self._region_combo.currentText())

        return frame

    def _make_spin(self, label: str, min_val: int, max_val: int) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(min_val, max_val)
        spin.setSingleStep(1)
        spin.setFont(QFont("Consolas", 12))
        spin.valueChanged.connect(self._on_spin_changed)
        return spin

    def _build_chat(self) -> QFrame:
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(6, 6, 6, 6)
        self._chat_display = QTextEdit()
        self._chat_display.setReadOnly(True)
        self._chat_display.setFont(QFont("Consolas", 13))
        layout.addWidget(self._chat_display)
        return frame

    def _build_input(self) -> QFrame:
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(6, 6, 6, 6)
        self._input_field = QLineEdit()
        self._input_field.setPlaceholderText("Ask a strategy question...")
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
        if hasattr(self._layout, name) and name != "extra_regions":
            return getattr(self._layout, name)
        return self._layout.extra_regions.get(name)

    def _set_region(self, name: str, region: ScreenRegion):
        if self._layout is None:
            return
        if name.startswith("shop_card_"):
            idx = int(name.split("_")[-1])
            self._layout.shop_card_names[idx] = region
        elif hasattr(self._layout, name) and name != "extra_regions":
            setattr(self._layout, name, region)
        else:
            self._layout.extra_regions[name] = region

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
        # All built-in regions
        for name in BUILTIN_REGION_NAMES:
            region = self._get_region(name)
            if region:
                qt_regions.append((
                    QRect(gx + region.x, gy + region.y, region.w, region.h),
                    name,
                ))
        # All extra regions from calibration.json
        for name in sorted(self._layout.extra_regions.keys()):
            region = self._layout.extra_regions[name]
            qt_regions.append((
                QRect(gx + region.x, gy + region.y, region.w, region.h),
                name,
            ))

        self._region_overlay.set_regions(qt_regions)
        self._region_overlay.setGeometry(0, 0, screen_w, screen_h)
        self._region_overlay.show()

        # Auto-hide after 10 seconds
        QTimer.singleShot(10000, self._region_overlay.hide)

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
        self._current_game_state_text = self._info_label.text()
        self._start_ai_request(text)

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
        slots = state.shop or []
        shop_parts = []
        for i, name in enumerate(slots):
            shop_parts.append(f"{i+1}:{name}" if name else f"{i+1}:\u2014")
        shop_str = "  ".join(shop_parts) or "\u2014"
        items_count = len(state.items_on_bench)
        items_value = items_count * 2500 * max(0, 30 - self._round_to_int(state.round_number))
        board_str = self._format_champions(state.my_board)
        bench_str = self._format_champions(state.my_bench)
        hearts = "\u2665" * (state.lives or 0)
        lines = [
            f"Round: {state.round_number or '--'}  "
            f"Gold: {state.gold or '--'}  "
            f"Level: {state.level or '--'}  "
            f"Lives: {hearts}",
            f"Board ({len(state.my_board)}): {board_str}",
            f"Bench ({len(state.my_bench)}): {bench_str}",
            f"Shop: {shop_str}",
            f"Items on bench: {items_count}  (+{items_value:,} pts)",
            f"Projected score: {projected_score:,}",
        ]
        self._info_label.setText("\n".join(lines))

    def _round_to_int(self, round_str: str | None) -> int:
        if not round_str or "-" not in round_str:
            return 0
        try:
            stage, rnd = round_str.split("-")
            return (int(stage) - 1) * 10 + int(rnd)
        except ValueError:
            return 0
