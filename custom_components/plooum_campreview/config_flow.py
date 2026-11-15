"""Config flow: one entry per camera; options: capture interval and filter settings."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
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
    MIN_INTERVAL,
)
from .decision import Settings


def _number(lo: float, hi: float, step: float, unit: str | None = None) -> selector.NumberSelector:
    config = selector.NumberSelectorConfig(min=lo, max=hi, step=step, mode=selector.NumberSelectorMode.BOX)
    if unit:
        config["unit_of_measurement"] = unit
    return selector.NumberSelector(config)


def _options_schema(values: dict[str, Any]) -> vol.Schema:
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
    return vol.Schema({vol.Required(key, default=values.get(key, default)): sel for key, default, sel in fields})


class CamPreviewConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            camera = user_input[CONF_CAMERA]
            await self.async_set_unique_id(camera)
            self._abort_if_unique_id_configured()
            st = self.hass.states.get(camera)
            title = st.name if st else camera
            return self.async_create_entry(title=title, data={CONF_CAMERA: camera})
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_CAMERA): selector.EntitySelector(selector.EntitySelectorConfig(domain="camera"))}
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return CamPreviewOptionsFlow()


class CamPreviewOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(step_id="init", data_schema=_options_schema(dict(self.config_entry.options)))
