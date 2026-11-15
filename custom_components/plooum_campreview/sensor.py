"""Status of the last capture: ok, or why the picture was ignored."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import CamPreviewConfigEntry
from .const import STATUSES
from .entity import PreviewEntity
from .manager import PreviewManager


async def async_setup_entry(
    hass: HomeAssistant, entry: CamPreviewConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    for key, m in entry.runtime_data.items():
        async_add_entities([PreviewStatus(m)], config_subentry_id=key)


class PreviewStatus(PreviewEntity, SensorEntity):
    _attr_translation_key = "status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = STATUSES

    def __init__(self, manager: PreviewManager) -> None:
        super().__init__(manager, "status")

    @property
    def native_value(self) -> str:
        return self.manager.status
