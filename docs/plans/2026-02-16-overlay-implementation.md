# TFT Tocker's Trials Overlay — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a real-time screen overlay that reads TFT game state via computer vision and provides score-optimized strategy advice for Tocker's Trials.

**Architecture:** Modular Python app with four components — screen capture (DXcam), vision engine (OpenCV template matching), strategy agent (local SQLite rules + Claude API), and overlay UI (PyQt6). Core logic is platform-independent and testable on Linux; capture and overlay modules are Windows-only.

**Tech Stack:** Python 3.11+, DXcam/BetterCam, OpenCV, PyQt6, SQLite, Anthropic SDK

---

## Development Notes

- We develop on Linux. The overlay runs on Windows.
- Core logic (vision matching, strategy engine, DB queries) is testable on Linux with mock/sample images.
- Windows-specific code (screen capture, overlay window) is isolated behind interfaces so the rest can be tested without Windows.
- The `tft.db` database and `build_db.py` already exist in the project root.

---

### Task 1: Project Structure and Dependencies

**Files:**
- Create: `overlay/__init__.py`
- Create: `overlay/capture.py`
- Create: `overlay/vision.py`
- Create: `overlay/strategy.py`
- Create: `overlay/ui.py`
- Create: `overlay/main.py`
- Create: `overlay/config.py`
- Create: `tests/__init__.py`
- Create: `tests/test_vision.py`
- Create: `tests/test_strategy.py`
- Create: `requirements.txt`

**Step 1: Create the package structure**

```
overlay/
  __init__.py
  config.py      # Resolution, screen regions, paths
  capture.py     # Screen capture (Windows-only)
  vision.py      # Template matching, detection
  strategy.py    # Rules engine + Claude API
  ui.py          # PyQt6 overlay window
  main.py        # Entry point, wires everything together
tests/
  __init__.py
  test_vision.py
  test_strategy.py
references/       # Template images (champions, items, digits)
  champions/
  items/
  digits/
  augments/
```

**Step 2: Create requirements.txt**

```
opencv-python>=4.9
numpy>=1.24
PyQt6>=6.6
anthropic>=0.40
```

Note: `dxcam` or `bettercam` are Windows-only and installed separately on the target machine. Don't include them in requirements.txt — import them conditionally in `capture.py`.

**Step 3: Install cross-platform dependencies in the venv**

Run: `.venv/bin/pip install opencv-python numpy anthropic`
Expected: Success

**Step 4: Commit**

```
git add overlay/ tests/ requirements.txt
git commit -m "feat: scaffold overlay project structure"
```

---

### Task 2: Configuration Module

**Files:**
- Create: `overlay/config.py`

**Step 1: Write config with screen regions for 4K**

TFT at 3840x2160 has fixed UI positions. Define bounding boxes for each detection zone. These are approximate and will need calibration — we'll provide a calibration tool later.

```python
from dataclasses import dataclass, field
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "tft.db"
REFERENCES_DIR = Path(__file__).parent.parent / "references"

@dataclass
class ScreenRegion:
    x: int
    y: int
    w: int
    h: int

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.x + self.w, self.y + self.h)

@dataclass
class TFTLayout:
    """Screen regions for TFT UI elements at a given resolution."""
    resolution: tuple[int, int] = (3840, 2160)

    # These are starting estimates for 4K — will need calibration
    board: ScreenRegion = field(default_factory=lambda: ScreenRegion(1100, 500, 1640, 900))
    bench: ScreenRegion = field(default_factory=lambda: ScreenRegion(1100, 1450, 1640, 150))
    item_bench: ScreenRegion = field(default_factory=lambda: ScreenRegion(500, 1200, 400, 400))
    shop: ScreenRegion = field(default_factory=lambda: ScreenRegion(1060, 1900, 1720, 220))
    gold_level: ScreenRegion = field(default_factory=lambda: ScreenRegion(700, 1880, 300, 100))
    augment_select: ScreenRegion = field(default_factory=lambda: ScreenRegion(900, 600, 2040, 800))

CAPTURE_FPS = 1  # Frames per second during planning phase
MATCH_THRESHOLD = 0.8  # OpenCV template match confidence threshold
CLAUDE_MODEL = "claude-sonnet-4-5-20250929"
```

