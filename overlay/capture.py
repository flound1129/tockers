import logging
import time

import numpy as np

log = logging.getLogger(__name__)

_GAME_CHECK_INTERVAL = 3.0  # seconds between window checks


class ScreenCapture:
    """Captures game frames. Windows-only (uses DXcam)."""

    def __init__(self, target_fps: int = 1,
                 game_resolution: tuple[int, int] = (2560, 1440)):
        self.target_fps = target_fps
        self.game_w, self.game_h = game_resolution
        self._camera = None
        self._game_running = False
        self._game_check_time = 0.0

    def start(self):
        try:
            import dxcam
        except ImportError:
            raise RuntimeError(
                "dxcam not available. Install on Windows: pip install dxcam"
            )
        self._camera = dxcam.create(output_color="BGR")

    def is_game_running(self) -> bool:
        now = time.monotonic()
        if now - self._game_check_time < _GAME_CHECK_INTERVAL:
            return self._game_running
        self._game_check_time = now
        was_running = self._game_running
        self._game_running = self._find_game_window()
        if self._game_running != was_running:
            log.info("game window %s", "found" if self._game_running else "lost")
        return self._game_running

    @staticmethod
    def _find_game_window() -> bool:
        """Check for the League of Legends game window via Win32 API."""
        try:
            import ctypes
            hwnd = ctypes.windll.user32.FindWindowW("RiotWindowClass", None)
            return hwnd != 0
        except Exception:
            return True  # assume running if we can't check

    def grab(self) -> np.ndarray | None:
        if self._camera is None:
            raise RuntimeError("Call start() first")
        frame = self._camera.grab()
        if frame is None:
            return None
        h, w = frame.shape[:2]
        if w > self.game_w:
            x_off = (w - self.game_w) // 2
            frame = frame[:, x_off:x_off + self.game_w]
        if h > self.game_h:
            y_off = (h - self.game_h) // 2
            frame = frame[y_off:y_off + self.game_h, :]
        return frame

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

    def is_game_running(self) -> bool:
        return True

    def grab(self) -> np.ndarray | None:
        if self.image_path:
            import cv2
            return cv2.imread(self.image_path)
        return np.zeros((2160, 3840, 3), dtype=np.uint8)

    def stop(self):
        pass
