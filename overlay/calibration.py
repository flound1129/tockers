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
            "rerolls_text": _region_to_dict(layout.rerolls_text),
            "ionia_trait_text": _region_to_dict(layout.ionia_trait_text),
            "board": _region_to_dict(layout.board),
            "item_bench": _region_to_dict(layout.item_bench),
            "trait_panel": _region_to_dict(layout.trait_panel),
            "dmg_champ": _region_to_dict(layout.dmg_champ),
            "dmg_stars": _region_to_dict(layout.dmg_stars),
            "dmg_bar": _region_to_dict(layout.dmg_bar),
            "dmg_amount": _region_to_dict(layout.dmg_amount),
            "score_display": _region_to_dict(layout.score_display),
            "augment_select": _region_to_dict(layout.augment_select),
            "augment_icons": _region_to_dict(layout.augment_icons),
            "augment_name_0": _region_to_dict(layout.augment_name_0),
            "augment_name_1": _region_to_dict(layout.augment_name_1),
            "augment_name_2": _region_to_dict(layout.augment_name_2),
            "champion_bench": _region_to_dict(layout.champion_bench),
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