**Step 2: Commit**

```
git add overlay/config.py
git commit -m "feat: add config with 4K screen regions"
```

---

### Task 3: Vision Engine — Template Matching Core

**Files:**
- Create: `overlay/vision.py`
- Create: `tests/test_vision.py`
- Create: `tests/fixtures/` (test images)

**Step 1: Write failing tests for template matching**

```python
# tests/test_vision.py
import numpy as np
import cv2
import pytest
from overlay.vision import TemplateMatcher

@pytest.fixture
def matcher(tmp_path):
    """Create a matcher with synthetic test templates."""
    templates_dir = tmp_path / "champions"
    templates_dir.mkdir()
    red = np.zeros((20, 20, 3), dtype=np.uint8)
    red[:, :, 2] = 255  # BGR red
    cv2.imwrite(str(templates_dir / "TFT16_TestChamp.png"), red)

    blue = np.zeros((20, 20, 3), dtype=np.uint8)
    blue[:, :, 0] = 255  # BGR blue
    cv2.imwrite(str(templates_dir / "TFT16_OtherChamp.png"), blue)

    return TemplateMatcher(templates_dir)


def test_loads_templates(matcher):
    assert len(matcher.templates) == 2
    assert "TFT16_TestChamp" in matcher.templates


def test_finds_match_in_image(matcher):
    scene = np.zeros((100, 100, 3), dtype=np.uint8)
    scene[30:50, 50:70, 2] = 255  # Place red square at (50, 30)

    matches = matcher.find_matches(scene, threshold=0.95)
    assert len(matches) == 1
    assert matches[0].name == "TFT16_TestChamp"
    assert abs(matches[0].x - 50) <= 2
    assert abs(matches[0].y - 30) <= 2


def test_no_false_positives(matcher):
    scene = np.zeros((100, 100, 3), dtype=np.uint8)
    scene[:, :, 1] = 255  # All green

    matches = matcher.find_matches(scene, threshold=0.95)
    assert len(matches) == 0
```

**Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_vision.py -v`
Expected: FAIL (ImportError — vision module doesn't exist yet)

**Step 3: Implement TemplateMatcher**

```python
# overlay/vision.py
from dataclasses import dataclass
from pathlib import Path
import cv2
import numpy as np

@dataclass
class Match:
    name: str
    x: int
    y: int
    confidence: float

class TemplateMatcher:
    def __init__(self, templates_dir: Path):
        self.templates: dict[str, np.ndarray] = {}
        self._load_templates(templates_dir)

    def _load_templates(self, templates_dir: Path):
        for img_path in templates_dir.glob("*.png"):
            name = img_path.stem
            img = cv2.imread(str(img_path))
            if img is not None:
                self.templates[name] = img

    def find_matches(
        self,
        scene: np.ndarray,
        threshold: float = 0.8,
        names: list[str] | None = None,
    ) -> list[Match]:
        matches = []
        search = names or list(self.templates.keys())
        for name in search:
            tmpl = self.templates.get(name)
            if tmpl is None:
                continue
            result = cv2.matchTemplate(scene, tmpl, cv2.TM_CCOEFF_NORMED)
            locations = np.where(result >= threshold)
            for y, x in zip(*locations):
                matches.append(Match(
                    name=name, x=int(x), y=int(y),
                    confidence=float(result[y, x]),
                ))
        return self._deduplicate(matches)

    def _deduplicate(self, matches: list[Match], distance: int = 10) -> list[Match]:
        if not matches:
            return []
        matches.sort(key=lambda m: -m.confidence)
        kept = []
        for m in matches:
            if not any(
                abs(m.x - k.x) < distance and abs(m.y - k.y) < distance
                for k in kept
            ):
                kept.append(m)
        return kept
```

**Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_vision.py -v`
Expected: PASS

**Step 5: Commit**

```
git add overlay/vision.py tests/test_vision.py
git commit -m "feat: implement template matcher with deduplication"
```

---

### Task 4: Vision Engine — Game State Reader

**Files:**
- Modify: `overlay/vision.py`
- Create: `tests/test_game_state.py`

