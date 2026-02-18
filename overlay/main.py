import sys
import time
import threading
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from overlay.config import TFTLayout, CAPTURE_FPS, REFERENCES_DIR, DB_PATH
from overlay.capture import ScreenCapture, MockCapture
from overlay.vision import TemplateMatcher, GameStateReader
from overlay.strategy import StrategyEngine


def create_matchers():
    item_dir = REFERENCES_DIR / "items"
    augment_dir = REFERENCES_DIR / "augments"

    def load_or_empty(d):
        if d.exists() and any(d.glob("*.png")):
            return TemplateMatcher(d)
        m = TemplateMatcher.__new__(TemplateMatcher)
        m.templates = {}
        return m

    return load_or_empty(item_dir), load_or_empty(augment_dir)


def vision_loop(capture, reader, engine, overlay, companion, stop_event):
    """Background thread: capture frames, read game state, update overlay."""
    current_round = 0
    while not stop_event.is_set():
        frame = capture.grab()
        if frame is None:
            time.sleep(0.5)
            continue

        state = reader.read(frame)
        num_components = len(state.items_on_bench)
        gold = state.gold or 0
        rounds_remaining = 30 - current_round

        projection = engine.projected_score(
            current_round=current_round,
            num_components=num_components,
            gold=gold,
            surviving_units=len(state.my_board),
        )

        enemy_name = ""
        next_round = current_round + 1
        if next_round <= 30:
            info = engine.get_round_info(next_round)
            if info:
                enemy_name = (
                    f"Stage {info['stage']}-{info['round_in_stage']} "
                    f"({info['round_type']})"
                )

        companion.update_game_state(state, projected_score=projection["total"])

        overlay.update_signal.emit({
            "score": projection["total"],
            "components": num_components,
            "component_value": engine.component_score(
                num_components, rounds_remaining
            ),
            "round": current_round,
            "enemy_name": enemy_name,
            "gold": gold,
            "advice": "",
        })

        time.sleep(1.0 / CAPTURE_FPS)


def main():
    from PyQt6.QtWidgets import QApplication

    use_mock = "--mock" in sys.argv
    mock_image = None
    for arg in sys.argv:
        if arg.startswith("--image="):
            mock_image = arg.split("=", 1)[1]
            use_mock = True

    app = QApplication(sys.argv)
    layout = TFTLayout()
    item_m, aug_m = create_matchers()
    reader = GameStateReader(layout, item_matcher=item_m, augment_matcher=aug_m)
    engine = StrategyEngine(DB_PATH)

    capture = MockCapture(mock_image) if use_mock else ScreenCapture(CAPTURE_FPS)
    capture.start()

    from overlay.ui import OverlayWindow
    from overlay.companion import CompanionWindow
    overlay = OverlayWindow()
    overlay.show()
    companion = CompanionWindow(engine=engine)
    companion.show()

    stop_event = threading.Event()
    vision_thread = threading.Thread(
        target=vision_loop,
        args=(capture, reader, engine, overlay, companion, stop_event),
        daemon=True,
    )
    vision_thread.start()

    try:
        sys.exit(app.exec())
    finally:
        stop_event.set()
        capture.stop()


if __name__ == "__main__":
    main()
