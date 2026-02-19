import pytest
import numpy as np
from unittest.mock import MagicMock
from PyQt6.QtWidgets import QApplication
from overlay.companion import CompanionWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _make_engine(**scores):
    engine = MagicMock()
    engine.get_augment_scores.return_value = scores
    return engine


def test_companion_window_has_panels(app):
    window = CompanionWindow(engine=_make_engine())
    assert window.game_info_panel is not None
    assert window.chat_panel is not None
    assert window.input_bar is not None


def test_companion_window_title(app):
    window = CompanionWindow(engine=_make_engine())
    assert "Tocker" in window.windowTitle()


def test_companion_internals(app):
    from PyQt6.QtWidgets import QTextEdit, QLineEdit, QPushButton
    window = CompanionWindow(engine=_make_engine())
    assert isinstance(window._chat_display, QTextEdit)
    assert window._chat_display.isReadOnly()
    assert isinstance(window._input_field, QLineEdit)
    assert isinstance(window._send_button, QPushButton)
    assert window._history == []
    assert window._current_game_state_text == ""


def test_game_info_updates(app):
    from overlay.vision import GameState
    window = CompanionWindow(engine=_make_engine())
    state = GameState(
        phase="planning",
        round_number="2-5",
        gold=8,
        level=5,
        lives=3,
        shop=["Kog'Maw", "", "Illaoi", "", ""],
        items_on_bench=[],
    )
    window.update_game_state(state, projected_score=142300)
    # Score displayed in dedicated widget
    assert "142,300" in window._score_value.text()
    # Round displayed as absolute
    assert "15" in window._round_value.text()
    # Gold displayed
    assert "8" in window._gold_value.text()


def test_chat_appends_user_message(app):
    window = CompanionWindow(engine=_make_engine())
    window._input_field.setText("Should I level?")
    window._on_send()
    assert "Should I level?" in window._chat_display.toPlainText()


def test_chat_clears_input_on_send(app):
    window = CompanionWindow(engine=_make_engine())
    window._input_field.setText("Should I level?")
    window._on_send()
    assert window._input_field.text() == ""


def test_chat_shows_thinking_indicator(app):
    window = CompanionWindow(engine=_make_engine())
    window._input_field.setText("Any advice?")
    window._on_send()
    assert "thinking" in window._chat_display.toPlainText().lower()


def test_chat_replaces_thinking_with_response(app):
    engine = _make_engine()
    engine.ask_claude.return_value = "Hold your components."
    window = CompanionWindow(engine=engine)
    window._input_field.setText("Should I build?")
    window._on_send()
    # Simulate worker finishing synchronously
    window._on_ai_response("Hold your components.", "Should I build?")
    text = window._chat_display.toPlainText()
    assert "Hold your components." in text
    assert "thinking" not in text.lower()


def test_augment_recommendations_update(app):
    """When augment choices arrive on augment round, recommendations should appear."""
    from overlay.vision import GameState
    scores = {"Augment A": 85, "Augment B": 72, "Augment C": 41}
    window = CompanionWindow(engine=_make_engine(**scores))
    state = GameState(
        round_number="1-5",
        augment_choices=["Augment A", "Augment B", "Augment C"],
        items_on_bench=[],
    )
    window.update_game_state(state)
    assert window._current_choices == ["Augment A", "Augment B", "Augment C"]
    rec_text = window._augment_rec_label.text()
    # Best score (85) should appear first
    assert "Augment A" in rec_text
    assert "85" in rec_text


def test_augment_recommendations_sorted_by_score(app):
    """Augments should be sorted by score descending."""
    from overlay.vision import GameState
    scores = {"Low": 10, "High": 90, "Mid": 50}
    window = CompanionWindow(engine=_make_engine(**scores))
    state = GameState(
        round_number="2-5",
        augment_choices=["Low", "Mid", "High"],
        items_on_bench=[],
    )
    window.update_game_state(state)
    rec_text = window._augment_rec_label.text()
    # High should appear before Mid and Low
    high_pos = rec_text.index("High")
    mid_pos = rec_text.index("Mid")
    low_pos = rec_text.index("Low")
    assert high_pos < mid_pos < low_pos


