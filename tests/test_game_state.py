import numpy as np
from overlay.vision import GameStateReader, GameState, TemplateMatcher
from overlay.config import TFTLayout


def test_read_returns_game_state():
    layout = TFTLayout()
    empty = TemplateMatcher.__new__(TemplateMatcher)
    empty.templates = {}

    reader = GameStateReader(layout, item_matcher=empty)
    frame = np.zeros((1440, 2560, 3), dtype=np.uint8)
    state = reader.read(frame)

    assert isinstance(state, GameState)
    assert state.phase == "planning"
    assert state.items_on_bench == []
    assert state.shop == []  # no round detected, shop not scanned yet
