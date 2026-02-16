import pytest
from overlay.strategy import StrategyEngine


@pytest.fixture
def engine():
    return StrategyEngine("tft.db")


def test_score_from_components(engine):
    score = engine.component_score(num_components=5, rounds_remaining=20)
    assert score == 250_000


def test_interest_calculation(engine):
    assert engine.interest(gold=0) == 0
    assert engine.interest(gold=10) == 1
    assert engine.interest(gold=35) == 3
    assert engine.interest(gold=50) == 5
    assert engine.interest(gold=99) == 5


def test_lookup_enemy_board(engine):
    board = engine.get_enemy_board(round_number=3)
    assert board is not None
    assert len(board) > 0  # Round 3 is Qiyana with 3 units


def test_lookup_tocker_augments(engine):
    augments = engine.get_tocker_augments()
    assert len(augments) == 30


def test_round_info(engine):
    info = engine.get_round_info(5)
    assert info["round_type"] == "augment"
    assert info["augment_tier"] == "gold"
    assert info["stage"] == 1
    assert info["round_in_stage"] == 5


def test_projected_score(engine):
    result = engine.projected_score(
        current_round=10, num_components=5, gold=30, surviving_units=6
    )
    # 5 * 2500 * 20 = 250000
    assert result["component_pts"] == 250_000
    # min(30//10, 5) = 3, 3 * 1000 * 20 = 60000
    assert result["interest_pts"] == 60_000
    # 6 * 250 * 20 = 30000
    assert result["surviving_pts"] == 30_000
    # 2750 * 20 = 55000
    assert result["time_pts"] == 55_000
    assert result["total"] == 395_000
