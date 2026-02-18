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
        self._send_button.setEnabled(False)
        self._send_button.clicked.connect(self._on_send)
        self._input_field.returnPressed.connect(self._on_send)
        layout.addWidget(self._input_field, stretch=4)
        layout.addWidget(self._send_button, stretch=1)
        return frame

    def _on_send(self):
        pass
