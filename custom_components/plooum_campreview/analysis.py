"""Picture analysis: what a camera picture shows, independently of Home Assistant.

A picture is reduced to a small signature: the brightness gradient (edges) of a SIG_W x SIG_H
gray copy, blurred a little and scaled to a unit norm. Edges hardly change with the light of the
day, nor in a gray infrared night view, whereas a turn of a few degrees moves all of them: two
signatures compare by a dot product (1 = same picture, ~0 = unrelated), whatever their brightness.
Same method as the floorplan card of HA-Plooum-Cards (pictureEdges()), so both agree.

Also tells whether a picture carries no information (black, or a uniform frame such as the gray
or blue "no signal" screen of some cameras), and whether it is a color or an infrared picture.
"""

from __future__ import annotations

from array import array
import base64
from dataclasses import dataclass
import io
import math

from PIL import Image, ImageStat

SIG_W = 64
SIG_H = 36
# Infrared (night) pictures are gray: their mean saturation (0-255) stays under this.
IR_SATURATION = 12
MODE_COLOR = "color"
MODE_IR = "ir"


@dataclass
class Frame:
    """What a picture shows (see analyze())."""

    signature: array  # 2 * SIG_W * SIG_H floats ('f'), unit norm (all zero for a flat picture)
    brightness: float  # 98th percentile of the luminance, 0-255: under the black level, black
    contrast: float  # standard deviation of the luminance, 0-255: very low, a uniform frame
    mode: str  # MODE_COLOR or MODE_IR
    width: int
    height: int


def analyze(content: bytes) -> Frame:
    """Analyze a JPEG/PNG picture. Raises ValueError when it can't be decoded."""
    try:
        with Image.open(io.BytesIO(content)) as img:
            width, height = img.size
            img.draft("RGB", (SIG_W * 4, SIG_H * 4))  # fast JPEG decode at a reduced size
            rgb = img.convert("RGB")
    except Exception as err:  # noqa: BLE001 - Pillow raises many kinds of errors
        raise ValueError(f"Unreadable picture: {err}") from err
    small = rgb.resize((SIG_W, SIG_H), Image.Resampling.BOX)
    gray = small.convert("L")
    hist = gray.histogram()
    brightness = _percentile(hist, 0.98)
    contrast = ImageStat.Stat(gray).stddev[0]
    saturation = ImageStat.Stat(small.convert("HSV")).mean[1]
    return Frame(
        signature=_edges(gray.tobytes()),
        brightness=brightness,
        contrast=contrast,
        mode=MODE_IR if saturation < IR_SATURATION else MODE_COLOR,
        width=width,
        height=height,
    )


def _percentile(hist: list[int], q: float) -> float:
    total = sum(hist)
    if not total:
        return 0.0
    limit = q * total
    seen = 0
    for level, count in enumerate(hist):
        seen += count
        if seen >= limit:
            return float(level)
    return 255.0


def _edges(gray: bytes) -> array:
    """Unit-norm, blurred gradient (x, y per pixel) of a SIG_W x SIG_H gray picture."""
    w, h = SIG_W, SIG_H
    grad = [0.0] * (2 * w * h)
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            i = y * w + x
            grad[2 * i] = gray[i + 1] - gray[i - 1]
            grad[2 * i + 1] = gray[i + w] - gray[i - w]
    edges = array("f", bytes(4 * 2 * w * h))
    norm = 0.0
    for y in range(h):
        for x in range(w):
            for k in (0, 1):
                total = 0.0
                for dy in (-1, 0, 1):
                    yy = min(max(y + dy, 0), h - 1)
                    for dx in (-1, 0, 1):
                        xx = min(max(x + dx, 0), w - 1)
                        total += grad[2 * (yy * w + xx) + k]
                edges[2 * (y * w + x) + k] = total
                norm += total * total
    norm = math.sqrt(norm)
    if norm:
        for i in range(len(edges)):
            edges[i] /= norm
    return edges


def similarity(a: array, b: array) -> float:
    """How much two signatures look alike: 1 the same picture, ~0 unrelated."""
    if len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))


def encode_signature(sig: array) -> str:
    return base64.b64encode(sig.tobytes()).decode("ascii")


def decode_signature(text: str) -> array:
    sig = array("f")
    sig.frombytes(base64.b64decode(text))
    return sig
