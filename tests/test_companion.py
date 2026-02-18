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
    text = window._info_label.text()
    assert "2-5" in text
    assert "8" in text
    assert "142" in text
