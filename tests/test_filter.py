"""Tests of the picture filter (analysis.py, decision.py), without Home Assistant.

Run: python -m unittest discover tests   (needs Pillow)

Pictures are synthetic scenes: a crop of a large, detailed landscape. A camera that turns is a
crop shifted sideways; dusk a darker copy; an infrared night a gray copy with other contrasts.
"""

from __future__ import annotations

import importlib.util
import io
from pathlib import Path
import random
import sys
import types
import unittest

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

# Load analysis.py and decision.py as a package without its __init__ (which needs Home Assistant).
PKG = "campreview_filter"
SRC = Path(__file__).resolve().parents[1] / "custom_components" / "plooum_campreview"
sys.modules[PKG] = types.ModuleType(PKG)
sys.modules[PKG].__path__ = [str(SRC)]
for name in ("analysis", "decision"):
    spec = importlib.util.spec_from_file_location(f"{PKG}.{name}", SRC / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
analysis = sys.modules[f"{PKG}.analysis"]
decision = sys.modules[f"{PKG}.decision"]

W, H = 640, 360


def _world(seed: int = 1) -> Image.Image:
    """A wide landscape: sky, ground, houses, trees, a road."""
    rnd = random.Random(seed)
    img = Image.new("RGB", (3 * W, H), (120, 170, 230))
    d = ImageDraw.Draw(img)
    d.rectangle([0, int(H * 0.6), 3 * W, H], fill=(70, 140, 70))
    d.polygon([(0, H), (3 * W, int(H * 0.75)), (3 * W, H)], fill=(100, 100, 105))
    for _ in range(40):
        x = rnd.randint(0, 3 * W)
        y = rnd.randint(int(H * 0.3), int(H * 0.65))
        w = rnd.randint(30, 120)
        h = rnd.randint(30, 140)
        color = tuple(rnd.randint(60, 240) for _ in range(3))
        d.rectangle([x, y - h, x + w, y], fill=color, outline=(30, 30, 30), width=3)
        for k in range(rnd.randint(1, 4)):
            wx = x + 8 + k * 22
            d.rectangle([wx, y - h + 10, wx + 12, y - h + 28], fill=(40, 60, 90))
    for _ in range(30):
        x = rnd.randint(0, 3 * W)
        y = rnd.randint(int(H * 0.55), int(H * 0.8))
        r = rnd.randint(12, 35)
        d.ellipse([x - r, y - 2 * r, x + r, y], fill=(30, rnd.randint(90, 130), 40))
        d.rectangle([x - 3, y, x + 3, y + 20], fill=(90, 60, 30))
    return img


WORLD = _world()


def view(offset: int = W, world: Image.Image = WORLD) -> Image.Image:
    """What the camera sees when it points at `offset` (px of the landscape)."""
    return world.crop((offset, 0, offset + W, H))


def jpeg(img: Image.Image, noise: float = 0, seed: int = 0) -> bytes:
    if noise:
        rnd = random.Random(seed)
        grain = Image.effect_noise(img.size, noise * 100).convert("RGB")
        img = Image.blend(img, grain, noise * (0.5 + rnd.random() * 0.5))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=80)
    return buf.getvalue()


def dusk(img: Image.Image) -> Image.Image:
    return ImageEnhance.Brightness(img, ).enhance(0.35)


def infrared(img: Image.Image) -> Image.Image:
    """A night infrared view: gray, vegetation bright, sky dark, a bit blurred and noisy."""
    r, g, b = img.split()
    gray = Image.merge("RGB", (g, g, g)).convert("L")  # foliage reflects IR
    gray = ImageOps.autocontrast(gray, cutoff=2).filter(ImageFilter.GaussianBlur(1.2))
    return ImageEnhance.Brightness(gray).enhance(0.8).convert("RGB")


def frame(img: Image.Image, **kw) -> analysis.Frame:
    return analysis.analyze(jpeg(img, **kw))


MIN = 60
S = decision.Settings()


