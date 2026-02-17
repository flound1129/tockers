# Companion Window Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a `CompanionWindow` PyQt6 panel with live game info and an AI chat interface where users ask strategy questions via text.

**Architecture:** A second `QWidget` instantiated alongside the existing `OverlayWindow` in `main.py`. The companion shares the same `GameState` object that the vision loop updates every second. Chat messages inject game state as context before calling `StrategyEngine.ask_claude()`, which is extended to accept conversation history for multi-turn dialogue.

**Tech Stack:** PyQt6 (already installed), existing `StrategyEngine`, existing `GameState` dataclass, `anthropic` SDK (already used)

---

### Task 1: Extend `ask_claude` to support conversation history

**Files:**
- Modify: `overlay/strategy.py` (the `ask_claude` method)
- Modify: `tests/test_strategy_ai.py`

**Step 1: Add a test for conversation history**

In `tests/test_strategy_ai.py`, add below the existing test:

```python
def test_ask_claude_with_history():
    engine = StrategyEngine("tft.db")
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Still hold them.")]
    mock_client.messages.create.return_value = mock_response

    history = [
        {"role": "user", "content": "Game state:\nRound 5\n\nQuestion: Should I build?"},
        {"role": "assistant", "content": "No, hold components."},
    ]

    with patch("anthropic.Anthropic", return_value=mock_client):
        result = engine.ask_claude("Round 6, 5 components", "What about now?", history=history)

    assert result == "Still hold them."
    call_kwargs = mock_client.messages.create.call_args.kwargs
    messages = call_kwargs["messages"]
    assert len(messages) == 3          # 2 history + 1 new
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
    assert messages[2]["role"] == "user"
    assert "What about now?" in messages[2]["content"]
```

**Step 2: Run test to confirm it fails**

```
.venv/bin/pytest tests/test_strategy_ai.py::test_ask_claude_with_history -v
```

Expected: FAIL — `ask_claude()` doesn't accept a `history` kwarg yet.

**Step 3: Update `ask_claude` in `overlay/strategy.py`**

Replace the existing `ask_claude` method with:

```python
def ask_claude(self, game_state_summary: str, question: str,
               history: list[dict] | None = None) -> str:
    """Ask Claude for complex strategy advice. Returns advice text."""
    from anthropic import Anthropic
    client = Anthropic()

    system = (
        "You are a TFT Tocker's Trials score optimizer. 30 PVE rounds. "
        "The #1 rule: unused components on bench = 2,500 pts/component/round. "
        "This massively dominates all other scoring. NEVER recommend building "
        "items unless the player will lose a life without them. "
        "Other scoring: surviving champ = 250/round, close call (1 alive) = "
        "5,000/round, gold interest = 1,000/gold/round, star-up = 1,000 "
        "one-time, time bonus ~2,750/round. Be concise."
    )

    new_message = {
        "role": "user",
        "content": f"Game state:\n{game_state_summary}\n\nQuestion: {question}",
    }
    messages = list(history or []) + [new_message]

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=300,
        system=system,
        messages=messages,
    )
    return response.content[0].text
```

**Step 4: Run all tests**

```
.venv/bin/pytest tests/ -v
```

Expected: all 12 tests pass.

**Step 5: Commit**

```bash
git add overlay/strategy.py tests/test_strategy_ai.py
git commit -m "feat: support conversation history in ask_claude"
```

---

### Task 2: Build `CompanionWindow` skeleton

**Files:**
- Create: `overlay/companion.py`
- Create: `tests/test_companion.py`

**Step 1: Write a failing test for the window structure**

Create `tests/test_companion.py`:

```python
import pytest
from unittest.mock import MagicMock
from PyQt6.QtWidgets import QApplication
from overlay.companion import CompanionWindow
from overlay.vision import GameState


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
```

**Step 2: Run test to confirm it fails**

```
.venv/bin/pytest tests/test_companion.py -v
```

Expected: FAIL — `overlay/companion.py` doesn't exist.

**Step 3: Create `overlay/companion.py` with skeleton**

```python
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QLineEdit, QPushButton, QLabel, QScrollArea, QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QThread, pyqtSignal as Signal
from PyQt6.QtGui import QFont


class CompanionWindow(QWidget):
    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.setWindowTitle("Tocker's Companion")
        self.resize(400, 700)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.game_info_panel = self._build_game_info()
        self.chat_panel = self._build_chat()
        self.input_bar = self._build_input()

        layout.addWidget(self.game_info_panel, stretch=2)
        layout.addWidget(self.chat_panel, stretch=5)
        layout.addWidget(self.input_bar, stretch=1)
        self.setLayout(layout)

    def _build_game_info(self) -> QFrame:
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(6, 6, 6, 6)
        self._info_label = QLabel("Waiting for game state...")
        self._info_label.setWordWrap(True)
        self._info_label.setFont(QFont("Consolas", 10))
        layout.addWidget(self._info_label)
        return frame

    def _build_chat(self) -> QFrame:
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(6, 6, 6, 6)
        self._chat_display = QTextEdit()
        self._chat_display.setReadOnly(True)
        self._chat_display.setFont(QFont("Consolas", 10))
        layout.addWidget(self._chat_display)
        return frame

    def _build_input(self) -> QFrame:
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(6, 6, 6, 6)
        self._input_field = QLineEdit()
        self._input_field.setPlaceholderText("Ask a strategy question...")
        self._send_button = QPushButton("Send ↵")
        layout.addWidget(self._input_field, stretch=4)
        layout.addWidget(self._send_button, stretch=1)
        return frame
```

