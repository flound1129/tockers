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


def _round_str_to_int(round_str: str | None) -> int:
    """Convert '2-5' to absolute round number 15. Returns 0 if unparseable."""
    if not round_str or "-" not in round_str:
        return 0
    try:
        stage, rnd = round_str.split("-")
        return (int(stage) - 1) * 10 + int(rnd)
    except ValueError:
        return 0


def vision_loop(capture, reader, engine, overlay, companion, stop_event):
    """Background thread: capture frames, read game state, update overlay."""
    from overlay.stats import StatsRecorder
    recorder = StatsRecorder(engine.conn)
    prev_round: str | None = None

    try:
        while not stop_event.is_set():
            frame = capture.grab()
            if frame is None:
                time.sleep(0.5)
                continue

            companion.set_frame(frame)
            state = reader.read(frame)
            num_components = len(state.items_on_bench)
            gold = state.gold or 0
            current_round = state.round_number  # e.g. "1-3" or None

            # Detect run completion when round 3-10 ends and OCR loses the round display
            if current_round is None and prev_round == "3-10" and recorder.active_run_id is not None:
                recorder.record_round(
                    round_number="3-10",
                    gold=state.gold,
                    level=state.level,
                    lives=state.lives,
                    component_count=num_components,
                    shop=state.shop or [],
                )
                recorder.end_run("completed")
                threading.Thread(target=engine.update_strategy, daemon=True).start()
                prev_round = None

            # --- Round transition detection ---
            if current_round is not None and current_round != prev_round:
                if current_round == "1-1":
                    # New run starting
                    if recorder.active_run_id is not None:
                        recorder.end_run("abandoned")
                    recorder.start_run()
                elif prev_round is not None:
                    # Record the round that just ended
                    recorder.record_round(
                        round_number=prev_round,
                        gold=state.gold,
                        level=state.level,
                        lives=state.lives,
                        component_count=num_components,
                        shop=state.shop or [],
                    )

                    # Check if round 30 just completed
                    if prev_round == "3-10":
                        recorder.end_run("completed")
                        threading.Thread(
                            target=engine.update_strategy, daemon=True
                        ).start()

                prev_round = current_round

            # Note: Elimination detection (lives reaching 0) is not currently
            # implemented because _read_lives() returns None on failure and
            # only validates values 1-3. Eliminated runs will be closed as
            # "abandoned" via the finally block when the overlay is restarted.

            # --- Overlay update ---
            abs_round = _round_str_to_int(current_round)
            rounds_remaining = max(0, 30 - abs_round)

            projection = engine.projected_score(
                current_round=abs_round,
                num_components=num_components,
                gold=gold,
                surviving_units=len(state.my_board),
            )

            enemy_name = ""
            next_round_num = abs_round + 1
            if next_round_num <= 30:
                info = engine.get_round_info(next_round_num)
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
                "round": abs_round,
                "enemy_name": enemy_name,
                "gold": gold,
                "advice": "",
            })

            time.sleep(1.0 / CAPTURE_FPS)

    finally:
        if recorder.active_run_id is not None:
            recorder.end_run("abandoned")


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
    companion = CompanionWindow(engine=engine, layout=layout)
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
