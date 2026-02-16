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
