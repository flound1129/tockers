from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFont


class OverlayWindow(QWidget):
    """Transparent always-on-top overlay for TFT advice."""

    update_signal = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("TFT Overlay")
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._visible = True
        self._init_ui()
        self.update_signal.connect(self._on_update)

    def _init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        font = QFont("Consolas", 14)
        font.setBold(True)

        self.score_label = self._make_label(font, "Score: --")
        self.components_label = self._make_label(font, "Components: --")
        self.round_label = self._make_label(font, "Round: --")
        self.gold_label = self._make_label(font, "Gold: --")
        self.advice_label = self._make_label(font, "")

        for lbl in [self.score_label, self.components_label,
                     self.round_label, self.gold_label, self.advice_label]:
            layout.addWidget(lbl)

        self.setLayout(layout)
        self.move(3840 - 500, 50)
        self.resize(450, 300)

    def _make_label(self, font, text):
        lbl = QLabel(text)
        lbl.setFont(font)
        lbl.setStyleSheet(
            "color: white; background-color: rgba(0, 0, 0, 160); "
            "padding: 4px 8px; border-radius: 4px;"
        )
        return lbl

    @pyqtSlot(dict)
    def _on_update(self, data: dict):
        if "score" in data:
            self.score_label.setText(f"Score: {data['score']:,}")
        if "components" in data:
            self.components_label.setText(
                f"Components: {data['components']} "
                f"({data.get('component_value', 0):,} pts remaining)"
            )
        if "round" in data:
            self.round_label.setText(
                f"Round: {data['round']}/30 - {data.get('enemy_name', '')}"
            )
        if "gold" in data:
            interest = min(data["gold"] // 10, 5)
            self.gold_label.setText(
                f"Gold: {data['gold']} (interest: {interest}g)"
            )
        if "advice" in data:
            self.advice_label.setText(data["advice"])
            self.advice_label.setVisible(bool(data["advice"]))

    def toggle_visibility(self):
        self._visible = not self._visible
        self.setVisible(self._visible)
