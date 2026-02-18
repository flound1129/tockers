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
    """Screen regions for TFT UI elements at 2560x1440."""
    resolution: tuple[int, int] = (2560, 1440)

    # Calibrated from actual screenshot at 2560x1440
    board: ScreenRegion = field(default_factory=lambda: ScreenRegion(600, 400, 1360, 600))
    bench: ScreenRegion = field(default_factory=lambda: ScreenRegion(345, 1190, 1635, 55))
    item_bench: ScreenRegion = field(default_factory=lambda: ScreenRegion(345, 1190, 1635, 55))
    shop: ScreenRegion = field(default_factory=lambda: ScreenRegion(590, 1260, 1400, 170))
    augment_select: ScreenRegion = field(default_factory=lambda: ScreenRegion(600, 400, 1360, 600))

    # Text regions for OCR
    round_text: ScreenRegion = field(default_factory=lambda: ScreenRegion(960, 15, 110, 35))
    gold_text: ScreenRegion = field(default_factory=lambda: ScreenRegion(1895, 1190, 45, 23))
    lives_text: ScreenRegion = field(default_factory=lambda: ScreenRegion(2355, 290, 65, 25))
    level_text: ScreenRegion = field(default_factory=lambda: ScreenRegion(330, 1193, 210, 25))

    # Individual shop card name bars (5 slots, ~280px each)
    shop_card_names: list[ScreenRegion] = field(default_factory=lambda: [
        ScreenRegion(590, 1400, 280, 30),
        ScreenRegion(870, 1400, 280, 30),
        ScreenRegion(1150, 1400, 280, 30),
        ScreenRegion(1430, 1400, 280, 30),
        ScreenRegion(1710, 1400, 280, 30),
    ])


CAPTURE_FPS = 1  # Frames per second during planning phase
MATCH_THRESHOLD = 0.8  # OpenCV template match confidence threshold
CLAUDE_MODEL = "claude-sonnet-4-5-20250929"
