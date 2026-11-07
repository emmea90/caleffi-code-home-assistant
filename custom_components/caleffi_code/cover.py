"""Open and close controls for Caleffi CODE valves."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from homeassistant.components.cover import (
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
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
    added_valves: set[tuple[str, str, str]] = set()

    def add_new_valves() -> None:
        entities: list[CaleffiValveCover] = []
        for gateway_serial, gateway_data in coordinator.data.items():
            for zone_id, zone in gateway_data["zones"].items():
                for device_serial in zone.get("valves", {}):
                    valve_key = (gateway_serial, zone_id, device_serial)
                    if valve_key not in added_valves:
                        added_valves.add(valve_key)
                        entities.append(
                            CaleffiValveCover(
                                coordinator, gateway_serial, zone_id, device_serial
                            )
                        )
        if entities:
            async_add_entities(entities)

    entry.async_on_unload(coordinator.async_add_listener(add_new_valves))
    add_new_valves()


class CaleffiValveCover(CoordinatorEntity[CaleffiCoordinator], CoverEntity):
    """Represent the actual open/close control of a Caleffi CODE valve."""

    _attr_supported_features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE

    def __init__(
        self,
        coordinator: CaleffiCoordinator,
        gateway_serial: str,
        zone_id: str,
        device_serial: str,
    ) -> None:
        super().__init__(coordinator)
        self._gateway_serial = gateway_serial
        self._zone_id = zone_id
        self._device_serial = device_serial
        self._attr_unique_id = (
            f"{gateway_serial}_{zone_id}_{device_serial}_valve_control"
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, gateway_serial)},
            manufacturer="Caleffi",
            model="CODE",
            name=self._gateway_name,
        )
        self._attr_name = f"Testina {self._device_name}"

    @property
    def _gateway(self) -> dict[str, Any]:
        return self.coordinator.data[self._gateway_serial]["gateway"]

    @property
    def _valve(self) -> dict[str, Any]:
        return (
            self.coordinator.data.get(self._gateway_serial, {})
            .get("zones", {})
            .get(self._zone_id, {})
            .get("valves", {})
            .get(self._device_serial, {})
        )

    @property
    def _gateway_name(self) -> str:
        return str(self._gateway.get("name") or self._gateway_serial)

    @property
    def _device_name(self) -> str:
        device = self._valve.get("device", {})
        return str(device.get("name") or self._device_serial)

    @property
    def available(self) -> bool:
        return (
            super().available
            and self._gateway_serial in self.coordinator.data
            and self._zone_id
            in self.coordinator.data[self._gateway_serial]["zones"]
            and self._device_serial
            in self.coordinator.data[self._gateway_serial]["zones"][self._zone_id][
                "valves"
            ]
        )

    @property
    def current_cover_position(self) -> int | None:
        value = self._valve.get("params", {}).get("pc_opening")
        if value is None:
            return None
        try:
            return max(0, min(100, round(float(value))))
        except (TypeError, ValueError):
            return None

    @property
    def is_closed(self) -> bool | None:
        position = self.current_cover_position
        return None if position is None else position == 0

    async def async_open_cover(self, **kwargs: Any) -> None:
        await self._set_open(True)

    async def async_close_cover(self, **kwargs: Any) -> None:
        await self._set_open(False)

    async def _set_open(self, is_open: bool) -> None:
        await self.coordinator.api.async_request(
            "PUT",
            f"code/{quote(self._gateway_serial, safe='')}/zone/"
            f"{quote(self._zone_id, safe='')}/device/confort_control/"
            f"{quote(f'1-{self._device_serial}', safe='')}/force_open",
            json_body={"open": is_open},
        )
        await self.coordinator.async_request_refresh()