**Step 4: Run tests**

```
.venv/bin/pytest tests/test_companion.py -v
```

Expected: both tests pass.

**Step 5: Commit**

```bash
git add overlay/companion.py tests/test_companion.py
git commit -m "feat: add CompanionWindow skeleton with game info, chat, and input panels"
```

---

### Task 3: Game info panel — display live game state

**Files:**
- Modify: `overlay/companion.py`
- Modify: `tests/test_companion.py`

**Step 1: Add test for game state update**

Add to `tests/test_companion.py`:

```python
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
    assert "8" in text   # gold
    assert "142" in text  # score in thousands
```

**Step 2: Run test to confirm it fails**

```
.venv/bin/pytest tests/test_companion.py::test_game_info_updates -v
```

Expected: FAIL — `update_game_state` not defined.

**Step 3: Add `update_game_state` method to `CompanionWindow`**

Add this method to the `CompanionWindow` class:

```python
def update_game_state(self, state, projected_score: int = 0):
    """Refresh the game info panel with current state. Safe to call from any thread."""
    shop_names = [s for s in (state.shop or []) if s]
    items_count = len(state.items_on_bench)
    items_value = items_count * 2500 * max(0, 30 - self._round_to_int(state.round_number))

    lines = [
        f"Round: {state.round_number or '--'}  "
        f"Gold: {state.gold or '--'}  "
        f"Level: {state.level or '--'}  "
        f"Lives: {'♥' * (state.lives or 0)}",
        f"Shop: {', '.join(shop_names) or '—'}",
        f"Items on bench: {items_count}  (+{items_value:,} pts)",
        f"Projected score: {projected_score:,}",
    ]
    self._info_label.setText("\n".join(lines))

def _round_to_int(self, round_str: str | None) -> int:
    """Convert '2-5' to absolute round number (15)."""
    if not round_str or "-" not in round_str:
        return 0
    try:
        stage, rnd = round_str.split("-")
        return (int(stage) - 1) * 10 + int(rnd)
    except ValueError:
        return 0
```

**Step 4: Run tests**

```
.venv/bin/pytest tests/test_companion.py -v
```

Expected: all 3 tests pass.

**Step 5: Commit**

```bash
git add overlay/companion.py tests/test_companion.py
git commit -m "feat: game info panel displays live round, gold, level, shop, score"
```

---

### Task 4: Chat panel — send message and display response

**Files:**
- Modify: `overlay/companion.py`
- Modify: `tests/test_companion.py`

**Step 1: Add tests for chat send and display**

Add to `tests/test_companion.py`:

```python
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
```

**Step 2: Run tests to confirm they fail**

```
.venv/bin/pytest tests/test_companion.py::test_chat_appends_user_message -v
```

Expected: FAIL — `_on_send` not defined.

**Step 3: Wire up the input bar and add `_on_send`**

In `_build_input`, add connections after creating the widgets:

```python
self._send_button.clicked.connect(self._on_send)
self._input_field.returnPressed.connect(self._on_send)
```

Add these methods to `CompanionWindow`:

```python
def _on_send(self):
    text = self._input_field.text().strip()
    if not text:
        return
    self._input_field.clear()
    self._append_message("You", text)
    self._append_message("AI", "thinking...")
    self._current_game_state_text = self._info_label.text()
    self._start_ai_request(text)

def _append_message(self, sender: str, text: str):
    self._chat_display.append(f"[{sender}]  {text}\n")
    # Scroll to bottom
    sb = self._chat_display.verticalScrollBar()
    sb.setValue(sb.maximum())

def _start_ai_request(self, question: str):
    # Placeholder — implemented in Task 5
    pass
```

Also add to `__init__` after `self.engine = engine`:

```python
self._history: list[dict] = []
self._current_game_state_text = ""
```

**Step 4: Run tests**

```
.venv/bin/pytest tests/test_companion.py -v
```

Expected: all 6 tests pass.

**Step 5: Commit**

```bash
git add overlay/companion.py tests/test_companion.py
git commit -m "feat: chat panel displays messages and shows thinking indicator on send"
```

---

### Task 5: AI worker thread — non-blocking Claude API calls

**Files:**
- Modify: `overlay/companion.py`
- Modify: `tests/test_companion.py`

**Step 1: Add test for AI response rendering**

Add to `tests/test_companion.py`:

```python
def test_chat_replaces_thinking_with_response(app):
    mock_engine = MagicMock()
    mock_engine.ask_claude.return_value = "Hold your components."
    window = CompanionWindow(engine=mock_engine)
    window._input_field.setText("Should I build?")
    window._on_send()
    # Simulate the worker finishing synchronously
    window._on_ai_response("Hold your components.", "Should I build?")
    text = window._chat_display.toPlainText()
    assert "Hold your components." in text
    assert "thinking" not in text.lower()
```