class AnalysisTest(unittest.TestCase):
    def test_same_view_matches_whatever_the_light(self):
        day = frame(view())
        for other in (frame(view(), noise=0.2, seed=3), frame(dusk(view())), frame(infrared(view()))):
            self.assertGreater(analysis.similarity(day.signature, other.signature), S.match_threshold)

    def test_turned_camera_does_not_match(self):
        day = frame(view())
        for shift in (40, -60, 200, 640):
            turned = frame(view(W + shift))
            self.assertLess(analysis.similarity(day.signature, turned.signature), S.match_threshold, shift)

    def test_black_uniform_and_modes(self):
        self.assertLess(frame(Image.new("RGB", (W, H), (8, 8, 8)), noise=0.05).brightness, S.black_level)
        self.assertLess(frame(Image.new("RGB", (W, H), (40, 60, 160))).contrast, S.min_contrast)
        self.assertEqual(frame(view()).mode, analysis.MODE_COLOR)
        self.assertEqual(frame(infrared(view())).mode, analysis.MODE_IR)

    def test_unreadable(self):
        with self.assertRaises(ValueError):
            analysis.analyze(b"not a picture")

    def test_signature_round_trip(self):
        sig = frame(view()).signature
        self.assertEqual(analysis.decode_signature(analysis.encode_signature(sig)), sig)


class DecisionTest(unittest.TestCase):
    def setUp(self):
        self.state = decision.FilterState()
        self.t = 1_000_000.0

    def run_(self, img: Image.Image, minutes: float = 5, force: bool = False, **kw) -> str:
        self.t += minutes * MIN
        return decide_reason(self.state, frame(img, **kw), self.t, force)

    def test_day_night_cycle_never_rejects(self):
        self.assertEqual(self.run_(view()), decision.FIRST)
        seen = []
        for day in range(3):
            seen.append(self.run_(view(), noise=0.1, seed=day))
            seen.append(self.run_(dusk(view()), seed=day))
            seen.append(self.run_(infrared(view()), noise=0.1, seed=day))
            seen.append(self.run_(infrared(view()), seed=day + 10))
            seen.append(self.run_(view(), seed=day + 20))
        self.assertTrue(all(r in decision.ACCEPTING for r in seen), seen)
        self.assertEqual(seen[2], decision.NEW_MODE)  # first infrared night
        self.assertEqual(set(self.state.references), {"color", "ir"})

    def test_black_and_uniform_are_ignored_but_never_rebase(self):
        self.run_(view())
        for _ in range(12 * 24):  # a whole day of black pictures (5 min)
            self.assertEqual(self.run_(Image.new("RGB", (W, H), (5, 5, 5))), decision.BLACK)
        self.assertEqual(self.run_(Image.new("RGB", (W, H), (0, 0, 255))), decision.UNIFORM)
        self.assertEqual(self.run_(view()), decision.ACCEPTED)

    def test_turned_camera_is_ignored_then_its_new_view_adopted(self):
        self.run_(view())
        self.assertEqual(self.run_(view(W + 200)), decision.MOVED)
        self.assertEqual(self.run_(view(W + 200), seed=1, noise=0.1), decision.MOVED)
        self.assertEqual(self.run_(view(W + 200), seed=2, noise=0.1), decision.REBASED)  # 10 min, 3 alike
        self.assertEqual(self.run_(view(W + 200)), decision.ACCEPTED)
        self.assertEqual(self.run_(view()), decision.MOVED)  # the old view is now the odd one

    def test_short_turn_comes_back(self):
        self.run_(view())
        self.assertEqual(self.run_(view(W + 300)), decision.MOVED)  # PTZ looked elsewhere
        self.assertEqual(self.run_(view()), decision.ACCEPTED)
        self.assertEqual(self.state.pending, [])

    def test_patrolling_camera_never_rebases_until_max_age(self):
        self.run_(view())
        reasons = [self.run_(view(W + 150 * (1 + k % 4)), minutes=30) for k in range(23)]
        self.assertTrue(all(r == decision.MOVED for r in reasons), reasons)  # 11.5 h
        self.assertEqual(self.run_(view(W + 150), minutes=30), decision.STALE)  # 12 h: safeguard 4

    def test_forced_update(self):
        self.run_(view())
        self.assertEqual(self.run_(view(W + 400), force=True), decision.FORCED)
        self.assertEqual(self.run_(view(W + 400)), decision.ACCEPTED)
        self.assertEqual(self.run_(Image.new("RGB", (W, H)), force=True), decision.FORCED)

    def test_state_round_trip(self):
        self.run_(view())
        self.run_(view(W + 200))
        again = decision.FilterState.from_dict(self.state.as_dict())
        self.assertEqual(again.as_dict(), self.state.as_dict())


def decide_reason(state, fr, t, force):
    return decision.decide(state, fr, t, S, force=force).reason


if __name__ == "__main__":
    unittest.main()