**Step 1: Add GameState dataclass and GameStateReader to vision.py**

```python
# Add to overlay/vision.py

@dataclass
class GameState:
    phase: str  # "planning", "combat", "augment", "carousel", "unknown"
    my_board: list[Match]
    my_bench: list[Match]
    items_on_bench: list[Match]
    shop: list[Match]
    gold: int | None
    level: int | None
    augment_choices: list[Match]
    round_number: int | None

class GameStateReader:
    def __init__(self, layout, champion_matcher, item_matcher,
                 augment_matcher, digit_matcher):
        self.layout = layout
        self.champion_matcher = champion_matcher
        self.item_matcher = item_matcher
        self.augment_matcher = augment_matcher
        self.digit_matcher = digit_matcher

    def read(self, frame: np.ndarray) -> GameState:
        phase = self._detect_phase(frame)
        board_crop = self._crop(frame, self.layout.board)
        bench_crop = self._crop(frame, self.layout.bench)
        item_crop = self._crop(frame, self.layout.item_bench)
        shop_crop = self._crop(frame, self.layout.shop)

        state = GameState(
            phase=phase,
            my_board=self.champion_matcher.find_matches(board_crop),
            my_bench=self.champion_matcher.find_matches(bench_crop),
            items_on_bench=self.item_matcher.find_matches(item_crop),
            shop=self.champion_matcher.find_matches(shop_crop),
            gold=self._read_gold(frame),
            level=None,
            augment_choices=[],
            round_number=None,
        )

        if phase == "augment":
            aug_crop = self._crop(frame, self.layout.augment_select)
            state.augment_choices = self.augment_matcher.find_matches(aug_crop)

        return state

    def _crop(self, frame: np.ndarray, region) -> np.ndarray:
        return frame[region.y:region.y + region.h, region.x:region.x + region.w]

    def _detect_phase(self, frame: np.ndarray) -> str:
        return "planning"  # Placeholder

    def _read_gold(self, frame: np.ndarray) -> int | None:
        return None  # Placeholder
```

**Step 2: Write test**

```python
# tests/test_game_state.py
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
```

**Step 3: Run tests**

Run: `.venv/bin/pytest tests/ -v`
Expected: PASS

**Step 4: Commit**

```
git add overlay/vision.py tests/test_game_state.py
git commit -m "feat: add GameStateReader with region cropping"
```

---

### Task 5: Strategy Engine — Local Rules

**Files:**
- Create: `overlay/strategy.py`
- Create: `tests/test_strategy.py`

**Step 1: Write failing tests**

```python
# tests/test_strategy.py
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
    assert len(board) > 0

def test_lookup_tocker_augments(engine):
    augments = engine.get_tocker_augments()
    assert len(augments) == 30

def test_round_info(engine):
    info = engine.get_round_info(5)
    assert info["round_type"] == "augment"
    assert info["augment_tier"] == "gold"
    assert info["stage"] == 1
    assert info["round_in_stage"] == 5
```

**Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_strategy.py -v`
Expected: FAIL (ImportError)

**Step 3: Implement StrategyEngine**

```python
# overlay/strategy.py
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

@dataclass
class EnemyUnit:
    character: str
    star_level: int
    row: int | None
    col: int | None
    items: list[str]
    mod_health: float | None
    mod_ad: float | None
    mod_ap: float | None

