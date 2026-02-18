#!/usr/bin/env python3
"""Debug shop OCR: capture screen, crop shop regions, run OCR, save crops."""
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

import cv2
import numpy as np
import pytesseract
from pathlib import Path

from overlay.config import TFTLayout, ScreenRegion
from overlay.vision import _ocr_text, _load_champion_names

# Set tesseract path on Windows
if sys.platform == "win32":
    _win = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    if _win.exists():
        pytesseract.pytesseract.tesseract_cmd = str(_win)

OUT_DIR = Path(__file__).parent.parent / "debug_crops"
layout = TFTLayout()


def main():
    # Try dxcam first, fall back to a file argument
    frame = None
    if len(sys.argv) > 1:
        path = sys.argv[1]
        frame = cv2.imread(path)
        if frame is None:
            print(f"Could not read image: {path}")
            return
        print(f"Loaded image: {path} ({frame.shape[1]}x{frame.shape[0]})")
    else:
        try:
            import dxcam
            cam = dxcam.create()
            frame = cam.grab()
            if frame is None:
                print("dxcam grab returned None — is TFT visible?")
                return
            frame = cv2.cvtColor(np.array(frame), cv2.COLOR_RGB2BGR)
            print(f"Captured screen: {frame.shape[1]}x{frame.shape[0]}")
        except Exception as e:
            print(f"dxcam failed: {e}")
            print("Usage: python tools/debug_shop.py [screenshot.png]")
            return

    OUT_DIR.mkdir(exist_ok=True)
    champ_names = _load_champion_names()
    print(f"Loaded {len(champ_names)} champion names for fuzzy match\n")

    for i, region in enumerate(layout.shop_card_names):
        crop = frame[region.y:region.y + region.h, region.x:region.x + region.w]
        crop_path = OUT_DIR / f"shop_slot_{i}.png"
        cv2.imwrite(str(crop_path), crop)

        # Check if empty
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        if gray.mean() < 15:
            print(f"Slot {i}: EMPTY (avg brightness {gray.mean():.1f})")
            continue

        # Adaptive pass
        scaled_a = cv2.resize(gray, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
        proc_a = cv2.adaptiveThreshold(scaled_a, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                        cv2.THRESH_BINARY, 31, -10)
        text_a = pytesseract.image_to_string(proc_a, config="--psm 11").strip()
        text_a_line = text_a.split("\n")[0].strip() if text_a else ""
        cv2.imwrite(str(OUT_DIR / f"shop_slot_{i}_adaptive.png"), proc_a)

        # OTSU pass
        scaled_o = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        _, proc_o = cv2.threshold(scaled_o, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        text_o = pytesseract.image_to_string(proc_o, config="--psm 11").strip()
        text_o_line = text_o.split("\n")[0].strip() if text_o else ""
        cv2.imwrite(str(OUT_DIR / f"shop_slot_{i}_otsu.png"), proc_o)

        # Fuzzy match
        from difflib import SequenceMatcher, get_close_matches
        best_name = None
        best_ratio = 0.0
        for raw in [text_a_line, text_o_line]:
            if not raw:
                continue
            close = get_close_matches(raw, champ_names, n=1, cutoff=0.3)
            if close:
                ratio = SequenceMatcher(None, raw.lower(), close[0].lower()).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_name = close[0]

        print(f"Slot {i}: adaptive='{text_a_line}' otsu='{text_o_line}' "
              f"-> match='{best_name}' ({best_ratio:.2f})")
        print(f"  coords: x={region.x} y={region.y} w={region.w} h={region.h}")

    print(f"\nCrops saved to: {OUT_DIR}/")


if __name__ == "__main__":
    main()
