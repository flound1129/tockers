import numpy as np
from overlay.vision import GameStateReader, GameState, TemplateMatcher
from overlay.config import TFTLayout


def test_read_returns_game_state():
    layout = TFTLayout()
    empty = TemplateMatcher.__new__(TemplateMatcher)
    empty.templates = {}

    reader = GameStateReader(layout, empty, empty, empty, empty)
    frame = np.zeros((2160, 3840, 3), dtype=np.uint8)
    state = reader.read(frame)

    assert isinstance(state, GameState)
    assert state.phase == "planning"
    assert state.my_board == []
    assert state.items_on_bench == []
