"""The preview of one camera: captures a picture regularly, filters it, keeps the last good one."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
import logging
from pathlib import Path
import time
from typing import Any

from homeassistant.components.camera import async_get_image
from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .analysis import Frame, analyze
from .const import (
    CAPTURE_TIMEOUT,
    CONF_BLACK_LEVEL,
    CONF_CAMERA,
    CONF_INTERVAL,
    CONF_MATCH_THRESHOLD,
    CONF_MAX_AGE_HOURS,
    CONF_MIN_CONTRAST,
    CONF_REBASE_COUNT,
    CONF_REBASE_MINUTES,
    DEFAULT_INTERVAL,
    DOMAIN,
    EVENT_VIEW_CHANGED,
    STATUS_ERROR,
    STATUS_OK,
    STATUS_UNAVAILABLE,
    STATUS_WAITING,
    STORAGE_VERSION,
)
from .decision import FIRST, FilterState, Settings, Verdict, decide

_LOGGER = logging.getLogger(__name__)

SETTING_KEYS = {
    CONF_BLACK_LEVEL: "black_level",
    CONF_MIN_CONTRAST: "min_contrast",
    CONF_MATCH_THRESHOLD: "match_threshold",
    CONF_REBASE_COUNT: "rebase_count",
    CONF_REBASE_MINUTES: "rebase_minutes",
    CONF_MAX_AGE_HOURS: "max_age_hours",
}


def settings_from(options: dict[str, Any]) -> Settings:
    s = Settings()
    for key, attr in SETTING_KEYS.items():
        if options.get(key) is not None:
            setattr(s, attr, type(getattr(s, attr))(options[key]))
    return s


def _store(hass: HomeAssistant, key: str) -> Store[dict[str, Any]]:
    return Store(hass, STORAGE_VERSION, f"{DOMAIN}.{key}")


def _image_path(hass: HomeAssistant, key: str) -> Path:
    return Path(hass.config.path(".storage", DOMAIN, f"{key}.img"))


async def async_remove_preview(hass: HomeAssistant, key: str) -> None:
    """Forget what a camera's preview keeps (a removed camera)."""
    await _store(hass, key).async_remove()
    await hass.async_add_executor_job(_image_path(hass, key).unlink, True)


def _iso(ts: float | None) -> str | None:
    return dt_util.utc_from_timestamp(ts).isoformat() if ts is not None else None


