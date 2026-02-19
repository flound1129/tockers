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

from .config import (
    DB_PATH, ScreenRegion, TFTLayout,
    BENCH_MATCH_THRESHOLD, BOARD_MATCH_THRESHOLD,
)


@dataclass
class Match:
    name: str
    x: int
    y: int
    confidence: float
    stars: int = 0  # 0=unknown, 1/2/3=detected star level


class TemplateMatcher:
    def __init__(self, templates_dir: Path, icon_size: int | None = None):
        self.templates: dict[str, np.ndarray] = {}
        self._load_templates(templates_dir, icon_size)

    def _load_templates(self, templates_dir: Path, icon_size: int | None):
        for img_path in templates_dir.glob("*.png"):
            name = img_path.stem
            img = cv2.imread(str(img_path))
            if img is not None:
                if icon_size and (img.shape[0] != icon_size or img.shape[1] != icon_size):
                    img = cv2.resize(img, (icon_size, icon_size),
                                     interpolation=cv2.INTER_AREA)
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
        return [r[0].strip() for r in rows]
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
class DamageBreakdown:
    physical_pct: float = 0.0  # red pixels
    magic_pct: float = 0.0     # blue pixels
    true_pct: float = 0.0      # white pixels
    amount: int | None = None   # total damage number
    champion: str | None = None
    stars: int = 0


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
    rerolls: int | None = None
    ionia_path: str | None = None
    top_damage: DamageBreakdown | None = None


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
            rerolls=self._read_rerolls(frame),
            ionia_path=self._read_ionia_path(frame),
            shop=self._read_shop_names(frame),
        )

        if self.item_matcher:
            bench_crop = _crop(frame, self.layout.item_bench)
            state.items_on_bench = self.item_matcher.find_matches(bench_crop)

        if self.champion_matcher and self.champion_matcher.templates:
            state.my_bench = self._detect_bench_champions(frame)
            state.my_board = self._detect_board_champions(frame)

        if state.phase == "augment" and self.augment_matcher:
            aug_crop = _crop(frame, self.layout.augment_select)
            state.augment_choices = self.augment_matcher.find_matches(aug_crop)

        state.top_damage = self._read_top_damage(frame)

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

    def _read_rerolls(self, frame: np.ndarray) -> int | None:
        crop = _crop(frame, self.layout.rerolls_text)
        text = _ocr_text(crop, scale=5, method="threshold",
                         threshold_val=140, psm=8,
                         whitelist="0123456789")
        digits = re.sub(r"\D", "", text)
        if digits:
            val = int(digits)
            if 0 <= val <= 99:
                return val
        return None

    # Map displayed path names to trait names
    IONIA_PATH_MAP = {
        "Blade": "Blades",
        "Determination": "Determination",
        "Enlightenment": "Enlightenment",
        "Prosperous": "Generosity",
        "Spirit": "Spirit",
        "Transcendence": "Transcendence",
    }

    def _read_ionia_path(self, frame: np.ndarray) -> str | None:
        crop = _crop(frame, self.layout.ionia_trait_text)
        if np.mean(crop) < 10:
            return None
        text = _ocr_text(crop, scale=4, method="adaptive", psm=7)
        if not text:
            return None
        # Extract keyword from "Path of the <Name>:" or "Path of <Name>:"
        from difflib import get_close_matches
        words = re.findall(r"[a-zA-Z]+", text)
        for word in words:
            matches = get_close_matches(
                word, list(self.IONIA_PATH_MAP.keys()), n=1, cutoff=0.6
            )
            if matches:
                return self.IONIA_PATH_MAP[matches[0]]
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
        if np.mean(crop) < 25:
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

    def _detect_bench_champions(self, frame: np.ndarray) -> list[Match]:
        """Detect champions on the bench using template matching."""
        bench_crop = _crop(frame, self.layout.champion_bench)
        matches = self.champion_matcher.find_matches(
            bench_crop, threshold=BENCH_MATCH_THRESHOLD,
        )
        # Translate coordinates to full-frame and detect stars
        region = self.layout.champion_bench
        result = []
        for m in matches:
            m.x += region.x
            m.y += region.y
            m.stars = self._detect_stars(frame, m)
            result.append(m)
        return result

    def _detect_board_champions(self, frame: np.ndarray) -> list[Match]:
        """Detect champions on the board by scanning each hex cell."""
        results = []
        for region in self.layout.board_hex_regions:
            cell_crop = _crop(frame, region)
            # Skip empty cells
            gray = cv2.cvtColor(cell_crop, cv2.COLOR_BGR2GRAY)
            if np.mean(gray) < 15:
                continue
            matches = self.champion_matcher.find_matches(
                cell_crop, threshold=BOARD_MATCH_THRESHOLD,
            )
            if matches:
                best = max(matches, key=lambda m: m.confidence)
                best.x += region.x
                best.y += region.y
                best.stars = self._detect_stars(frame, best)
                results.append(best)
        return results

    def _detect_stars(self, frame: np.ndarray, match: Match) -> int:
        """Detect star level (1/2/3) from gold/silver pips below a champion.

        Looks at a horizontal strip below the detected champion position and
        counts gold-colored pixels (HSV thresholding) to classify star level.
        """
        # Crop a strip below the champion icon
        pip_y = match.y + 60  # below the icon
        pip_h = 20
        pip_x = match.x - 10
        pip_w = 80
        # Clamp to frame bounds
        h, w = frame.shape[:2]
        pip_x = max(0, pip_x)
        pip_y = max(0, pip_y)
        if pip_x + pip_w > w:
            pip_w = w - pip_x
        if pip_y + pip_h > h:
            pip_h = h - pip_y
        if pip_w <= 0 or pip_h <= 0:
            return 0

        pip_crop = frame[pip_y:pip_y + pip_h, pip_x:pip_x + pip_w]
        hsv = cv2.cvtColor(pip_crop, cv2.COLOR_BGR2HSV)

        # Gold pips: H 20-40, S > 100, V > 150
        gold_mask = cv2.inRange(hsv, (20, 100, 150), (40, 255, 255))
        gold_pixels = cv2.countNonZero(gold_mask)

        # Silver pips: S < 60, V > 180 (grayish-white)
        silver_mask = cv2.inRange(hsv, (0, 0, 180), (180, 60, 255))
        silver_pixels = cv2.countNonZero(silver_mask)

        total_pip_pixels = gold_pixels + silver_pixels
        if gold_pixels > 50:
            return 3  # 3-star has prominent gold pips
        elif total_pip_pixels > 30:
            return 2  # 2-star has silver/gold pips
        elif total_pip_pixels > 5:
            return 1
        return 1  # Default to 1-star if champion is detected

    def _read_top_damage(self, frame: np.ndarray) -> DamageBreakdown | None:
        """Read the #1 damage dealer from three separate regions."""
        bar_crop = _crop(frame, self.layout.dmg_bar)
        if np.mean(bar_crop) < 10:
            return None  # bar not visible

        hsv = cv2.cvtColor(bar_crop, cv2.COLOR_BGR2HSV)

        # Red (physical): H 0-10 or 170-180, S > 80, V > 80
        red_lo = cv2.inRange(hsv, (0, 80, 80), (10, 255, 255))
        red_hi = cv2.inRange(hsv, (170, 80, 80), (180, 255, 255))
        red_px = cv2.countNonZero(red_lo) + cv2.countNonZero(red_hi)

        # Blue (magic): H 100-130, S > 80, V > 80
        blue_px = cv2.countNonZero(cv2.inRange(hsv, (100, 80, 80), (130, 255, 255)))

        # White (true): S < 40, V > 200
        white_px = cv2.countNonZero(cv2.inRange(hsv, (0, 0, 200), (180, 40, 255)))

        total = red_px + blue_px + white_px
        if total == 0:
            return None

        dmg = DamageBreakdown(
            physical_pct=red_px / total,
            magic_pct=blue_px / total,
            true_pct=white_px / total,
        )

        # Identify champion from dmg_champ icon region
        if self.champion_matcher and self.champion_matcher.templates:
            champ_crop = _crop(frame, self.layout.dmg_champ)
            matches = self.champion_matcher.find_matches(champ_crop, threshold=BOARD_MATCH_THRESHOLD)
            if matches:
                best = max(matches, key=lambda m: m.confidence)
                dmg.champion = best.name

        # Read stars from dmg_stars region (gold/silver pip counting)
        stars_crop = _crop(frame, self.layout.dmg_stars)
        hsv_stars = cv2.cvtColor(stars_crop, cv2.COLOR_BGR2HSV)
        gold_mask = cv2.inRange(hsv_stars, (20, 100, 150), (40, 255, 255))
        gold_px = cv2.countNonZero(gold_mask)
        silver_mask = cv2.inRange(hsv_stars, (0, 0, 180), (180, 60, 255))
        silver_px = cv2.countNonZero(silver_mask)
        pip_total = gold_px + silver_px
        if gold_px > 50:
            dmg.stars = 3
        elif pip_total > 30:
            dmg.stars = 2
        elif pip_total > 5:
            dmg.stars = 1

        # OCR the damage number
        amt_crop = _crop(frame, self.layout.dmg_amount)
        amt_text = _ocr_text(amt_crop, scale=5, method="threshold",
                             threshold_val=140, psm=8,
                             whitelist="0123456789")
        digits = re.sub(r"\D", "", amt_text)
        if digits:
            dmg.amount = int(digits)

        return dmg
