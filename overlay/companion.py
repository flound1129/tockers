from pathlib import Path

import cv2
import numpy as np
import pytesseract
from difflib import SequenceMatcher, get_close_matches

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QLineEdit, QPushButton, QLabel, QFrame,
)
from PyQt6.QtCore import QThread, Qt
from PyQt6.QtCore import pyqtSlot
from PyQt6.QtCore import pyqtSignal as Signal
from PyQt6.QtGui import QFont

from overlay.vision import _load_champion_names


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


class CompanionWindow(QWidget):
    def __init__(self, engine, layout=None, parent=None):
        super().__init__(parent)
        self.engine = engine
        self._layout = layout
        self._history: list[dict] = []
        self._current_game_state_text = ""
        self._worker: _AiWorker | None = None
        self._last_frame: np.ndarray | None = None
        self._champ_names: list[str] = _load_champion_names()
        self.setWindowTitle("Tocker's Companion")
        self.resize(400, 700)
        self._init_ui()

    def closeEvent(self, event):
        """Ensure the worker thread is stopped before the window is destroyed."""
        if self._worker is not None and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(2000)
        super().closeEvent(event)

    def __del__(self):
        if self._worker is not None and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(2000)

    def _init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.game_info_panel = self._build_game_info()
        self.chat_panel = self._build_chat()
        self.input_bar = self._build_input()

        layout.addWidget(self.game_info_panel, stretch=2)
        layout.addWidget(self.chat_panel, stretch=5)
        layout.addWidget(self.input_bar, stretch=1)
        self.setLayout(layout)

    def _build_game_info(self) -> QFrame:
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(6, 6, 6, 6)
        self._info_label = QLabel("Waiting for game state...")
        self._info_label.setWordWrap(True)
        self._info_label.setFont(QFont("Consolas", 10))
        layout.addWidget(self._info_label)
        return frame

    def _build_chat(self) -> QFrame:
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(6, 6, 6, 6)
        self._chat_display = QTextEdit()
        self._chat_display.setReadOnly(True)
        self._chat_display.setFont(QFont("Consolas", 10))
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
        self._debug_button = QPushButton("Debug Shop")
        self._debug_button.clicked.connect(self._on_debug_shop)
        layout.addWidget(self._input_field, stretch=4)
        layout.addWidget(self._send_button, stretch=1)
        layout.addWidget(self._debug_button, stretch=1)
        return frame

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

    def set_frame(self, frame: np.ndarray) -> None:
        """Store the latest captured frame for debug use."""
        self._last_frame = frame

    def _on_debug_shop(self):
        if self._last_frame is None or self._layout is None:
            self._append_message("Debug", "No frame captured yet.")
            return

        frame = self._last_frame
        out_dir = Path(__file__).parent.parent / "debug_crops"
        out_dir.mkdir(exist_ok=True)

        self._append_message("Debug", f"Frame: {frame.shape[1]}x{frame.shape[0]}")

        for i, region in enumerate(self._layout.shop_card_names):
            crop = frame[region.y:region.y + region.h,
                         region.x:region.x + region.w]
            cv2.imwrite(str(out_dir / f"shop_slot_{i}.png"), crop)

            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            if gray.mean() < 15:
                self._append_message("Debug",
                    f"Slot {i}: EMPTY (brightness {gray.mean():.0f})")
                continue

            # Adaptive pass (scale 4)
            scaled_a = cv2.resize(gray, None, fx=4, fy=4,
                                  interpolation=cv2.INTER_CUBIC)
            proc_a = cv2.adaptiveThreshold(
                scaled_a, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY, 31, -10)
            text_a = pytesseract.image_to_string(
                proc_a, config="--psm 11").strip()
            text_a = text_a.split("\n")[0].strip() if text_a else ""
            cv2.imwrite(str(out_dir / f"shop_slot_{i}_adaptive.png"), proc_a)

            # OTSU pass (scale 3)
            scaled_o = cv2.resize(gray, None, fx=3, fy=3,
                                  interpolation=cv2.INTER_CUBIC)
            _, proc_o = cv2.threshold(
                scaled_o, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            text_o = pytesseract.image_to_string(
                proc_o, config="--psm 11").strip()
            text_o = text_o.split("\n")[0].strip() if text_o else ""
            cv2.imwrite(str(out_dir / f"shop_slot_{i}_otsu.png"), proc_o)

            # Fuzzy match
            best_name, best_ratio = None, 0.0
            for raw in [text_a, text_o]:
                if not raw:
                    continue
                close = get_close_matches(
                    raw, self._champ_names, n=1, cutoff=0.3)
                if close:
                    ratio = SequenceMatcher(
                        None, raw.lower(), close[0].lower()).ratio()
                    if ratio > best_ratio:
                        best_ratio = ratio
                        best_name = close[0]

            self._append_message("Debug",
                f"Slot {i}: adap='{text_a}' otsu='{text_o}' "
                f"-> {best_name} ({best_ratio:.2f})")

        self._append_message("Debug", f"Crops saved to {out_dir}")

    def update_game_state(self, state, projected_score: int = 0):
        """Refresh the game info panel. Safe to call from any thread via signal."""
        shop_names = [s for s in (state.shop or []) if s]
        items_count = len(state.items_on_bench)
        items_value = items_count * 2500 * max(0, 30 - self._round_to_int(state.round_number))
        lines = [
            f"Round: {state.round_number or '--'}  "
            f"Gold: {state.gold or '--'}  "
            f"Level: {state.level or '--'}  "
            f"Lives: {'♥' * (state.lives or 0)}",
            f"Shop: {', '.join(shop_names) or '—'}",
            f"Items on bench: {items_count}  (+{items_value:,} pts)",
            f"Projected score: {projected_score:,}",
        ]
        self._info_label.setText("\n".join(lines))

    def _round_to_int(self, round_str: str | None) -> int:
        """Convert '2-5' to absolute round number (15)."""
        if not round_str or "-" not in round_str:
            return 0
        try:
            stage, rnd = round_str.split("-")
            return (int(stage) - 1) * 10 + int(rnd)
        except ValueError:
            return 0
