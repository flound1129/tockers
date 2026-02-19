import pytest
from unittest.mock import MagicMock
from PyQt6.QtWidgets import QApplication
from overlay.companion import CompanionWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_companion_window_has_panels(app):
    window = CompanionWindow(engine=MagicMock())
    assert window.game_info_panel is not None
    assert window.chat_panel is not None
    assert window.input_bar is not None


def test_companion_window_title(app):
    window = CompanionWindow(engine=MagicMock())
    assert "Tocker" in window.windowTitle()


def test_companion_internals(app):
    from PyQt6.QtWidgets import QTextEdit, QLineEdit, QPushButton
    window = CompanionWindow(engine=MagicMock())
    assert isinstance(window._chat_display, QTextEdit)
    assert window._chat_display.isReadOnly()
    assert isinstance(window._input_field, QLineEdit)
    assert isinstance(window._send_button, QPushButton)
    assert window._history == []
    assert window._current_game_state_text == ""


def test_game_info_updates(app):
    from overlay.vision import GameState
    window = CompanionWindow(engine=MagicMock())
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
    window = CompanionWindow(engine=MagicMock())
    window._input_field.setText("Should I level?")
    window._on_send()
    assert "Should I level?" in window._chat_display.toPlainText()


def test_chat_clears_input_on_send(app):
    window = CompanionWindow(engine=MagicMock())
    window._input_field.setText("Should I level?")
    window._on_send()
    assert window._input_field.text() == ""


def test_chat_shows_thinking_indicator(app):
    window = CompanionWindow(engine=MagicMock())
    window._input_field.setText("Any advice?")
    window._on_send()
    assert "thinking" in window._chat_display.toPlainText().lower()


def test_chat_replaces_thinking_with_response(app):
    mock_engine = MagicMock()
    mock_engine.ask_claude.return_value = "Hold your components."
    window = CompanionWindow(engine=mock_engine)
    window._input_field.setText("Should I build?")
    window._on_send()
    # Simulate worker finishing synchronously
    window._on_ai_response("Hold your components.", "Should I build?")
    text = window._chat_display.toPlainText()
    assert "Hold your components." in text
    assert "thinking" not in text.lower()


def test_augment_locking_after_pick(app):
    """After picking an augment, the dropdown should be locked."""
    window = CompanionWindow(engine=MagicMock())
    from overlay.vision import GameState
    state = GameState(
        round_number="1-5",
        augment_choices=["Augment A", "Augment B", "Augment C"],
        items_on_bench=[],
    )
    window.update_game_state(state)
    assert window._augment_combo.count() == 3
    assert not window._augments_locked

    # Pick an augment
    window._augment_combo.setCurrentIndex(0)
    window._on_augment_pick()
    assert window._augments_locked
    assert window._picked_augments == ["Augment A"]

    # Further updates should not change the combo
    state2 = GameState(
        round_number="1-5",
        augment_choices=["Garbage X", "Garbage Y"],
        items_on_bench=[],
    )
    window.update_game_state(state2)
    # Combo should still have original choices since it's locked
    assert window._augment_combo.count() == 3


def test_augment_locking_after_6_seen(app):
    """After seeing 6 unique augments, lock automatically (reroll scenario)."""
    window = CompanionWindow(engine=MagicMock())
    from overlay.vision import GameState

    state1 = GameState(
        round_number="2-5",
        augment_choices=["Aug1", "Aug2", "Aug3"],
        items_on_bench=[],
    )
    window.update_game_state(state1)
    assert not window._augments_locked

    # Simulate reroll: 3 new augments
    state2 = GameState(
        round_number="2-5",
        augment_choices=["Aug4", "Aug5", "Aug6"],
        items_on_bench=[],
    )
    window.update_game_state(state2)
    assert window._augments_locked


def test_augment_round_reset(app):
    """Each augment round (1-5, 2-5, 3-5) should reset the lock."""
    window = CompanionWindow(engine=MagicMock())
    from overlay.vision import GameState

    # First augment round
    state = GameState(
        round_number="1-5",
        augment_choices=["A", "B", "C"],
        items_on_bench=[],
    )
    window.update_game_state(state)
    window._augment_combo.setCurrentIndex(0)
    window._on_augment_pick()
    assert window._augments_locked

    # New augment round should reset
    state2 = GameState(
        round_number="2-5",
        augment_choices=["D", "E", "F"],
        items_on_bench=[],
    )
    window.update_game_state(state2)
    assert not window._augments_locked
    assert window._augment_combo.count() == 3


def test_new_game_resets_augment_state(app):
    """Round 1-1 should reset all augment state."""
    window = CompanionWindow(engine=MagicMock())
    from overlay.vision import GameState

    state = GameState(
        round_number="1-5",
        augment_choices=["X", "Y", "Z"],
        items_on_bench=[],
    )
    window.update_game_state(state)
    window._on_augment_pick()
    assert window._augments_locked
    assert len(window._picked_augments) == 1

    # New game
    state2 = GameState(round_number="1-1", items_on_bench=[])
    window.update_game_state(state2)
    assert not window._augments_locked
    assert window._picked_augments == []
    assert window._all_seen_augments == set()
    assert window._current_augment_round is None


def test_non_augment_round_ignored(app):
    """Augment choices on non-augment rounds should be ignored."""
    window = CompanionWindow(engine=MagicMock())
    from overlay.vision import GameState

    # Set up augments on 1-5 and pick
    state = GameState(
        round_number="1-5",
        augment_choices=["A", "B", "C"],
        items_on_bench=[],
    )
    window.update_game_state(state)
    window._augment_combo.setCurrentIndex(0)
    window._on_augment_pick()
    assert window._augments_locked
    assert window._augment_combo.count() == 3

    # Non-augment round with garbage should not reset or update combo
    state2 = GameState(
        round_number="1-6",
        augment_choices=["Garbage"],
        items_on_bench=[],
    )
    window.update_game_state(state2)
    assert window._augments_locked
    assert window._augment_combo.count() == 3


def test_collapsible_sections_exist(app):
    """Verify collapsible sections are present."""
    window = CompanionWindow(engine=MagicMock())
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
