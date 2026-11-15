"""Plooum CamPreview: a regular, filtered preview picture of a camera.

Each config entry follows one camera: every `interval` it captures a picture, ignores it when it is
black, uniform or when the camera turned (see decision.py), and otherwise keeps it as the preview,
shown by an image entity (image.<camera>_preview) and kept across restarts. A button and the
`plooum_campreview.update` action force an update.
"""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.service import async_extract_entity_ids
from homeassistant.helpers.typing import ConfigType

from .const import ATTR_FORCE, DOMAIN, SERVICE_UPDATE
from .manager import PreviewManager

PLATFORMS = [Platform.IMAGE, Platform.SENSOR, Platform.BUTTON]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type CamPreviewConfigEntry = ConfigEntry[PreviewManager]

UPDATE_SCHEMA = cv.make_entity_service_schema({vol.Optional(ATTR_FORCE, default=False): cv.boolean})


async def _entity_ids(hass: HomeAssistant, call: ServiceCall) -> set[str]:
    """Entities targeted by a call (entities, devices, areas...)."""
    try:
        return await async_extract_entity_ids(call)
    except TypeError:  # Home Assistant before 2026: hass first
        return await async_extract_entity_ids(hass, call)  # type: ignore[arg-type]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async def update(call: ServiceCall) -> None:
        registry = er.async_get(hass)
        managers = []
        for entity_id in sorted(await _entity_ids(hass, call)):
            ent = registry.async_get(entity_id)
            entry = ent and ent.config_entry_id and hass.config_entries.async_get_entry(ent.config_entry_id)
            if not entry or entry.domain != DOMAIN or not hasattr(entry, "runtime_data"):
                continue  # a device or an area also holds other entities
            if entry.runtime_data not in managers:
                managers.append(entry.runtime_data)
        if not managers:
            raise ServiceValidationError(f"No {DOMAIN} preview targeted")
        for manager in managers:
            await manager.async_update(force=call.data[ATTR_FORCE])

    hass.services.async_register(DOMAIN, SERVICE_UPDATE, update, schema=UPDATE_SCHEMA)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: CamPreviewConfigEntry) -> bool:
    manager = PreviewManager(hass, entry)
    await manager.async_load()
    entry.runtime_data = manager
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    entry.async_on_unload(manager.async_stop)
    manager.async_start()
    return True


async def _async_reload(hass: HomeAssistant, entry: CamPreviewConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: CamPreviewConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await PreviewManager(hass, entry).async_remove()
