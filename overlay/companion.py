from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QLineEdit, QPushButton, QLabel, QFrame,
)
from PyQt6.QtCore import QThread
from PyQt6.QtCore import pyqtSlot
from PyQt6.QtCore import pyqtSignal as Signal
from PyQt6.QtGui import QFont


class CompanionWindow(QWidget):
    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self._history: list[dict] = []
        self._current_game_state_text = ""
        self.setWindowTitle("Tocker's Companion")
        self.resize(400, 700)
        self._init_ui()

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
        layout.addWidget(self._input_field, stretch=4)
        layout.addWidget(self._send_button, stretch=1)
        return frame

    def _on_send(self):
        text = self._input_field.text().strip()
        if not text:
            return
        self._input_field.clear()
        self._append_message("You", text)
        self._append_message("AI", "thinking...")
        self._current_game_state_text = self._info_label.text()
        self._start_ai_request(text)

    def _append_message(self, sender: str, text: str):
        self._chat_display.append(f"[{sender}]  {text}\n")
        sb = self._chat_display.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _start_ai_request(self, question: str):
        # Implemented in Task 5
        pass

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