class PreviewManager:
    """Captures, filters and keeps the preview of one camera (one subentry of the config entry)."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, subentry: ConfigSubentry) -> None:
        self.hass = hass
        self.entry = entry
        self.key = subentry.subentry_id
        self.title = subentry.title
        options = dict(subentry.data)
        self.camera: str = options[CONF_CAMERA]
        self.interval: int = int(options.get(CONF_INTERVAL, DEFAULT_INTERVAL))
        self.settings = settings_from(options)
        self._store = _store(hass, self.key)
        self._image_path = _image_path(hass, self.key)
        self._lock = asyncio.Lock()
        self._listeners: list[Callable[[], None]] = []
        self._unsubs: list[CALLBACK_TYPE] = []

        self.filter = FilterState()
        self.image: bytes | None = None
        self.content_type = "image/jpeg"
        self.image_time: datetime | None = None
        self.status = STATUS_WAITING
        self.last_attempt: datetime | None = None
        self.last_verdict: Verdict | None = None
        self.last_frame: Frame | None = None
        self.rejections = 0  # in a row
        self.error: str | None = None

    # --- lifecycle

    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        self.filter = FilterState.from_dict(data.get("filter"))
        self.content_type = data.get("content_type", self.content_type)
        if data.get("image_time"):
            self.image_time = dt_util.parse_datetime(data["image_time"])
        self.image = await self.hass.async_add_executor_job(self._read_image)
        if self.image is None:
            self.image_time = None
        self.status = data.get("status", STATUS_WAITING)
        self.rejections = data.get("rejections", 0)

    @callback
    def async_start(self) -> None:
        """Capture every `interval`, the first time once Home Assistant has started (cameras ready)."""
        self._unsubs.append(
            async_track_time_interval(
                self.hass, self._async_tick, timedelta(seconds=self.interval), name=f"{DOMAIN} {self.camera}"
            )
        )

        @callback
        def first(_hass: HomeAssistant) -> None:
            self.entry.async_create_background_task(self.hass, self.async_update(), f"{DOMAIN} first capture")

        self._unsubs.append(async_at_started(self.hass, first))

    @callback
    def async_stop(self) -> None:
        while self._unsubs:
            self._unsubs.pop()()

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> CALLBACK_TYPE:
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    async def _async_tick(self, _now: datetime) -> None:
        await self.async_update()

    # --- capture

    async def async_update(self, force: bool = False) -> None:
        """Capture a picture and decide whether it becomes the preview (always when forced)."""
        async with self._lock:
            await self._async_capture(force)
            self._notify()
            await self._store.async_save(self._data())

    async def _async_capture(self, force: bool) -> None:
        self.last_attempt = dt_util.utcnow()
        st = self.hass.states.get(self.camera)
        if st is None or st.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self.status = STATUS_UNAVAILABLE
            self.error = None if st else "Camera entity not found"
            return
        try:
            picture = await async_get_image(self.hass, self.camera, timeout=CAPTURE_TIMEOUT)
        except HomeAssistantError as err:
            self.status = STATUS_UNAVAILABLE
            self.error = str(err)
            _LOGGER.debug("%s: no picture: %s", self.camera, err)
            return
        try:
            frame = await self.hass.async_add_executor_job(analyze, picture.content)
        except ValueError as err:
            self.status = STATUS_ERROR
            self.error = str(err)
            self.rejections += 1
            return
        self.error = None
        self.last_frame = frame
        now = time.time()
        verdict = decide(self.filter, frame, now, self.settings, force=force)
        self.last_verdict = verdict
        if not verdict.accepted:
            self.status = verdict.reason
            self.rejections += 1
            _LOGGER.debug("%s: picture rejected (%s, score %s)", self.camera, verdict.reason, verdict.score)
            return
        self.status = STATUS_OK
        self.rejections = 0
        self.image = picture.content
        self.content_type = picture.content_type or "image/jpeg"
        self.image_time = dt_util.utc_from_timestamp(now)
        await self.hass.async_add_executor_job(self._write_image, picture.content)
        if verdict.new_view and verdict.reason != FIRST:
            _LOGGER.info("%s: new view adopted (%s)", self.camera, verdict.reason)
            self.hass.bus.async_fire(
                EVENT_VIEW_CHANGED,
                {"camera_entity": self.camera, "reason": verdict.reason, "score": verdict.score},
            )

    # --- state shown by the entities

    @property
    def attributes(self) -> dict[str, Any]:
        v, f, st = self.last_verdict, self.last_frame, self.filter
        return {
            "camera_entity": self.camera,
            "status": self.status,
            "moved": self.status == "moved",
            "last_reason": v.reason if v else None,
            "score": round(v.score, 3) if v and v.score is not None else None,
            "mode": f.mode if f else None,
            "brightness": round(f.brightness) if f else None,
            "contrast": round(f.contrast, 1) if f else None,
            "rejections": self.rejections,
            "last_attempt": self.last_attempt.isoformat() if self.last_attempt else None,
            "view_since": _iso(st.view_since),
            "moved_since": _iso(st.moved_since),
            "references": sorted(st.references),
            "error": self.error,
        }

    @callback
    def _notify(self) -> None:
        for listener in list(self._listeners):
            listener()

    # --- persistence

    def _data(self) -> dict[str, Any]:
        return {
            "filter": self.filter.as_dict(),
            "content_type": self.content_type,
            "image_time": self.image_time.isoformat() if self.image_time else None,
            "status": self.status,
            "rejections": self.rejections,
        }

    def _read_image(self) -> bytes | None:
        try:
            return self._image_path.read_bytes()
        except OSError:
            return None

    def _write_image(self, content: bytes) -> None:
        self._image_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._image_path.with_suffix(".tmp")
        tmp.write_bytes(content)
        tmp.replace(self._image_path)
