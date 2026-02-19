"""JSON save/load for screen region calibration."""
import json
from pathlib import Path

from .config import ScreenRegion, TFTLayout


def _region_to_dict(r: ScreenRegion) -> dict:
    return {"x": r.x, "y": r.y, "w": r.w, "h": r.h}


def _dict_to_region(d: dict) -> ScreenRegion:
    return ScreenRegion(d["x"], d["y"], d["w"], d["h"])


def save_calibration(path: Path, layout: TFTLayout) -> None:
    """Serialize a TFTLayout to a JSON calibration file."""
    data = {
        "resolution": list(layout.resolution),
        "regions": {
            "round_text": _region_to_dict(layout.round_text),
            "gold_text": _region_to_dict(layout.gold_text),
            "lives_text": _region_to_dict(layout.lives_text),
            "level_text": _region_to_dict(layout.level_text),
            "board": _region_to_dict(layout.board),
            "item_bench": _region_to_dict(layout.item_bench),
            "item_panel": _region_to_dict(layout.item_panel),
            "score_display": _region_to_dict(layout.score_display),
            "shop": _region_to_dict(layout.shop),
            "augment_select": _region_to_dict(layout.augment_select),
            "champion_bench": _region_to_dict(layout.champion_bench),
            **{name: _region_to_dict(r) for name, r in layout.extra_regions.items()},
        },
        "shop_card_names": [_region_to_dict(r) for r in layout.shop_card_names],
        "hex_grid": {
            "origin": list(layout.board_hex_origin),
            "cols": layout.board_hex_cols,
            "rows": layout.board_hex_rows,
            "col_width": layout.board_hex_col_width,
            "row_height": layout.board_hex_row_height,
            "row_offset": layout.board_hex_row_offset,
            "portrait_h": layout.board_hex_portrait_h,
        },
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_calibration(path: Path) -> dict:
    """Read a calibration JSON file and return the raw dict."""
    return json.loads(path.read_text(encoding="utf-8"))
