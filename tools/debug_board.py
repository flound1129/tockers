#!/usr/bin/env python3
"""Debug board/bench champion detection: crop hex cells and bench slots, save annotated images."""
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

import cv2
import numpy as np
from pathlib import Path

from overlay.config import TFTLayout

OUT_DIR = Path(__file__).parent.parent / "debug_crops"
layout = TFTLayout()


def debug_bench(frame: np.ndarray):
    """Crop and annotate bench champion slots."""
    region = layout.champion_bench
    bench_crop = frame[region.y:region.y + region.h,
                       region.x:region.x + region.w]
    cv2.imwrite(str(OUT_DIR / "bench_full.png"), bench_crop)

    print(f"\n=== BENCH ===")
    print(f"Region: x={region.x} y={region.y} w={region.w} h={region.h}")

    num_slots = 9
    slot_w = region.w // num_slots
    annotated = bench_crop.copy()

    for i in range(num_slots):
        sx = i * slot_w
        slot_crop = bench_crop[:, sx:sx + slot_w]
        cv2.imwrite(str(OUT_DIR / f"bench_slot_{i}.png"), slot_crop)

        brightness = np.mean(cv2.cvtColor(slot_crop, cv2.COLOR_BGR2GRAY))
        print(f"  Slot {i}: x={region.x + sx} brightness={brightness:.0f}")

        cv2.rectangle(annotated, (sx, 0), (sx + slot_w, region.h),
                      (0, 255, 0), 1)
        cv2.putText(annotated, f"{i}", (sx + 5, 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)

    cv2.imwrite(str(OUT_DIR / "bench_annotated.png"), annotated)
    print(f"  Saved bench_annotated.png + {num_slots} slot crops")


def debug_board(frame: np.ndarray):
    """Crop and annotate board hex grid cells."""
    hex_regions = layout.board_hex_regions
    ox, oy = layout.board_hex_origin
    max_x = max(r.x + r.w for r in hex_regions)
    max_y = max(r.y + r.h for r in hex_regions)
    board_crop = frame[oy:max_y, ox:max_x]
    cv2.imwrite(str(OUT_DIR / "board_full.png"), board_crop)

    print(f"\n=== BOARD ===")
    print(f"Origin: ({ox}, {oy})")
    print(f"Hex cells: {len(hex_regions)} "
          f"({layout.board_hex_rows}x{layout.board_hex_cols})")

    annotated = board_crop.copy()
    cols = layout.board_hex_cols

    for idx, region in enumerate(hex_regions):
        row = idx // cols
        col = idx % cols
        cell_crop = frame[region.y:region.y + region.h,
                          region.x:region.x + region.w]
        cv2.imwrite(str(OUT_DIR / f"board_r{row}_c{col}.png"), cell_crop)

        brightness = np.mean(cv2.cvtColor(cell_crop, cv2.COLOR_BGR2GRAY))
        print(f"  Cell r{row}c{col}: x={region.x} y={region.y} "
              f"brightness={brightness:.0f}")

        rx = region.x - ox
        ry = region.y - oy
        cv2.rectangle(annotated, (rx, ry), (rx + region.w, ry + region.h),
                      (0, 255, 0), 1)
        cv2.putText(annotated, f"{row},{col}", (rx + 3, ry + 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 255, 0), 1)

    cv2.imwrite(str(OUT_DIR / "board_annotated.png"), annotated)
    print(f"  Saved board_annotated.png + {len(hex_regions)} cell crops")


def main():
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
            print("Usage: python tools/debug_board.py [screenshot.png]")
            return

    OUT_DIR.mkdir(exist_ok=True)
    debug_bench(frame)
    debug_board(frame)
    print(f"\nAll crops saved to: {OUT_DIR}/")


if __name__ == "__main__":
    main()
