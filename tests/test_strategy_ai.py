from unittest.mock import patch, MagicMock
from overlay.strategy import StrategyEngine


def test_ask_claude_sends_correct_prompt():
    engine = StrategyEngine("tft.db")
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Save your components.")]
    mock_client.messages.create.return_value = mock_response

    with patch("anthropic.Anthropic", return_value=mock_client):
        result = engine.ask_claude("Round 10, 5 components", "Should I level?")

    assert result == "Save your components."
    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert "2,500" in call_kwargs["system"]
    assert "Round 10" in call_kwargs["messages"][0]["content"]
