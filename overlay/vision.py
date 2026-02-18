import re
import sqlite3
import sys
from dataclasses import dataclass, field
from difflib import SequenceMatcher, get_close_matches
from pathlib import Path

import cv2
import numpy as np
import pytesseract

# On Windows, Tesseract is not on PATH by default
if sys.platform == "win32":
    _win_tesseract = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    if _win_tesseract.exists():
        pytesseract.pytesseract.tesseract_cmd = str(_win_tesseract)

from .config import DB_PATH, ScreenRegion, TFTLayout


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
            if tmpl.shape[0] > scene.shape[0] or tmpl.shape[1] > scene.shape[1]:
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


def _load_champion_names() -> list[str]:
    """Load all champion names from the database for fuzzy matching."""
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute("SELECT name FROM champions").fetchall()
        conn.close()
        return [r[0] for r in rows]
    except Exception:
        return []


CHAMPION_NAMES = _load_champion_names()


def _ocr_text(image: np.ndarray, scale: int = 4, method: str = "threshold",
              threshold_val: int = 140, psm: int = 7, whitelist: str = "") -> str:
    """Run Tesseract OCR on a BGR image with preprocessing."""
    try:
        import pytesseract
    except ImportError:
        return ""

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    scaled = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    if method == "otsu":
        _, proc = cv2.threshold(scaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    elif method == "adaptive":
        proc = cv2.adaptiveThreshold(scaled, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                      cv2.THRESH_BINARY, 31, -10)
    else:
        _, proc = cv2.threshold(scaled, threshold_val, 255, cv2.THRESH_BINARY)

    config = f"--psm {psm}"
    if whitelist:
        config += f" -c tessedit_char_whitelist={whitelist}"
    return pytesseract.image_to_string(proc, config=config).strip()


def _crop(frame: np.ndarray, region: ScreenRegion) -> np.ndarray:
    return frame[region.y:region.y + region.h, region.x:region.x + region.w]


@dataclass
class GameState:
    phase: str = "planning"
    my_board: list[Match] = field(default_factory=list)
    my_bench: list[Match] = field(default_factory=list)
    items_on_bench: list[Match] = field(default_factory=list)
    shop: list[str] = field(default_factory=list)
    gold: int | None = None
    level: int | None = None
    lives: int | None = None
    augment_choices: list[Match] = field(default_factory=list)
    round_number: str | None = None


class GameStateReader:
    def __init__(self, layout: TFTLayout,
                 champion_matcher: TemplateMatcher | None = None,
                 item_matcher: TemplateMatcher | None = None,
                 augment_matcher: TemplateMatcher | None = None):
        self.layout = layout
        self.champion_matcher = champion_matcher
        self.item_matcher = item_matcher
        self.augment_matcher = augment_matcher

    def read(self, frame: np.ndarray) -> GameState:
        state = GameState(
            phase=self._detect_phase(frame),
            round_number=self._read_round(frame),
            gold=self._read_gold(frame),
            lives=self._read_lives(frame),
            level=self._read_level(frame),
            shop=self._read_shop_names(frame),
        )

        if self.item_matcher:
            bench_crop = _crop(frame, self.layout.bench)
            state.items_on_bench = self.item_matcher.find_matches(bench_crop)

        if state.phase == "augment" and self.augment_matcher:
            aug_crop = _crop(frame, self.layout.augment_select)
            state.augment_choices = self.augment_matcher.find_matches(aug_crop)

        return state

    def _detect_phase(self, frame: np.ndarray) -> str:
        return "planning"  # TODO: detect from UI elements

    def _read_round(self, frame: np.ndarray) -> str | None:
        crop = _crop(frame, self.layout.round_text)
        text = _ocr_text(crop, scale=3, method="threshold",
                         threshold_val=140, psm=7)
        m = re.search(r"(\d+\s*-\s*\d+)", text)
        if m:
            return m.group(1).replace(" ", "")
        return None

    def _read_gold(self, frame: np.ndarray) -> int | None:
        crop = _crop(frame, self.layout.gold_text)
        text = _ocr_text(crop, scale=5, method="threshold",
                         threshold_val=140, psm=8,
                         whitelist="0123456789")
        digits = re.sub(r"\D", "", text)
        return int(digits) if digits else None

    def _read_lives(self, frame: np.ndarray) -> int | None:
        crop = _crop(frame, self.layout.lives_text)
        text = _ocr_text(crop, scale=5, method="threshold",
                         threshold_val=140, psm=7,
                         whitelist="0123456789")
        digits = re.sub(r"\D", "", text)
        if digits:
            val = int(digits[0])
            if 1 <= val <= 3:
                return val
        return None

    def _read_level(self, frame: np.ndarray) -> int | None:
        crop = _crop(frame, self.layout.level_text)
        text = _ocr_text(crop, scale=4, method="adaptive", psm=7)
        digits = re.findall(r"\d+", text)
        if digits:
            val = int(digits[-1])
            if 1 <= val <= 10:
                return val
        return None

    def _read_shop_names(self, frame: np.ndarray) -> list[str]:
        """Read champion names from 5 shop card slots using multi-pass OCR."""
        names = []
        for card_region in self.layout.shop_card_names:
            name = self._read_single_card(frame, card_region)
            names.append(name or "")
        return names

    def _read_single_card(self, frame: np.ndarray, region: ScreenRegion) -> str | None:
        """Read a single shop card name with adaptive + OTSU fallback."""
        crop = _crop(frame, region)
        if np.mean(crop) < 15:
            return None

        ocr_texts = []

        # Method 1: adaptive threshold, scale 4, PSM 11 (best for Illaoi-type names)
        text1 = _ocr_text(crop, scale=4, method="adaptive", psm=11)
        first_line = text1.split("\n")[0].strip()
        clean1 = re.sub(r"[^a-zA-Z\s']", "", first_line).strip()
        if clean1:
            ocr_texts.append(clean1)

        # Method 2: OTSU threshold, scale 3, PSM 11 (best for Kog'Maw-type names)
        text2 = _ocr_text(crop, scale=3, method="otsu", psm=11)
        first_line2 = text2.split("\n")[0].strip()
        clean2 = re.sub(r"[^a-zA-Z\s']", "", first_line2).strip()
        if clean2:
            ocr_texts.append(clean2)

        # Pick the OCR text that gives the highest similarity to any champion
        best_match = None
        best_ratio = 0
        for ocr in ocr_texts:
            matches = get_close_matches(ocr, CHAMPION_NAMES, n=1, cutoff=0.3)
            if matches:
                ratio = SequenceMatcher(None, ocr.lower(), matches[0].lower()).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_match = matches[0]

        return best_match
