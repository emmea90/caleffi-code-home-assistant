"""Temperature sensors for Caleffi CODE zones."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import CaleffiCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: CaleffiCoordinator = hass.data[DOMAIN][entry.entry_id]
    added_zones: set[tuple[str, str]] = set()

    def add_new_zones() -> None:
        entities: list[CaleffiZoneTemperature] = []
        for gateway_serial, gateway_data in coordinator.data.items():
            for zone_id in gateway_data["zones"]:
                zone_key = (gateway_serial, zone_id)
                if zone_key not in added_zones:
                    added_zones.add(zone_key)
                    entities.append(
                        CaleffiZoneTemperature(coordinator, gateway_serial, zone_id)
                    )
        if entities:
            async_add_entities(entities)

    entry.async_on_unload(coordinator.async_add_listener(add_new_zones))
    add_new_zones()


class CaleffiZoneTemperature(CoordinatorEntity[CaleffiCoordinator], SensorEntity):
    """Expose a zone's current room temperature as a history-friendly sensor."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: CaleffiCoordinator,
        gateway_serial: str,
        zone_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._gateway_serial = gateway_serial
        self._zone_id = zone_id
        self._attr_unique_id = f"{gateway_serial}_{zone_id}_room_temperature"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, gateway_serial)},
            manufacturer="Caleffi",
            model="CODE",
            name=self._gateway_name,
        )
        self._attr_name = f"Caleffi {self._zone_name} temperatura"

    @property
    def _gateway(self) -> dict[str, Any]:
        return self.coordinator.data[self._gateway_serial]["gateway"]

    @property
    def _zone(self) -> dict[str, Any]:
        return self.coordinator.data[self._gateway_serial]["zones"][self._zone_id]

    @property
    def _gateway_name(self) -> str:
        return str(self._gateway.get("name") or self._gateway_serial)

    @property
    def _zone_name(self) -> str:
        return str(self._zone.get("name") or f"Zona {self._zone_id}")

    @property
    def available(self) -> bool:
        return (
            super().available
            and self._gateway_serial in self.coordinator.data
            and self._zone_id
            in self.coordinator.data[self._gateway_serial]["zones"]
        )

    @property
    def native_value(self) -> float | None:
        value = self._zone.get("temp_room")
        if value is None:
            return None
        try:
            return float(value) / 10
        except (TypeError, ValueError):
            return None
