from dataclasses import dataclass
from pathlib import Path
import cv2
import numpy as np


@dataclass
class Match:
    name: str
    x: int
    y: int
    confidence: float


class TemplateMatcher:
    def __init__(self, templates_dir: Path):
        self.templates: dict[str, np.ndarray] = {}
        self._load_templates(templates_dir)

    def _load_templates(self, templates_dir: Path):
        for img_path in templates_dir.glob("*.png"):
            name = img_path.stem
            img = cv2.imread(str(img_path))
            if img is not None:
                self.templates[name] = img

    def find_matches(
        self,
        scene: np.ndarray,
        threshold: float = 0.8,
        names: list[str] | None = None,
    ) -> list[Match]:
        matches = []
        search = names or list(self.templates.keys())
        for name in search:
            tmpl = self.templates.get(name)
            if tmpl is None:
                continue
            result = cv2.matchTemplate(scene, tmpl, cv2.TM_CCOEFF_NORMED)
            locations = np.where(result >= threshold)
            for y, x in zip(*locations):
                matches.append(Match(
                    name=name, x=int(x), y=int(y),
                    confidence=float(result[y, x]),
                ))
        return self._deduplicate(matches)

    def _deduplicate(self, matches: list[Match], distance: int = 10) -> list[Match]:
        if not matches:
            return []
        matches.sort(key=lambda m: -m.confidence)
        kept = []
        for m in matches:
            if not any(
                abs(m.x - k.x) < distance and abs(m.y - k.y) < distance
                for k in kept
            ):
                kept.append(m)
        return kept
