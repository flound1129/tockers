import numpy as np
import cv2
import pytest
from overlay.vision import TemplateMatcher


def _make_checkerboard(size, color_a, color_b):
    """Create a checkerboard pattern with two colors for reliable matching."""
    img = np.zeros((size, size, 3), dtype=np.uint8)
    half = size // 2
    # Top-left and bottom-right quadrants get color_a
    img[:half, :half] = color_a
    img[half:, half:] = color_a
    # Top-right and bottom-left quadrants get color_b
    img[:half, half:] = color_b
    img[half:, :half] = color_b
    return img


@pytest.fixture
def matcher(tmp_path):
    """Create a matcher with synthetic test templates that have internal variance."""
    templates_dir = tmp_path / "champions"
    templates_dir.mkdir()

    # Red-black checkerboard pattern (has variance, so TM_CCOEFF_NORMED works)
    red_pattern = _make_checkerboard(20, [0, 0, 255], [0, 0, 0])
    cv2.imwrite(str(templates_dir / "TFT16_TestChamp.png"), red_pattern)

    # Blue-black checkerboard pattern
    blue_pattern = _make_checkerboard(20, [255, 0, 0], [0, 0, 0])
    cv2.imwrite(str(templates_dir / "TFT16_OtherChamp.png"), blue_pattern)

    return TemplateMatcher(templates_dir)


def test_loads_templates(matcher):
    assert len(matcher.templates) == 2
    assert "TFT16_TestChamp" in matcher.templates


def test_finds_match_in_image(matcher):
    scene = np.zeros((100, 100, 3), dtype=np.uint8)
    # Embed the red checkerboard pattern at position (50, 30)
    pattern = _make_checkerboard(20, [0, 0, 255], [0, 0, 0])
    scene[30:50, 50:70] = pattern

    matches = matcher.find_matches(scene, threshold=0.95)
    assert len(matches) == 1
    assert matches[0].name == "TFT16_TestChamp"
    assert abs(matches[0].x - 50) <= 2
    assert abs(matches[0].y - 30) <= 2


def test_no_false_positives(matcher):
    scene = np.zeros((100, 100, 3), dtype=np.uint8)
    scene[:, :, 1] = 255  # All green — no match for red or blue patterns

    matches = matcher.find_matches(scene, threshold=0.95)
    assert len(matches) == 0
