"""Force update: take the camera's current picture as the preview and as its new view."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import CamPreviewConfigEntry
from .entity import PreviewEntity
from .manager import PreviewManager


async def async_setup_entry(
    hass: HomeAssistant, entry: CamPreviewConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([ForceUpdateButton(entry.runtime_data)])


class ForceUpdateButton(PreviewEntity, ButtonEntity):
    _attr_translation_key = "force_update"

    def __init__(self, manager: PreviewManager) -> None:
        super().__init__(manager, "force_update")

    async def async_press(self) -> None:
        await self.manager.async_update(force=True)