class StrategyEngine:
    def __init__(self, db_path: str | Path):
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row

    def component_score(self, num_components: int, rounds_remaining: int) -> int:
        return num_components * 2500 * rounds_remaining

    def interest(self, gold: int) -> int:
        return min(gold // 10, 5)

    def get_enemy_board(self, round_number: int) -> list[EnemyUnit]:
        rows = self.conn.execute("""
            SELECT eu.character, eu.star_level, eu.row, eu.col,
                   eu.items, eu.mod_health, eu.mod_ad, eu.mod_ap
            FROM enemy_units eu
            JOIN enemy_boards eb ON eu.board_id = eb.id
            WHERE eb.round_number = ?
        """, (round_number,)).fetchall()
        return [
            EnemyUnit(
                character=r["character"],
                star_level=r["star_level"],
                row=r["row"],
                col=r["col"],
                items=json.loads(r["items"]) if r["items"] else [],
                mod_health=r["mod_health"],
                mod_ad=r["mod_ad"],
                mod_ap=r["mod_ap"],
            )
            for r in rows
        ]

    def get_round_info(self, round_number: int) -> dict | None:
        row = self.conn.execute("""
            SELECT stage, round_in_stage, round_type, augment_tier
            FROM tocker_rounds WHERE round_number = ?
        """, (round_number,)).fetchone()
        if not row:
            return None
        return dict(row)

    def get_tocker_augments(self) -> list[dict]:
        rows = self.conn.execute("""
            SELECT api_name, name, description, effects, associated_traits
            FROM augments WHERE in_tockers = 1
            ORDER BY name
        """).fetchall()
        return [dict(r) for r in rows]

    def projected_score(self, current_round: int, num_components: int,
                        gold: int, surviving_units: int) -> dict:
        rounds_remaining = 30 - current_round
        component_pts = self.component_score(num_components, rounds_remaining)
        interest_pts = self.interest(gold) * 1000 * rounds_remaining
        surviving_pts = surviving_units * 250 * rounds_remaining
        time_pts = 2750 * rounds_remaining
        return {
            "component_pts": component_pts,
            "interest_pts": interest_pts,
            "surviving_pts": surviving_pts,
            "time_pts": time_pts,
            "total": component_pts + interest_pts + surviving_pts + time_pts,
        }
```

**Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_strategy.py -v`
Expected: PASS

**Step 5: Commit**

```
git add overlay/strategy.py tests/test_strategy.py
git commit -m "feat: implement strategy engine with scoring and DB lookups"
```

---

### Task 6: Strategy Engine — Claude API Integration

**Files:**
- Modify: `overlay/strategy.py`
- Create: `tests/test_strategy_ai.py`

**Step 1: Add Claude advisor method to StrategyEngine**

```python
# Add to overlay/strategy.py
import os
from overlay.config import CLAUDE_MODEL

# Add this method to the StrategyEngine class:

    def ask_claude(self, game_state_summary: str, question: str) -> str:
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

        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=300,
            system=system,
            messages=[{
                "role": "user",
                "content": f"Game state:\n{game_state_summary}\n\nQuestion: {question}",
            }],
        )
        return response.content[0].text
```

**Step 2: Write mock test**

```python
# tests/test_strategy_ai.py
from unittest.mock import patch, MagicMock
from overlay.strategy import StrategyEngine

def test_ask_claude_sends_correct_prompt():
    engine = StrategyEngine("tft.db")
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Save your components.")]
    mock_client.messages.create.return_value = mock_response

    with patch("overlay.strategy.Anthropic", return_value=mock_client):
        result = engine.ask_claude("Round 10, 5 components", "Should I level?")

    assert result == "Save your components."
    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert "2,500" in call_kwargs["system"]
    assert "Round 10" in call_kwargs["messages"][0]["content"]
```

**Step 3: Run tests**

Run: `.venv/bin/pytest tests/test_strategy_ai.py -v`
Expected: PASS

**Step 4: Commit**

```
git add overlay/strategy.py tests/test_strategy_ai.py
git commit -m "feat: add Claude API integration for strategy advice"
```

---

### Task 7: Screen Capture Module (Windows-only)

**Files:**
- Create: `overlay/capture.py`

**Step 1: Write capture module with mock fallback**

```python
# overlay/capture.py
import numpy as np

class ScreenCapture:
    """Captures game frames. Windows-only (uses DXcam)."""

    def __init__(self, target_fps: int = 1):
        self.target_fps = target_fps
        self._camera = None

    def start(self):
        try:
            import dxcam
        except ImportError:
            raise RuntimeError(
                "dxcam not available. Install on Windows: pip install dxcam"
            )
        self._camera = dxcam.create(output_color="BGR")

    def grab(self) -> np.ndarray | None:
        if self._camera is None:
            raise RuntimeError("Call start() first")
        return self._camera.grab()

    def stop(self):
        if self._camera is not None:
            del self._camera
            self._camera = None


class MockCapture:
    """Mock capture for testing. Loads frames from image files."""

    def __init__(self, image_path: str | None = None):
        self.image_path = image_path

    def start(self):
        pass

    def grab(self) -> np.ndarray | None:
        if self.image_path:
            import cv2
            return cv2.imread(self.image_path)
        return np.zeros((2160, 3840, 3), dtype=np.uint8)

    def stop(self):
        pass
```

**Step 2: Commit**

```
git add overlay/capture.py
git commit -m "feat: add screen capture with mock for Linux testing"
```

---

### Task 8: Overlay UI (PyQt6)

**Files:**
- Create: `overlay/ui.py`

**Step 1: Write the overlay window**

```python
# overlay/ui.py
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFont

class OverlayWindow(QWidget):
    """Transparent always-on-top overlay for TFT advice."""

    update_signal = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("TFT Overlay")
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._visible = True
        self._init_ui()
        self.update_signal.connect(self._on_update)

    def _init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        font = QFont("Consolas", 14)
        font.setBold(True)

        self.score_label = self._make_label(font, "Score: --")
        self.components_label = self._make_label(font, "Components: --")
        self.round_label = self._make_label(font, "Round: --")
        self.gold_label = self._make_label(font, "Gold: --")
        self.advice_label = self._make_label(font, "")

        for lbl in [self.score_label, self.components_label,
                     self.round_label, self.gold_label, self.advice_label]:
            layout.addWidget(lbl)

        self.setLayout(layout)
        self.move(3840 - 500, 50)
        self.resize(450, 300)

    def _make_label(self, font, text):
        lbl = QLabel(text)
        lbl.setFont(font)
        lbl.setStyleSheet(
            "color: white; background-color: rgba(0, 0, 0, 160); "
            "padding: 4px 8px; border-radius: 4px;"
        )
        return lbl

    @pyqtSlot(dict)
    def _on_update(self, data: dict):
        if "score" in data:
            self.score_label.setText(f"Score: {data['score']:,}")
        if "components" in data:
            self.components_label.setText(
                f"Components: {data['components']} "
                f"({data.get('component_value', 0):,} pts remaining)"
            )
        if "round" in data:
            self.round_label.setText(
                f"Round: {data['round']}/30 - {data.get('enemy_name', '')}"
            )
        if "gold" in data:
            interest = min(data["gold"] // 10, 5)
            self.gold_label.setText(
                f"Gold: {data['gold']} (interest: {interest}g)"
            )
        if "advice" in data:
            self.advice_label.setText(data["advice"])
            self.advice_label.setVisible(bool(data["advice"]))

    def toggle_visibility(self):
        self._visible = not self._visible
        self.setVisible(self._visible)
```

**Step 2: Commit**

```
git add overlay/ui.py
git commit -m "feat: add PyQt6 overlay window with score display"
```

---

### Task 9: Main Loop — Wire Everything Together

**Files:**
- Create: `overlay/main.py`

**Step 1: Write the main entry point**

```python
# overlay/main.py
import sys
import time
import threading
from pathlib import Path

from overlay.config import TFTLayout, CAPTURE_FPS, REFERENCES_DIR, DB_PATH
from overlay.capture import ScreenCapture, MockCapture
from overlay.vision import TemplateMatcher, GameStateReader
from overlay.strategy import StrategyEngine


def create_matchers():
    champ_dir = REFERENCES_DIR / "champions"
    item_dir = REFERENCES_DIR / "items"
    augment_dir = REFERENCES_DIR / "augments"
    digit_dir = REFERENCES_DIR / "digits"

    def load_or_empty(d):
        if d.exists():
            return TemplateMatcher(d)
        m = TemplateMatcher.__new__(TemplateMatcher)
        m.templates = {}
        return m

    return load_or_empty(champ_dir), load_or_empty(item_dir), \
           load_or_empty(augment_dir), load_or_empty(digit_dir)


def vision_loop(capture, reader, engine, overlay, stop_event):
    current_round = 0
    while not stop_event.is_set():
        frame = capture.grab()
        if frame is None:
            time.sleep(0.5)
            continue

        state = reader.read(frame)
        num_components = len(state.items_on_bench)
        gold = state.gold or 0
        rounds_remaining = 30 - current_round

        projection = engine.projected_score(
            current_round=current_round,
            num_components=num_components,
            gold=gold,
            surviving_units=len(state.my_board),
        )

        enemy_name = ""
        next_round = current_round + 1
        if next_round <= 30:
            info = engine.get_round_info(next_round)
            if info:
                enemy_name = (
                    f"Stage {info['stage']}-{info['round_in_stage']} "
                    f"({info['round_type']})"
                )

        overlay.update_signal.emit({
            "score": projection["total"],
            "components": num_components,
            "component_value": engine.component_score(
                num_components, rounds_remaining
            ),
            "round": current_round,
            "enemy_name": enemy_name,
            "gold": gold,
            "advice": "",
        })

        time.sleep(1.0 / CAPTURE_FPS)


def main():
    from PyQt6.QtWidgets import QApplication

    use_mock = "--mock" in sys.argv
    mock_image = None
    for arg in sys.argv:
        if arg.startswith("--image="):
            mock_image = arg.split("=", 1)[1]
            use_mock = True

    app = QApplication(sys.argv)
    layout = TFTLayout()
    champ_m, item_m, aug_m, digit_m = create_matchers()
    reader = GameStateReader(layout, champ_m, item_m, aug_m, digit_m)
    engine = StrategyEngine(DB_PATH)

    capture = MockCapture(mock_image) if use_mock else ScreenCapture(CAPTURE_FPS)
    capture.start()

    from overlay.ui import OverlayWindow
    overlay = OverlayWindow()
    overlay.show()

    stop_event = threading.Event()
    vision_thread = threading.Thread(
        target=vision_loop,
        args=(capture, reader, engine, overlay, stop_event),
        daemon=True,
    )
    vision_thread.start()

    try:
        sys.exit(app.exec())
    finally:
        stop_event.set()
        capture.stop()


if __name__ == "__main__":
    main()
```

**Step 2: Write `overlay/__init__.py`**

Empty file.

**Step 3: Commit**

```
git add overlay/main.py overlay/__init__.py
git commit -m "feat: wire up main loop with all components"
```

---

### Task 10: Reference Image Collection Tool

**Files:**
- Create: `tools/collect_references.py`

**Step 1: Write the collection helper**

```python
# tools/collect_references.py
"""
Helper to collect reference images from TFT.
Run on Windows while TFT is open.

Usage:
  python tools/collect_references.py
"""
import sys
from pathlib import Path
from datetime import datetime


def take_screenshot(output_dir: Path):
    try:
        import dxcam
    except ImportError:
        print("dxcam not available. Install: pip install dxcam")
        sys.exit(1)

    camera = dxcam.create(output_color="BGR")
    frame = camera.grab()
    if frame is None:
        print("Failed to capture frame. Is a game running?")
        sys.exit(1)

    import cv2
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = output_dir / f"screenshot_{timestamp}.png"
    cv2.imwrite(str(out_path), frame)
    print(f"Saved: {out_path} ({frame.shape[1]}x{frame.shape[0]})")
    del camera


if __name__ == "__main__":
    output_dir = Path(__file__).parent.parent / "references" / "raw"
    output_dir.mkdir(parents=True, exist_ok=True)
    take_screenshot(output_dir)
```

**Step 2: Create reference directory structure**

Create directories: `references/champions`, `references/items`, `references/augments`, `references/digits`, `references/raw`

**Step 3: Commit**

```
git add tools/collect_references.py
git commit -m "feat: add reference image collection tool"
```

---

## Next Steps After Implementation

1. **Collect reference images** — Run TFT on Windows, take screenshots, crop champion/item/augment icons into `references/` directories
2. **Calibrate screen regions** — Adjust `config.py` bounding boxes to match actual 4K TFT layout
3. **Test end-to-end on Windows** — Run with `--mock` first using screenshots, then live capture
4. **Add F12 hotkey** — Register global hotkey to toggle overlay visibility
5. **Refine phase detection** — Detect planning vs combat vs augment select reliably
6. **Add digit matching** — Template match 0-9 for gold/level reading
