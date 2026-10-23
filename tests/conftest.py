from __future__ import annotations

import os

# Never open real windows in tests; must be set before Qt is imported.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from collections.abc import Callable
from pathlib import Path

import pytest
from PIL import Image

from tests.fixtures.generate import LARGE_SPEC, generate, write_photo
from tests.helpers.image_compare import compare_images, write_diff_image

GOLDEN_DIR = Path(__file__).parent / "golden" / "expected"
GOLDEN_DIFF_DIR = Path(__file__).parent / "golden" / "_diff"

AssertGolden = Callable[[Image.Image, str], None]


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--update-golden",
        action="store_true",
        default=False,
        help="rewrite golden reference images instead of comparing against them",
    )


@pytest.fixture(scope="session")
def sample_photos(tmp_path_factory: pytest.TempPathFactory) -> list[Path]:
    """The standard set of synthetic photos (various formats, ratios, EXIF, alpha)."""
    return generate(tmp_path_factory.mktemp("photos"))


@pytest.fixture(scope="session")
def large_photo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A 6000x4000 JPEG for memory/performance tests."""
    return write_photo(LARGE_SPEC, 99, tmp_path_factory.mktemp("large"))


@pytest.fixture
def assert_golden(request: pytest.FixtureRequest) -> AssertGolden:
    """Compare an image with tests/golden/expected/<name>.png.

    With --update-golden the reference image is rewritten instead.
    """
    update = bool(request.config.getoption("--update-golden"))

    def check(image: Image.Image, name: str) -> None:
        expected_path = GOLDEN_DIR / f"{name}.png"
        if update:
            expected_path.parent.mkdir(parents=True, exist_ok=True)
            image.save(expected_path)
            return
        if not expected_path.exists():
            pytest.fail(f"missing golden image {expected_path}; run pytest --update-golden")
        with Image.open(expected_path) as expected:
            expected.load()
        result = compare_images(image, expected)
        if not result.passed:
            diff_path = GOLDEN_DIFF_DIR / f"{name}.png"
            write_diff_image(image, expected, diff_path)
            pytest.fail(f"golden mismatch for {name}: {result.describe()} (diff: {diff_path})")

    return check
