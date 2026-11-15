"""Config flow: one entry, one subentry per camera ("Add camera"), each with its own settings."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryData,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector

from .const import (
    CONF_BLACK_LEVEL,
    CONF_CAMERA,
    CONF_CAMERAS,
    CONF_INTERVAL,
    CONF_MATCH_THRESHOLD,
    CONF_MAX_AGE_HOURS,
    CONF_MIN_CONTRAST,
    CONF_REBASE_COUNT,
    CONF_REBASE_MINUTES,
    DEFAULT_INTERVAL,
    DOMAIN,
    ENTRY_TITLE,
    MIN_INTERVAL,
    SUBENTRY_CAMERA,
)
from .decision import Settings


def _number(lo: float, hi: float, step: float, unit: str | None = None) -> selector.NumberSelector:
    config = selector.NumberSelectorConfig(min=lo, max=hi, step=step, mode=selector.NumberSelectorMode.BOX)
    if unit:
        config["unit_of_measurement"] = unit
    return selector.NumberSelector(config)


def _settings_fields(values: dict[str, Any]) -> dict[Any, Any]:
    """The capture and filter settings of a camera, filled with `values` or the defaults."""
    d = Settings()
    fields = [
        (CONF_INTERVAL, DEFAULT_INTERVAL, _number(MIN_INTERVAL, 86400, 1, "s")),
        (CONF_BLACK_LEVEL, d.black_level, _number(0, 255, 1)),
        (CONF_MIN_CONTRAST, d.min_contrast, _number(0, 100, 0.5)),
        (CONF_MATCH_THRESHOLD, d.match_threshold, _number(0, 1, 0.05)),
        (CONF_REBASE_COUNT, d.rebase_count, _number(0, 20, 1)),
        (CONF_REBASE_MINUTES, d.rebase_minutes, _number(0, 1440, 1, "min")),
        (CONF_MAX_AGE_HOURS, d.max_age_hours, _number(0, 720, 0.5, "h")),
    ]
    return {vol.Required(key, default=values.get(key, default)): sel for key, default, sel in fields}


def _camera_title(hass: HomeAssistant, camera: str) -> str:
    st = hass.states.get(camera)
    return st.name if st else camera


def _configured(entry: ConfigEntry) -> set[str]:
    return {s.data.get(CONF_CAMERA) for s in entry.subentries.values()}


class CamPreviewConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 2

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """The cameras to start with (default settings); more are added with "Add camera"."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if user_input is not None:
            subentries: list[ConfigSubentryData] = [
                {
                    "data": {CONF_CAMERA: camera},
                    "subentry_type": SUBENTRY_CAMERA,
                    "title": _camera_title(self.hass, camera),
                    "unique_id": camera,
                }
                for camera in dict.fromkeys(user_input.get(CONF_CAMERAS, []))
            ]
            return self.async_create_entry(title=ENTRY_TITLE, data={}, subentries=subentries)
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_CAMERAS, default=[]): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="camera", multiple=True)
                    )
                }
            ),
        )

    @classmethod
    @callback
    def async_get_supported_subentry_types(cls, config_entry: ConfigEntry) -> dict[str, type[ConfigSubentryFlow]]:
        return {SUBENTRY_CAMERA: CameraSubentryFlow}


class CameraSubentryFlow(ConfigSubentryFlow):
    """Add a camera, or change its settings."""

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        entry = self._get_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            camera = user_input[CONF_CAMERA]
            if camera in _configured(entry):
                errors[CONF_CAMERA] = "already_configured"
            else:
                return self.async_create_entry(
                    title=_camera_title(self.hass, camera), data=user_input, unique_id=camera
                )
        exclude = sorted(c for c in _configured(entry) if c)
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CAMERA): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="camera", exclude_entities=exclude)
                    ),
                    **_settings_fields(user_input or {}),
                }
            ),
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        subentry = self._get_reconfigure_subentry()
        if user_input is not None:
            return self.async_update_and_abort(
                self._get_entry(), subentry, data={**subentry.data, **user_input}
            )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(_settings_fields(dict(subentry.data))),
            description_placeholders={"camera": subentry.title},
        )
