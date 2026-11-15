"""Whether a new camera picture becomes the preview: the filter, independently of Home Assistant.

A picture is rejected when it carries no information (black, uniform) or when it no longer shows
what the camera usually shows (the camera turned: PTZ, a knock). What the camera usually shows is
kept as reference signatures, one per mode (color by day, infrared by night), so that the night
view is never compared with the day view only.

Safeguards against rejecting every picture forever (see decide()):
1. One reference per mode, the first picture of a new mode compared leniently: the first infrared
   night does not look "moved".
2. References follow slow changes (seasons, a parked car): a confident match replaces its mode's
   reference.
3. A new stable view is adopted: when the last `rebase_count` rejected pictures look alike and
   span at least `rebase_minutes`, the camera really points somewhere else now; the references are
   reset on the latest one (event "view changed").
4. Last resort: after `max_age_hours` without any accepted picture while informative ones keep
   coming (not black), the latest one is accepted and becomes the reference.
5. A forced update always accepts the picture and makes it the only reference.
Black and uniform pictures never count towards 3 and 4: a camera at night without infrared keeps
its last daylight preview, which is what a preview should show.
"""

from __future__ import annotations

from array import array
from dataclasses import dataclass, field
from typing import Any

from .analysis import Frame, decode_signature, encode_signature, similarity

ACCEPTED = "accepted"  # matches the references
FIRST = "first"  # first picture ever
NEW_MODE = "new_mode"  # first picture of a mode (first infrared night), leniently matched
FORCED = "forced"  # forced update
REBASED = "rebased"  # a new stable view (safeguard 3)
STALE = "stale"  # nothing accepted for too long (safeguard 4)
BLACK = "black"
UNIFORM = "uniform"
MOVED = "moved"
ACCEPTING = {ACCEPTED, FIRST, NEW_MODE, FORCED, REBASED, STALE}
NEW_VIEW = {FIRST, FORCED, REBASED, STALE}  # the references are reset


@dataclass
class Settings:
    black_level: float = 25  # 98th percentile of the luminance under which a picture is black
    min_contrast: float = 3  # luminance standard deviation under which a picture is uniform
    match_threshold: float = 0.5  # similarity from which a picture shows the same view
    confident_threshold: float = 0.75  # similarity from which it refreshes its mode's reference
    lenient_threshold: float = 0.3  # similarity accepted for the first picture of a mode
    rebase_count: int = 3  # rejected pictures alike in a row that make a new view (0: never)
    rebase_minutes: float = 10  # ...spanning at least this long
    max_age_hours: float = 12  # accept anyway after this long (0: never)


@dataclass
class Pending:
    """A picture rejected as moved, kept to detect a new stable view."""

    time: float
    signature: array
    mode: str


@dataclass
class FilterState:
    references: dict[str, array] = field(default_factory=dict)  # mode -> signature
    pending: list[Pending] = field(default_factory=list)
    last_accepted: float | None = None  # time (s)
    view_since: float | None = None  # time the references were last reset
    moved_since: float | None = None  # first rejection as moved since the last accepted picture

    def as_dict(self) -> dict[str, Any]:
        return {
            "references": {m: encode_signature(s) for m, s in self.references.items()},
            "pending": [
                {"time": p.time, "signature": encode_signature(p.signature), "mode": p.mode}
                for p in self.pending
            ],
            "last_accepted": self.last_accepted,
            "view_since": self.view_since,
            "moved_since": self.moved_since,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> FilterState:
        if not data:
            return cls()
        return cls(
            references={m: decode_signature(s) for m, s in data.get("references", {}).items()},
            pending=[
                Pending(p["time"], decode_signature(p["signature"]), p["mode"])
                for p in data.get("pending", [])
            ],
            last_accepted=data.get("last_accepted"),
            view_since=data.get("view_since"),
            moved_since=data.get("moved_since"),
        )


@dataclass
class Verdict:
    reason: str
    score: float | None = None  # similarity with the best matching reference

    @property
    def accepted(self) -> bool:
        return self.reason in ACCEPTING

    @property
    def new_view(self) -> bool:
        return self.reason in NEW_VIEW


def decide(state: FilterState, frame: Frame, now: float, s: Settings, force: bool = False) -> Verdict:
    """Decide on a new picture and update `state` accordingly."""
    if force:
        return _reset(state, frame, now, FORCED)
    if frame.brightness < s.black_level:
        return Verdict(BLACK)
    if frame.contrast < s.min_contrast:
        return Verdict(UNIFORM)
    if not state.references:
        return _reset(state, frame, now, FIRST)

    score = max(similarity(ref, frame.signature) for ref in state.references.values())
    own = state.references.get(frame.mode)
    if own is not None and score >= s.match_threshold:
        if similarity(own, frame.signature) >= s.confident_threshold:
            state.references[frame.mode] = frame.signature  # safeguard 2
        return _accept(state, now, Verdict(ACCEPTED, score))
    if own is None and score >= s.lenient_threshold:
        state.references[frame.mode] = frame.signature  # safeguard 1
        return _accept(state, now, Verdict(NEW_MODE, score))

    # Rejected as moved.
    if state.moved_since is None:
        state.moved_since = now
    state.pending.append(Pending(now, frame.signature, frame.mode))
    keep = max(s.rebase_count, 1)
    state.pending = state.pending[-keep:]
    if _stable(state.pending, s, now):
        return _reset(state, frame, now, REBASED, score)  # safeguard 3
    since = state.last_accepted if state.last_accepted is not None else state.moved_since
    if s.max_age_hours > 0 and now - since >= s.max_age_hours * 3600:
        return _reset(state, frame, now, STALE, score)  # safeguard 4
    return Verdict(MOVED, score)


def _stable(pending: list[Pending], s: Settings, now: float) -> bool:
    """Whether the last rebase_count rejected pictures show one same view for long enough."""
    if s.rebase_count <= 0 or len(pending) < s.rebase_count:
        return False
    last = pending[-s.rebase_count :]
    if now - last[0].time < s.rebase_minutes * 60:
        return False
    return all(
        similarity(a.signature, b.signature) >= s.match_threshold
        for i, a in enumerate(last)
        for b in last[i + 1 :]
    )


def _accept(state: FilterState, now: float, verdict: Verdict) -> Verdict:
    state.last_accepted = now
    state.pending = []
    state.moved_since = None
    return verdict


def _reset(state: FilterState, frame: Frame, now: float, reason: str, score: float | None = None) -> Verdict:
    state.references = {frame.mode: frame.signature}
    state.view_since = now
    return _accept(state, now, Verdict(reason, score))
