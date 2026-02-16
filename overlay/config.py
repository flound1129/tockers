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
