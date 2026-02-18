from unittest.mock import patch, MagicMock
from overlay.stats import StatsRecorder
import overlay.strategy as strategy_module
from overlay.strategy import StrategyEngine


def test_ask_claude_sends_correct_prompt():
    engine = StrategyEngine(":memory:")
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Save your components.")]
    mock_response.stop_reason = "end_turn"
    mock_client.messages.create.return_value = mock_response

    with patch("overlay.strategy.Anthropic", return_value=mock_client):
        result = engine.ask_claude("Round 10, 5 components", "Should I level?")

    assert result == "Save your components."
    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert "2,500" in call_kwargs["system"]
    assert "Round 10" in call_kwargs["messages"][0]["content"]


def test_ask_claude_with_history():
    engine = StrategyEngine(":memory:")
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Still hold them.")]
    mock_response.stop_reason = "end_turn"
    mock_client.messages.create.return_value = mock_response

    history = [
        {"role": "user", "content": "Game state:\nRound 5\n\nQuestion: Should I build?"},
        {"role": "assistant", "content": "No, hold components."},
    ]

    with patch("overlay.strategy.Anthropic", return_value=mock_client):
        result = engine.ask_claude("Round 6, 5 components", "What about now?", history=history)

    assert result == "Still hold them."
    call_kwargs = mock_client.messages.create.call_args.kwargs
    messages = call_kwargs["messages"]
    assert len(messages) == 3
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
    assert messages[2]["role"] == "user"
    assert "What about now?" in messages[2]["content"]


def _make_engine_with_runs():
    """Create an in-memory engine with two completed runs."""
    engine = StrategyEngine(":memory:")
    # Seed two runs with round data
    rec = StatsRecorder(engine.conn)
    for _ in range(2):
        rec.start_run()
        rec.record_round("1-1", gold=10, level=2, lives=3,
                         component_count=5, shop=["Jinx"])
        rec.record_round("1-2", gold=14, level=2, lives=3,
                         component_count=5, shop=["Vi"])
        rec.end_run("eliminated")
    return engine


def test_update_strategy_calls_claude_and_writes_file(tmp_path):
    engine = _make_engine_with_runs()

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="# Updated Strategy\nNew findings.")]
    mock_response.stop_reason = "end_turn"

    with patch("overlay.strategy.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_response

        # Patch file path to tmp
        strategy_file = tmp_path / "strategy.md"
        strategy_file.write_text("# Old Strategy", encoding="utf-8")
        with patch.object(strategy_module, "_STRATEGY_FILE", strategy_file):
            engine.update_strategy()

        assert mock_client.messages.create.called
        assert strategy_file.read_text(encoding="utf-8") == "# Updated Strategy\nNew findings."


def test_update_strategy_skips_if_no_runs():
    engine = StrategyEngine(":memory:")

    with patch("overlay.strategy.Anthropic") as mock_cls:
        engine.update_strategy()
        mock_cls.assert_not_called()


def test_update_strategy_reloads_global(tmp_path):
    engine = _make_engine_with_runs()

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="# Fresh Strategy")]
    mock_response.stop_reason = "end_turn"

    with patch("overlay.strategy.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_response

        strategy_file = tmp_path / "strategy.md"
        strategy_file.write_text("# Old", encoding="utf-8")
        with patch.object(strategy_module, "_STRATEGY_FILE", strategy_file):
            engine.update_strategy()

        assert strategy_module._STRATEGY == "# Fresh Strategy"
