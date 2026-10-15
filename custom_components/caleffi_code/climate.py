"""Climate entities for Caleffi CODE zones."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import CaleffiCoordinator

QUICK_FUN_NAMES = {
    0: "auto",
    1: "eco",
    2: "holiday",
    3: "manual",
    4: "off",
    5: "party",
    6: "cleaning",
    7: "forced_off",
}
QUICK_FUN_IDS = {name: quick_fun for quick_fun, name in QUICK_FUN_NAMES.items()}
MANUAL_DURATION_SECONDS = 7200


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: CaleffiCoordinator = hass.data[DOMAIN][entry.entry_id]
    added_zones: set[tuple[str, str]] = set()

    def add_new_zones() -> None:
        entities: list[CaleffiZoneClimate] = []
        for gateway_serial, gateway_data in coordinator.data.items():
            for zone_id in gateway_data["zones"]:
                zone_key = (gateway_serial, zone_id)
                if zone_key not in added_zones:
                    added_zones.add(zone_key)
                    entities.append(
                        CaleffiZoneClimate(coordinator, gateway_serial, zone_id)
                    )
        if entities:
            async_add_entities(entities)

    entry.async_on_unload(coordinator.async_add_listener(add_new_zones))
    add_new_zones()


class CaleffiZoneClimate(CoordinatorEntity[CaleffiCoordinator], ClimateEntity):
    """Represent a single Caleffi CODE heating zone."""

    _attr_has_entity_name = True
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.AUTO, HVACMode.HEAT, HVACMode.OFF]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.PRESET_MODE
    )
    _attr_preset_modes = list(QUICK_FUN_IDS)

    def __init__(
        self,
        coordinator: CaleffiCoordinator,
        gateway_serial: str,
        zone_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._gateway_serial = gateway_serial
        self._zone_id = zone_id
        self._attr_unique_id = f"{gateway_serial}_{zone_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, gateway_serial)},
            manufacturer="Caleffi",
            model="CODE",
            name=self._gateway_name,
        )
        self._attr_name = self._zone_name

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
    def current_temperature(self) -> float | None:
        return self._temperature_value("temp_room")

    @property
    def target_temperature(self) -> float | None:
        return self._temperature_value("temp_set")

    @property
    def min_temp(self) -> float:
        return self._gateway_temperature_limit("temp_min", 5.0)

    @property
    def max_temp(self) -> float:
        return self._gateway_temperature_limit("temp_max", 30.0)

    @property
    def hvac_mode(self) -> HVACMode:
        quick_fun = self._quick_fun
        if quick_fun == 0:
            return HVACMode.AUTO
        if quick_fun in (4, 7):
            return HVACMode.OFF
        return HVACMode.HEAT

    @property
    def preset_mode(self) -> str | None:
        return QUICK_FUN_NAMES.get(self._quick_fun)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "gateway_serial": self._gateway_serial,
            "zone_id": self._zone_id,
            "quick_function": self._quick_fun,
            "alarms": self._zone.get("alarms"),
        }

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temperature = kwargs.get("temperature")
        if temperature is None:
            raise ValueError("A target temperature is required")
        if not self.min_temp <= temperature <= self.max_temp:
            raise ValueError(
                f"Temperature must be between {self.min_temp} and {self.max_temp} °C"
            )
        await self._set_zone(
            {
                "quick_fun": 3,
                "temp_set": round(temperature * 10),
                "duration_sec": MANUAL_DURATION_SECONDS,
            }
        )

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.AUTO:
            body = {"quick_fun": 0}
        elif hvac_mode == HVACMode.OFF:
            body = {"quick_fun": 4}
        elif hvac_mode == HVACMode.HEAT:
            target = self.target_temperature
            if target is None:
                target = 20.0
            body = {
                "quick_fun": 3,
                "temp_set": round(target * 10),
                "duration_sec": MANUAL_DURATION_SECONDS,
            }
        else:
            raise ValueError(f"Unsupported HVAC mode: {hvac_mode}")
        await self._set_zone(body)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        quick_fun = QUICK_FUN_IDS.get(preset_mode)
        if quick_fun is None:
            raise ValueError(f"Unsupported Caleffi CODE preset: {preset_mode}")

        body: dict[str, int] = {"quick_fun": quick_fun}
        if quick_fun == 3:
            target = self.target_temperature
            if target is None:
                target = 20.0
            body["temp_set"] = round(target * 10)
            body["duration_sec"] = MANUAL_DURATION_SECONDS
        await self._set_zone(body)

    async def _set_zone(self, body: dict[str, Any]) -> None:
        await self.coordinator.api.async_request(
            "PUT",
            f"code/{quote(self._gateway_serial, safe='')}/zone/{quote(self._zone_id, safe='')}",
            json_body=body,
        )
        await self.coordinator.async_request_refresh()

    @property
    def _quick_fun(self) -> int:
        value = self._zone.get("quick_fun", self._zone.get("quick_function", 0))
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def _temperature_value(self, key: str) -> float | None:
        value = self._zone.get(key)
        if value is None:
            return None
        try:
            return float(value) / 10
        except (TypeError, ValueError):
            return None

    def _gateway_temperature_limit(self, key: str, default: float) -> float:
        value = self._gateway.get(key)
        if value is None:
            return default
        try:
            return float(value) / 10
        except (TypeError, ValueError):
            return default
