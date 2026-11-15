"""The preview picture: the last picture of the camera that passed the filter."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import CamPreviewConfigEntry
from .entity import PreviewEntity
from .manager import PreviewManager


async def async_setup_entry(
    hass: HomeAssistant, entry: CamPreviewConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    for key, m in entry.runtime_data.items():
        async_add_entities([PreviewImage(hass, m)], config_subentry_id=key)


class PreviewImage(PreviewEntity, ImageEntity):
    """State: time of the preview picture. Attributes: what the last capture gave (see manager)."""

    _attr_name = None  # the device's name: "<camera> preview"

    def __init__(self, hass: HomeAssistant, manager: PreviewManager) -> None:
        PreviewEntity.__init__(self, manager, "image")
        ImageEntity.__init__(self, hass)
        self._sync()

    @callback
    def _sync(self) -> None:
        self._attr_content_type = self.manager.content_type
        self._attr_image_last_updated = self.manager.image_time

    @callback
    def _handle_update(self) -> None:
        self._sync()
        super()._handle_update()

    @property
    def image_last_updated(self) -> datetime | None:
        return self.manager.image_time

    async def async_image(self) -> bytes | None:
        return self.manager.image

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self.manager.attributes
