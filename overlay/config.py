from dataclasses import dataclass, field
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "tft.db"
REFERENCES_DIR = Path(__file__).parent.parent / "references"
CALIBRATION_PATH = Path(__file__).parent.parent / "calibration.json"


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
    item_bench: ScreenRegion = field(default_factory=lambda: ScreenRegion(345, 1165, 1635, 55))
    item_panel: ScreenRegion = field(default_factory=lambda: ScreenRegion(0, 312, 151, 733))
    score_display: ScreenRegion = field(default_factory=lambda: ScreenRegion(2276, 378, 214, 91))
    shop: ScreenRegion = field(default_factory=lambda: ScreenRegion(590, 1260, 1400, 170))
    augment_select: ScreenRegion = field(default_factory=lambda: ScreenRegion(600, 400, 1360, 600))

    # Text regions for OCR
    round_text: ScreenRegion = field(default_factory=lambda: ScreenRegion(960, 15, 110, 35))
    gold_text: ScreenRegion = field(default_factory=lambda: ScreenRegion(1895, 1190, 45, 23))
    lives_text: ScreenRegion = field(default_factory=lambda: ScreenRegion(2355, 290, 65, 25))
    level_text: ScreenRegion = field(default_factory=lambda: ScreenRegion(330, 1193, 210, 25))

    # Individual shop card name bars (5 slots, 180px to exclude cost icon)
    shop_card_names: list[ScreenRegion] = field(default_factory=lambda: [
        ScreenRegion(600, 1390, 180, 30),
        ScreenRegion(880, 1390, 180, 30),
        ScreenRegion(1160, 1390, 180, 30),
        ScreenRegion(1440, 1390, 180, 30),
        ScreenRegion(1720, 1390, 180, 30),
    ])

    # Champion bench (taller than item bench to capture full portraits)
    champion_bench: ScreenRegion = field(
        default_factory=lambda: ScreenRegion(345, 1000, 1635, 120)
    )

    # Extra regions loaded from calibration.json (not hardcoded in code)
    extra_regions: dict[str, ScreenRegion] = field(default_factory=dict)

    # Board hex grid parameters (player side only — enemy data is in DB)
    # Calibrated from health bar positions: y=652, 779, 927, 971
    # Perspective compresses back rows, so row_height=130 is a compromise
    board_hex_origin: tuple[int, int] = (600, 555)
    board_hex_cols: int = 7
    board_hex_rows: int = 4
    board_hex_col_width: int = 194
    board_hex_row_height: int = 130
    board_hex_row_offset: int = 97  # odd-row horizontal offset
    board_hex_portrait_h: int = 115

    @property
    def board_hex_regions(self) -> list[ScreenRegion]:
        """Compute per-cell ScreenRegion list for the board hex grid."""
        regions = []
        ox, oy = self.board_hex_origin
        for row in range(self.board_hex_rows):
            for col in range(self.board_hex_cols):
                x = ox + col * self.board_hex_col_width
                if row % 2 == 1:
                    x += self.board_hex_row_offset
                y = oy + row * self.board_hex_row_height
                regions.append(ScreenRegion(
                    x, y,
                    self.board_hex_col_width,
                    self.board_hex_portrait_h,
                ))
        return regions

    @classmethod
    def from_calibration(cls, path: Path | None = None) -> "TFTLayout":
        """Load layout from calibration.json, falling back to hardcoded defaults."""
        if path is None:
            path = CALIBRATION_PATH
        if not path.exists():
            return cls()

        from .calibration import load_calibration, _dict_to_region
        try:
            data = load_calibration(path)
        except Exception:
            return cls()

        layout = cls()
        if "resolution" in data:
            layout.resolution = tuple(data["resolution"])

        regions = data.get("regions", {})
        for name, d in regions.items():
            r = _dict_to_region(d)
            if hasattr(layout, name) and name != "extra_regions":
                setattr(layout, name, r)
            else:
                layout.extra_regions[name] = r

        if "shop_card_names" in data:
            layout.shop_card_names = [_dict_to_region(d) for d in data["shop_card_names"]]

        hg = data.get("hex_grid", {})
        if "origin" in hg:
            layout.board_hex_origin = tuple(hg["origin"])
        for key in ("cols", "rows", "col_width", "row_height", "row_offset", "portrait_h"):
            if key in hg:
                setattr(layout, f"board_hex_{key}", hg[key])

        return layout


CAPTURE_FPS = 1  # Frames per second during planning phase
MATCH_THRESHOLD = 0.8  # OpenCV template match confidence threshold
BENCH_MATCH_THRESHOLD = 0.75
BOARD_MATCH_THRESHOLD = 0.70
BENCH_ICON_SIZE = 60  # estimated champion icon size on bench
CLAUDE_MODEL = "claude-sonnet-4-5-20250929"
