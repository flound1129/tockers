from overlay.main import _round_str_to_int


def test_round_str_to_int_normal():
    assert _round_str_to_int("1-1") == 1
    assert _round_str_to_int("2-5") == 15
    assert _round_str_to_int("3-10") == 30


def test_round_str_to_int_none_returns_zero():
    assert _round_str_to_int(None) == 0


def test_round_str_to_int_bad_input_returns_zero():
    assert _round_str_to_int("bad") == 0
    assert _round_str_to_int("") == 0
    assert _round_str_to_int("1-x") == 0
