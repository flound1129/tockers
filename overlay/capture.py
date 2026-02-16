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
