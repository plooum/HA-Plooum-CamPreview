"""Base of the entities of a camera preview."""

from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .manager import PreviewManager


class PreviewEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, manager: PreviewManager, key: str) -> None:
        self.manager = manager
        self._attr_unique_id = f"{manager.key}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, manager.key)},
            name=f"{manager.title} preview",
            manufacturer="Plooum",
            model="Camera preview",
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.manager.async_add_listener(self._handle_update))

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()
