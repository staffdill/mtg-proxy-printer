"""Locating and clicking Design Space's own UI by matching pixels.

Design Space is Electron/Chromium and exposes no UI Automation tree — probing its
window returns 3 elements, two of them opaque "Chrome Legacy Window" panes — so
this is the only way in. Native Windows dialogs are NOT handled here: see
native.py, which has real control handles and needs none of this guesswork.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import cv2
import numpy as np
import pyautogui
from PIL import Image

DEFAULT_CONFIDENCE = 0.85
TEMPLATE_DIR = Path(__file__).parent / "templates"
DEBUG_DIR = Path(__file__).resolve().parents[2] / "debug"


class TemplateNotFound(RuntimeError):
    """A template could not be located on screen, or its file is missing.

    Always fatal. A half-recognized UI is exactly when blind clicking is most
    dangerous: the next click lands somewhere unintended, and there is a blade
    and a printer attached to this application.
    """


#: TM_CCOEFF_NORMED is a correlation coefficient, so a template with no variance
#: (a flat, featureless crop) has an undefined match score and OpenCV returns
#: garbage — confidently, and at an arbitrary location. That is the worst possible
#: failure here, so refuse the template rather than click where it points.
MIN_TEMPLATE_STDDEV = 1.0


def match(screen: Image.Image, template: Image.Image) -> tuple[float, tuple[int, int]]:
    """Best match of template within screen, as (confidence, centre_xy) in
    screenshot pixels. Grayscale, so Design Space's colour/theme shifts do not
    break matching."""
    haystack = cv2.cvtColor(np.array(screen.convert("RGB")), cv2.COLOR_RGB2GRAY)
    needle = cv2.cvtColor(np.array(template.convert("RGB")), cv2.COLOR_RGB2GRAY)
    if float(needle.std()) < MIN_TEMPLATE_STDDEV:
        raise TemplateNotFound(
            "template is featureless (stddev "
            f"{needle.std():.2f} < {MIN_TEMPLATE_STDDEV}); "
            "normalized correlation cannot match it and would return a garbage "
            "location — re-crop it around something with contrast"
        )
    result = cv2.matchTemplate(haystack, needle, cv2.TM_CCOEFF_NORMED)
    _, confidence, _, (x, y) = cv2.minMaxLoc(result)
    return float(confidence), (x + needle.shape[1] // 2, y + needle.shape[0] // 2)


@dataclass
class Screen:
    template_dir: Path = TEMPLATE_DIR
    confidence: float = DEFAULT_CONFIDENCE
    debug_dir: Path = DEBUG_DIR
    grab: Callable[[], Image.Image] = field(default=lambda: pyautogui.screenshot())

    def scale(self) -> float:
        """Screenshot pixels per logical screen point. 1.0 at 100% DPI, but
        computed rather than assumed, so a display change cannot silently send
        every click to the wrong place."""
        shot_w, _ = self.grab().size
        screen_w, _ = pyautogui.size()
        return shot_w / screen_w

    def load(self, name: str) -> Image.Image:
        path = self.template_dir / name
        if not path.is_file():
            raise TemplateNotFound(f"template file missing: {path}")
        return Image.open(path)

    def find(self, name: str, timeout: float = 10.0) -> tuple[float, tuple[int, int]] | None:
        """Poll for the template. Returns (confidence, logical_xy), or None."""
        template = self.load(name)
        scale = self.scale()
        deadline = time.time() + timeout
        while True:
            confidence, (x, y) = match(self.grab(), template)
            if confidence >= self.confidence:
                return confidence, (round(x / scale), round(y / scale))
            if time.time() >= deadline:
                return None
            time.sleep(0.3)

    def require(self, name: str, timeout: float = 10.0) -> tuple[int, int]:
        """find(), but a miss is fatal and leaves evidence behind."""
        hit = self.find(name, timeout=timeout)
        if hit is None:
            self._dump(name)
            raise TemplateNotFound(
                f"could not find {name} on screen within {timeout}s "
                f"(screenshot of what was actually there: {self.debug_dir})"
            )
        return hit[1]

    def click(self, name: str, timeout: float = 10.0, settle: float = 1.0) -> None:
        x, y = self.require(name, timeout=timeout)
        pyautogui.moveTo(x, y, duration=0.2)
        pyautogui.click()
        time.sleep(settle)

    def _dump(self, name: str) -> None:
        self.debug_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%H%M%S")
        self.grab().save(self.debug_dir / f"miss_{Path(name).stem}_{stamp}.png")
