"""Plooum CamPreview: a regular, filtered preview picture of cameras.

One config entry, one subentry per camera ("Add camera"). For each camera, every `interval` it
captures a picture, ignores it when it is black, uniform or when the camera turned (see
decision.py), and otherwise keeps it as the preview, shown by an image entity
(image.<camera>_preview) and kept across restarts. A button and the `plooum_campreview.update`
action force an update.
"""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, device_registry as dr, entity_registry as er
from homeassistant.helpers.service import async_extract_entity_ids
from homeassistant.helpers.typing import ConfigType

from .const import ATTR_FORCE, CONF_CAMERA, DOMAIN, ENTRY_TITLE, SERVICE_UPDATE, SUBENTRY_CAMERA
from .manager import PreviewManager, async_remove_preview

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.IMAGE, Platform.SENSOR, Platform.BUTTON]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

# Subentry id -> the preview of that camera.
type CamPreviewConfigEntry = ConfigEntry[dict[str, PreviewManager]]

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
        managers: list[PreviewManager] = []
        for entity_id in sorted(await _entity_ids(hass, call)):
            ent = registry.async_get(entity_id)
            entry = ent and ent.config_entry_id and hass.config_entries.async_get_entry(ent.config_entry_id)
            if not entry or entry.domain != DOMAIN or not isinstance(getattr(entry, "runtime_data", None), dict):
                continue  # a device or an area also holds other entities
            manager = entry.runtime_data.get(ent.config_subentry_id)
            if manager and manager not in managers:
                managers.append(manager)
        if not managers:
            raise ServiceValidationError(f"No {DOMAIN} preview targeted")
        for manager in managers:
            await manager.async_update(force=call.data[ATTR_FORCE])

    hass.services.async_register(DOMAIN, SERVICE_UPDATE, update, schema=UPDATE_SCHEMA)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: CamPreviewConfigEntry) -> bool:
    managers: dict[str, PreviewManager] = {}
    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_CAMERA:
            continue
        manager = PreviewManager(hass, entry, subentry)
        await manager.async_load()
        managers[subentry.subentry_id] = manager
    entry.runtime_data = managers
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_updated))
    for manager in managers.values():
        entry.async_on_unload(manager.async_stop)
        manager.async_start()
    return True


async def _async_updated(hass: HomeAssistant, entry: CamPreviewConfigEntry) -> None:
    """A camera was added, changed or removed: forget the removed ones' pictures, reload."""
    for key in set(entry.runtime_data) - set(entry.subentries):
        await async_remove_preview(hass, key)
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: CamPreviewConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    for key in entry.subentries:
        await async_remove_preview(hass, key)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Version 1 (V0.1.0): one entry per camera, settings in its options. Version 2: the camera
    becomes a subentry with the entry's id, so that its stored pictures and entities are kept."""
    if entry.version > 2:
        return False
    if entry.version == 1:
        data = {**entry.data, **entry.options}
        camera = data.get(CONF_CAMERA)
        title = entry.title
        hass.config_entries.async_update_entry(entry, title=ENTRY_TITLE, data={}, options={}, version=2)
        if camera:
            hass.config_entries.async_add_subentry(
                entry,
                ConfigSubentry(
                    data=data,
                    subentry_id=entry.entry_id,
                    subentry_type=SUBENTRY_CAMERA,
                    title=title,
                    unique_id=camera,
                ),
            )
            # Its device and entities now belong to the camera's subentry.
            devices = dr.async_get(hass)
            for device in dr.async_entries_for_config_entry(devices, entry.entry_id):
                try:
                    devices.async_update_device(device.id, new_config_subentry_id=entry.entry_id)
                except TypeError:  # Home Assistant before 2026: devices of several subentries
                    devices.async_update_device(
                        device.id, add_config_entry_id=entry.entry_id, add_config_subentry_id=entry.entry_id
                    )
                    devices.async_update_device(
                        device.id, remove_config_entry_id=entry.entry_id, remove_config_subentry_id=None
                    )
            entities = er.async_get(hass)
            for ent in er.async_entries_for_config_entry(entities, entry.entry_id):
                entities.async_update_entity(ent.entity_id, config_subentry_id=entry.entry_id)
        _LOGGER.info("Migrated %s to a camera of %s", title, ENTRY_TITLE)
    return True
