from unittest.mock import patch, MagicMock
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
