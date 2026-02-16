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


@dataclass
class GameState:
    phase: str  # "planning", "combat", "augment", "carousel", "unknown"
    my_board: list[Match]
    my_bench: list[Match]
    items_on_bench: list[Match]
    shop: list[Match]
    gold: int | None
    level: int | None
    augment_choices: list[Match]
    round_number: int | None


class GameStateReader:
    def __init__(self, layout, champion_matcher, item_matcher,
                 augment_matcher, digit_matcher):
        self.layout = layout
        self.champion_matcher = champion_matcher
        self.item_matcher = item_matcher
        self.augment_matcher = augment_matcher
        self.digit_matcher = digit_matcher

    def read(self, frame: np.ndarray) -> GameState:
        phase = self._detect_phase(frame)
        board_crop = self._crop(frame, self.layout.board)
        bench_crop = self._crop(frame, self.layout.bench)
        item_crop = self._crop(frame, self.layout.item_bench)
        shop_crop = self._crop(frame, self.layout.shop)

        state = GameState(
            phase=phase,
            my_board=self.champion_matcher.find_matches(board_crop),
            my_bench=self.champion_matcher.find_matches(bench_crop),
            items_on_bench=self.item_matcher.find_matches(item_crop),
            shop=self.champion_matcher.find_matches(shop_crop),
            gold=self._read_gold(frame),
            level=None,
            augment_choices=[],
            round_number=None,
        )

        if phase == "augment":
            aug_crop = self._crop(frame, self.layout.augment_select)
            state.augment_choices = self.augment_matcher.find_matches(aug_crop)

        return state

    def _crop(self, frame: np.ndarray, region) -> np.ndarray:
        return frame[region.y:region.y + region.h, region.x:region.x + region.w]

    def _detect_phase(self, frame: np.ndarray) -> str:
        return "planning"  # Placeholder

    def _read_gold(self, frame: np.ndarray) -> int | None:
        return None  # Placeholder