**Step 2: Run test to confirm it fails**

```
.venv/bin/pytest tests/test_companion.py::test_chat_replaces_thinking_with_response -v
```

Expected: FAIL — `_on_ai_response` not defined.

**Step 3: Add `_AiWorker` thread and response handler**

Add `_AiWorker` class at the top of `companion.py` (outside `CompanionWindow`):

```python
class _AiWorker(QThread):
    finished = Signal(str, str)   # (response_text, original_question)
    error = Signal(str)

    def __init__(self, engine, game_state_text: str, question: str,
                 history: list[dict]):
        super().__init__()
        self.engine = engine
        self.game_state_text = game_state_text
        self.question = question
        self.history = history

    def run(self):
        try:
            response = self.engine.ask_claude(
                self.game_state_text, self.question, history=self.history
            )
            self.finished.emit(response, self.question)
        except Exception as e:
            self.error.emit(str(e))
```

Replace `_start_ai_request` in `CompanionWindow` with:

```python
def _start_ai_request(self, question: str):
    self._worker = _AiWorker(
        self.engine,
        self._current_game_state_text,
        question,
        list(self._history),
    )
    self._worker.finished.connect(self._on_ai_response)
    self._worker.error.connect(self._on_ai_error)
    self._worker.start()
```

Add response/error handlers to `CompanionWindow`:

```python
@pyqtSlot(str, str)
def _on_ai_response(self, response: str, question: str):
    # Replace "thinking..." with the actual response
    text = self._chat_display.toPlainText()
    text = text.replace("[AI]  thinking...\n\n", "")
    self._chat_display.setPlainText(text)
    self._append_message("AI", response)

    # Update conversation history (keep last 10 turns = 20 messages)
    self._history.append({
        "role": "user",
        "content": f"Game state:\n{self._current_game_state_text}\n\nQuestion: {question}",
    })
    self._history.append({"role": "assistant", "content": response})
    self._history = self._history[-20:]

@pyqtSlot(str)
def _on_ai_error(self, error: str):
    text = self._chat_display.toPlainText()
    text = text.replace("[AI]  thinking...\n\n", "")
    self._chat_display.setPlainText(text)
    self._append_message("AI", f"Error: {error}")
```

**Step 4: Run all tests**

```
.venv/bin/pytest tests/ -v
```

Expected: all 13 tests pass.

**Step 5: Commit**

```bash
git add overlay/companion.py tests/test_companion.py
git commit -m "feat: non-blocking AI worker thread with conversation history"
```

---

### Task 6: Wire companion window into `main.py`

**Files:**
- Modify: `overlay/main.py`

No new tests needed — this is wiring only; the existing integration tests cover it.

**Step 1: Import and instantiate `CompanionWindow`**

In `overlay/main.py`, add the import at the top of `main()`:

```python
from overlay.companion import CompanionWindow
```

After the existing `overlay = OverlayWindow()` / `overlay.show()` lines, add:

```python
companion = CompanionWindow(engine=engine)
companion.show()
```

**Step 2: Pass game state updates to companion**

In `vision_loop`, change the signature to accept `companion`:

```python
def vision_loop(capture, reader, engine, overlay, companion, stop_event):
```

Inside the loop, after building `projection`, add:

```python
companion.update_game_state(state, projected_score=projection["total"])
```

Update the call site in `main()` to pass `companion`:

```python
vision_thread = threading.Thread(
    target=vision_loop,
    args=(capture, reader, engine, overlay, companion, stop_event),
    daemon=True,
)
```

**Step 3: Run all tests**

```
.venv/bin/pytest tests/ -v
```

Expected: all 13 tests pass.

**Step 4: Smoke-test with mock image**

```
.venv/bin/python -m overlay.main --image=/tmp/tft_screenshot.png
```

Expected: both OverlayWindow and CompanionWindow appear. Game info panel shows round/gold/level. Chat input accepts text (API call will fail without a real `ANTHROPIC_API_KEY` but should show the error gracefully).

**Step 5: Commit**

```bash
git add overlay/main.py
git commit -m "feat: show CompanionWindow alongside OverlayWindow with shared game state"
```

---

### Task 7: Fix overlay window position for 2560x1440

**Files:**
- Modify: `overlay/ui.py`

The existing `OverlayWindow` hardcodes `self.move(3840 - 500, 50)` (4K coordinates). Update it for the actual resolution.

**Step 1: Update position in `_init_ui`**

In `overlay/ui.py`, change:

```python
self.move(3840 - 500, 50)
```

to:

```python
self.move(2560 - 460, 50)
```

**Step 2: Run tests**

```
.venv/bin/pytest tests/ -v
```

Expected: all 13 tests pass (no positional tests exist, just confirming nothing broke).

**Step 3: Commit**

```bash
git add overlay/ui.py
git commit -m "fix: update overlay position for 2560x1440 resolution"
```
