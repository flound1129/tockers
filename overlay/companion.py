import re
from pathlib import Path

import cv2
import numpy as np
import pytesseract
from difflib import SequenceMatcher, get_close_matches

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QLineEdit, QPushButton, QLabel, QFrame,
)
from PyQt6.QtCore import QThread, Qt, QRect
from PyQt6.QtCore import pyqtSlot
from PyQt6.QtCore import pyqtSignal as Signal
from PyQt6.QtGui import QFont, QPainter, QPen, QColor

from overlay.vision import _load_champion_names


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
        self._region_overlay = RegionOverlay()
        self.setWindowTitle("Tocker's Companion")
        self.resize(400, 700)
        self.move(50, 50)
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
        self._debug_bench_button = QPushButton("Debug Bench")
        self._debug_bench_button.clicked.connect(self._on_debug_bench)
        self._debug_board_button = QPushButton("Debug Board")
        self._debug_board_button.clicked.connect(self._on_debug_board)
        self._debug_all_button = QPushButton("Debug All")
        self._debug_all_button.clicked.connect(self._on_debug_all)
        layout.addWidget(self._input_field, stretch=4)
        layout.addWidget(self._send_button, stretch=1)
        layout.addWidget(self._debug_button, stretch=1)
        layout.addWidget(self._debug_bench_button, stretch=1)
        layout.addWidget(self._debug_board_button, stretch=1)
        layout.addWidget(self._debug_all_button, stretch=1)
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

        report_lines = [f"Frame: {frame.shape[1]}x{frame.shape[0]}"]
        self._append_message("Debug", report_lines[0])

        for i, region in enumerate(self._layout.shop_card_names):
            crop = frame[region.y:region.y + region.h,
                         region.x:region.x + region.w]
            cv2.imwrite(str(out_dir / f"shop_slot_{i}.png"), crop)

            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            brightness = gray.mean()
            if brightness < 25:
                line = f"Slot {i}: EMPTY (brightness {brightness:.0f})"
                self._append_message("Debug", line)
                report_lines.append(line)
                continue

            # Adaptive pass (scale 4)
            scaled_a = cv2.resize(gray, None, fx=4, fy=4,
                                  interpolation=cv2.INTER_CUBIC)
            proc_a = cv2.adaptiveThreshold(
                scaled_a, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY, 31, -10)
            raw_a = pytesseract.image_to_string(
                proc_a, config="--psm 11").strip()
            first_a = raw_a.split("\n")[0].strip() if raw_a else ""
            clean_a = re.sub(r"[^a-zA-Z\s']", "", first_a).strip()
            cv2.imwrite(str(out_dir / f"shop_slot_{i}_adaptive.png"), proc_a)

            # OTSU pass (scale 3)
            scaled_o = cv2.resize(gray, None, fx=3, fy=3,
                                  interpolation=cv2.INTER_CUBIC)
            _, proc_o = cv2.threshold(
                scaled_o, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            raw_o = pytesseract.image_to_string(
                proc_o, config="--psm 11").strip()
            first_o = raw_o.split("\n")[0].strip() if raw_o else ""
            clean_o = re.sub(r"[^a-zA-Z\s']", "", first_o).strip()
            cv2.imwrite(str(out_dir / f"shop_slot_{i}_otsu.png"), proc_o)

            # Fuzzy match
            best_name, best_ratio = None, 0.0
            for raw in [clean_a, clean_o]:
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

            line = (f"Slot {i}: brightness={brightness:.0f} "
                    f"adap_raw='{first_a}' adap_clean='{clean_a}' "
                    f"otsu_raw='{first_o}' otsu_clean='{clean_o}' "
                    f"-> {best_name} ({best_ratio:.2f})")
            self._append_message("Debug", line)
            report_lines.append(line)

        # Write report for remote debugging
        report_path = out_dir / "report.txt"
        report_path.write_text("\n".join(report_lines), encoding="utf-8")
        self._append_message("Debug", f"Crops + report saved to {out_dir}")

    def _on_debug_all(self):
        """Show all detection regions on the game overlay."""
        if self._last_frame is None or self._layout is None:
            self._append_message("Debug", "No frame captured yet.")
            return

        from overlay.config import ScreenRegion
        regions = []

        # Board hex grid
        cols = self._layout.board_hex_cols
        for idx, region in enumerate(self._layout.board_hex_regions):
            row = idx // cols
            col = idx % cols
            regions.append((region, f"b{row},{col}"))

        # Champion bench
        regions.append((self._layout.champion_bench, "bench"))

        # Item bench
        regions.append((self._layout.item_bench, "items"))

        # Shop card names
        for i, region in enumerate(self._layout.shop_card_names):
            regions.append((region, f"shop{i}"))

        # OCR regions
        regions.append((self._layout.round_text, "round"))
        regions.append((self._layout.gold_text, "gold"))
        regions.append((self._layout.lives_text, "lives"))
        regions.append((self._layout.level_text, "level"))

        self._show_debug_regions(regions)
        self._append_message("Debug", f"Showing {len(regions)} regions on overlay")

    def _show_debug_regions(self, regions: list[tuple]):
        """Show red rectangles on the game overlay.

        regions: list of (ScreenRegion, label) tuples in game coordinates.
        """
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        screen_w = screen.geometry().width()
        screen_h = screen.geometry().height()
        game_w, game_h = self._layout.resolution
        # Game is centered on screen (for ultrawide)
        gx = (screen_w - game_w) // 2
        gy = (screen_h - game_h) // 2
        gy = max(0, gy)
        gx = max(0, gx)

        qt_regions = []
        for sr, label in regions:
            qt_regions.append((
                QRect(gx + sr.x, gy + sr.y, sr.w, sr.h),
                label,
            ))

        self._region_overlay.set_regions(qt_regions)
        self._region_overlay.setGeometry(0, 0, screen_w, screen_h)
        self._region_overlay.show()

    def _on_debug_bench(self):
        if self._last_frame is None or self._layout is None:
            self._append_message("Debug", "No frame captured yet.")
            return

        frame = self._last_frame
        out_dir = Path(__file__).parent.parent / "debug_crops"
        out_dir.mkdir(exist_ok=True)

        region = self._layout.champion_bench
        bench_crop = frame[region.y:region.y + region.h,
                           region.x:region.x + region.w]
        cv2.imwrite(str(out_dir / "bench_full.png"), bench_crop)

        report_lines = [
            f"Frame: {frame.shape[1]}x{frame.shape[0]}",
            f"Bench region: x={region.x} y={region.y} w={region.w} h={region.h}",
        ]

        # Divide bench into slots (9 bench slots, evenly spaced)
        num_slots = 9
        slot_w = region.w // num_slots
        annotated = bench_crop.copy()

        for i in range(num_slots):
            sx = i * slot_w
            slot_crop = bench_crop[:, sx:sx + slot_w]
            cv2.imwrite(str(out_dir / f"bench_slot_{i}.png"), slot_crop)

            brightness = np.mean(cv2.cvtColor(slot_crop, cv2.COLOR_BGR2GRAY))
            line = f"Slot {i}: x={region.x + sx} brightness={brightness:.0f}"
            report_lines.append(line)

            # Draw grid lines on annotated image
            cv2.rectangle(annotated, (sx, 0), (sx + slot_w, region.h),
                          (0, 255, 0), 1)
            cv2.putText(annotated, f"{i}", (sx + 5, 15),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)

        cv2.imwrite(str(out_dir / "bench_annotated.png"), annotated)

        # Draw bench region on full frame in red
        frame_annotated = frame.copy()
        RED = (0, 0, 255)
        cv2.rectangle(frame_annotated,
                       (region.x, region.y),
                       (region.x + region.w, region.y + region.h),
                       RED, 2)
        cv2.putText(frame_annotated, "champion_bench",
                    (region.x + 5, region.y - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, RED, 2)
        # Also draw slot dividers
        for i in range(num_slots):
            sx = region.x + i * slot_w
            cv2.line(frame_annotated, (sx, region.y), (sx, region.y + region.h),
                     RED, 1)
        cv2.imwrite(str(out_dir / "bench_regions.png"), frame_annotated)

        report_path = out_dir / "bench_report.txt"
        report_path.write_text("\n".join(report_lines), encoding="utf-8")

        # Show red rectangles on game overlay
        from overlay.config import ScreenRegion
        overlay_regions = [(region, "bench")]
        for i in range(num_slots):
            sx = region.x + i * slot_w
            overlay_regions.append((
                ScreenRegion(sx, region.y, slot_w, region.h), f"{i}"
            ))
        self._show_debug_regions(overlay_regions)
        self._append_message("Debug", f"Bench crops saved ({num_slots} slots)")

    def _on_debug_board(self):
        if self._last_frame is None or self._layout is None:
            self._append_message("Debug", "No frame captured yet.")
            return

        frame = self._last_frame
        out_dir = Path(__file__).parent.parent / "debug_crops"
        out_dir.mkdir(exist_ok=True)

        hex_regions = self._layout.board_hex_regions
        ox, oy = self._layout.board_hex_origin
        # Compute bounding box for full board crop
        max_x = max(r.x + r.w for r in hex_regions)
        max_y = max(r.y + r.h for r in hex_regions)
        board_crop = frame[oy:max_y, ox:max_x]
        cv2.imwrite(str(out_dir / "board_full.png"), board_crop)

        report_lines = [
            f"Frame: {frame.shape[1]}x{frame.shape[0]}",
            f"Board origin: ({ox}, {oy})",
            f"Hex cells: {len(hex_regions)} "
            f"({self._layout.board_hex_rows}x{self._layout.board_hex_cols})",
        ]

        annotated = board_crop.copy()
        cols = self._layout.board_hex_cols

        for idx, region in enumerate(hex_regions):
            row = idx // cols
            col = idx % cols
            cell_crop = frame[region.y:region.y + region.h,
                              region.x:region.x + region.w]
            cv2.imwrite(str(out_dir / f"board_r{row}_c{col}.png"), cell_crop)

            brightness = np.mean(cv2.cvtColor(cell_crop, cv2.COLOR_BGR2GRAY))
            line = (f"Cell r{row}c{col}: x={region.x} y={region.y} "
                    f"brightness={brightness:.0f}")
            report_lines.append(line)

            # Draw rectangle on annotated image (offset from board origin)
            rx = region.x - ox
            ry = region.y - oy
            cv2.rectangle(annotated, (rx, ry), (rx + region.w, ry + region.h),
                          (0, 255, 0), 1)
            cv2.putText(annotated, f"{row},{col}", (rx + 3, ry + 12),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 255, 0), 1)

        cv2.imwrite(str(out_dir / "board_annotated.png"), annotated)

        # Draw hex grid on full frame in red
        frame_annotated = frame.copy()
        RED = (0, 0, 255)
        for idx, region in enumerate(hex_regions):
            row = idx // cols
            col = idx % cols
            cv2.rectangle(frame_annotated,
                           (region.x, region.y),
                           (region.x + region.w, region.y + region.h),
                           RED, 2)
            cv2.putText(frame_annotated, f"{row},{col}",
                        (region.x + 3, region.y + 14),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, RED, 1)
        # Also draw bench region for context
        bench = self._layout.champion_bench
        cv2.rectangle(frame_annotated,
                       (bench.x, bench.y),
                       (bench.x + bench.w, bench.y + bench.h),
                       RED, 2)
        cv2.putText(frame_annotated, "bench",
                    (bench.x + 5, bench.y - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, RED, 2)
        cv2.imwrite(str(out_dir / "board_regions.png"), frame_annotated)

        report_path = out_dir / "board_report.txt"
        report_path.write_text("\n".join(report_lines), encoding="utf-8")

        # Show red rectangles on game overlay
        overlay_regions = []
        for idx, region in enumerate(hex_regions):
            row = idx // cols
            col = idx % cols
            overlay_regions.append((region, f"{row},{col}"))
        bench = self._layout.champion_bench
        overlay_regions.append((bench, "bench"))
        self._show_debug_regions(overlay_regions)

        self._append_message(
            "Debug",
            f"Board crops saved ({len(hex_regions)} cells, "
            f"{self._layout.board_hex_rows}x{self._layout.board_hex_cols})"
        )

    @staticmethod
    def _format_champions(champions: list) -> str:
        """Format champion list with star indicators: 'Viego★★, Jhin★'."""
        if not champions:
            return "—"
        star_char = "★"
        parts = []
        for m in champions:
            stars = star_char * m.stars if m.stars > 0 else ""
            parts.append(f"{m.name}{stars}")
        return ", ".join(parts)

    def update_game_state(self, state, projected_score: int = 0):
        """Refresh the game info panel. Safe to call from any thread via signal."""
        shop_names = [s for s in (state.shop or []) if s]
        items_count = len(state.items_on_bench)
        items_value = items_count * 2500 * max(0, 30 - self._round_to_int(state.round_number))
        board_str = self._format_champions(state.my_board)
        bench_str = self._format_champions(state.my_bench)
        lines = [
            f"Round: {state.round_number or '--'}  "
            f"Gold: {state.gold or '--'}  "
            f"Level: {state.level or '--'}  "
            f"Lives: {'♥' * (state.lives or 0)}",
            f"Board ({len(state.my_board)}): {board_str}",
            f"Bench ({len(state.my_bench)}): {bench_str}",
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