def test_right_click_scan_records_augment(app):
    """Right-click scan should record detected augment."""
    from overlay.vision import GameState
    window = CompanionWindow(engine=_make_engine())

    # Set up a mock reader
    mock_reader = MagicMock()
    mock_reader.read_selected_augment.return_value = "Bandle Bounty I"
    window._reader = mock_reader
    window._last_frame = np.zeros((100, 100, 3), dtype=np.uint8)

    # Simulate right-click via contextMenuEvent
    from PyQt6.QtGui import QContextMenuEvent
    from PyQt6.QtCore import QPoint
    event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(10, 10))
    window.contextMenuEvent(event)

    assert "Bandle Bounty I" in window._picked_augments


def test_right_click_scan_gold_destiny(app):
    """Scanned augment can differ from offered choices (Gold Destiny case)."""
    from overlay.vision import GameState
    scores = {"A": 50, "B": 60, "C": 70}
    window = CompanionWindow(engine=_make_engine(**scores))

    state = GameState(
        round_number="1-5",
        augment_choices=["A", "B", "C"],
        items_on_bench=[],
    )
    window.update_game_state(state)

    # Scan returns a name NOT in offered choices
    mock_reader = MagicMock()
    mock_reader.read_selected_augment.return_value = "Random Augment Z"
    window._reader = mock_reader
    window._last_frame = np.zeros((100, 100, 3), dtype=np.uint8)

    from PyQt6.QtGui import QContextMenuEvent
    from PyQt6.QtCore import QPoint
    event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(10, 10))
    window.contextMenuEvent(event)

    # Should still record it
    assert "Random Augment Z" in window._picked_augments


def test_new_game_resets_augment_state(app):
    """Round 1-1 should reset all augment state."""
    from overlay.vision import GameState
    window = CompanionWindow(engine=_make_engine())

    state = GameState(
        round_number="1-5",
        augment_choices=["X", "Y", "Z"],
        items_on_bench=[],
    )
    window.update_game_state(state)
    assert window._current_choices == ["X", "Y", "Z"]

    # Simulate picking via right-click
    mock_reader = MagicMock()
    mock_reader.read_selected_augment.return_value = "X"
    window._reader = mock_reader
    window._last_frame = np.zeros((100, 100, 3), dtype=np.uint8)
    from PyQt6.QtGui import QContextMenuEvent
    from PyQt6.QtCore import QPoint
    event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(10, 10))
    window.contextMenuEvent(event)
    assert len(window._picked_augments) == 1

    # New game
    state2 = GameState(round_number="1-1", items_on_bench=[])
    window.update_game_state(state2)
    assert window._picked_augments == []
    assert window._all_seen_augments == set()
    assert window._current_augment_round is None
    assert window._current_choices == []


def test_non_augment_round_ignored(app):
    """Augment choices on non-augment rounds should be ignored."""
    from overlay.vision import GameState
    window = CompanionWindow(engine=_make_engine())

    state = GameState(
        round_number="1-5",
        augment_choices=["A", "B", "C"],
        items_on_bench=[],
    )
    window.update_game_state(state)
    assert window._current_choices == ["A", "B", "C"]

    # Non-augment round with garbage should not update choices
    state2 = GameState(
        round_number="1-6",
        augment_choices=["Garbage"],
        items_on_bench=[],
    )
    window.update_game_state(state2)
    assert window._current_choices == ["A", "B", "C"]


def test_augment_round_reset(app):
    """Each augment round (1-5, 2-5, 3-5) should reset seen augments."""
    from overlay.vision import GameState
    window = CompanionWindow(engine=_make_engine())

    state = GameState(
        round_number="1-5",
        augment_choices=["A", "B", "C"],
        items_on_bench=[],
    )
    window.update_game_state(state)
    assert len(window._all_seen_augments) == 3

    # New augment round should reset seen
    state2 = GameState(
        round_number="2-5",
        augment_choices=["D", "E", "F"],
        items_on_bench=[],
    )
    window.update_game_state(state2)
    assert window._all_seen_augments == {"D", "E", "F"}
    assert window._current_choices == ["D", "E", "F"]


def test_collapsible_sections_exist(app):
    """Verify collapsible sections are present."""
    window = CompanionWindow(engine=_make_engine())
    assert window._board_section is not None
    assert window._shop_section is not None
    assert window._cal_section is not None
    assert window._chat_section is not None


def test_score_breakdown_bar(app):
    """Verify ScoreBreakdownBar accepts segments."""
    from overlay.companion import ScoreBreakdownBar
    bar = ScoreBreakdownBar()
    bar.set_segments([(100, "#FF0000"), (200, "#00FF00"), (50, "#0000FF")])
    assert len(bar._segments) == 3
