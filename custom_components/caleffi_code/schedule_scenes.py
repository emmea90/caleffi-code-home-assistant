"""Persistent storage and Home Assistant services for schedule scenes."""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import quote

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.storage import Store

from .api import CaleffiApiError
from .const import DOMAIN
from .program import create_day_program, zone_program_by_day

SERVICE_SET_ZONE_SCHEDULE = "set_zone_schedule"
SERVICE_COPY_ZONE_SCHEDULE = "copy_zone_schedule"
SERVICE_SAVE_SCHEDULE_SCENE = "save_schedule_scene"
SERVICE_APPLY_SCHEDULE_SCENE = "apply_schedule_scene"
_SCENE_STORE_KEY = f"{DOMAIN}_schedule_scenes"
_STORE_KEY = f"{DOMAIN}_schedule_scenes"

_SERVICE_SCHEMAS = {
    SERVICE_SET_ZONE_SCHEDULE: vol.Schema(
        {
            vol.Required("gateway_serial"): cv.string,
            vol.Required("zone_id"): vol.Coerce(str),
            vol.Required("day"): vol.All(vol.Coerce(int), vol.Range(min=1, max=7)),
            vol.Required("slots"): list,
        }
    ),
    SERVICE_COPY_ZONE_SCHEDULE: vol.Schema(
        {
            vol.Required("source_gateway_serial"): cv.string,
            vol.Required("source_zone_id"): vol.Coerce(str),
            vol.Required("target_gateway_serial"): cv.string,
            vol.Required("target_zone_id"): vol.Coerce(str),
        }
    ),
    SERVICE_SAVE_SCHEDULE_SCENE: vol.Schema(
        {
            vol.Required("name"): vol.All(cv.string, vol.Length(min=1, max=100)),
            vol.Optional("gateway_serial"): cv.string,
            vol.Optional("zone_id"): vol.Coerce(str),
            vol.Required("scope"): vol.In(("day", "week")),
            vol.Optional("day"): vol.All(vol.Coerce(int), vol.Range(min=1, max=7)),
            vol.Optional("slots"): list,
            vol.Optional("days"): dict,
            vol.Optional("overwrite", default=False): cv.boolean,
        }
    ),
    SERVICE_APPLY_SCHEDULE_SCENE: vol.Schema(
        {
            vol.Required("name"): vol.All(cv.string, vol.Length(min=1, max=100)),
            vol.Required("gateway_serial"): cv.string,
            vol.Required("zone_id"): vol.Coerce(str),
            vol.Optional("day"): vol.All(vol.Coerce(int), vol.Range(min=1, max=7)),
        }
    ),
}


class ScheduleSceneStorage:
    """Keep schedule scenes in Home Assistant's storage directory."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store = Store(hass, 1, _STORE_KEY)
        self._scenes: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def async_load(self) -> None:
        stored = await self._store.async_load()
        if stored is None:
            return
        if not isinstance(stored, dict) or not all(
            isinstance(name, str) and isinstance(scene, dict)
            for name, scene in stored.items()
        ):
            raise HomeAssistantError("Archivio scenari Caleffi non valido")
        self._scenes = stored

    def get(self, name: str) -> dict[str, Any] | None:
        return self._scenes.get(name)

    async def async_save(
        self, name: str, scene: dict[str, Any], overwrite: bool
    ) -> None:
        async with self._lock:
            if name in self._scenes and not overwrite:
                raise HomeAssistantError(
                    f"Esiste già uno scenario chiamato '{name}'; "
                    "imposta overwrite: true per sostituirlo"
                )
            updated = {**self._scenes, name: scene}
            await self._store.async_save(updated)
            self._scenes = updated


def _coordinator(hass: HomeAssistant, serial: str, zone_id: str) -> Any:
    for coordinator in hass.data.get(DOMAIN, {}).values():
        if (
            serial in coordinator.data
            and zone_id in coordinator.data[serial]["zones"]
        ):
            return coordinator
    raise HomeAssistantError(
        f"La zona {zone_id} del gateway {serial} non è disponibile"
    )


def _zone_program(
    coordinator: Any, serial: str, zone_id: str
) -> dict[int, list[dict[str, int]]]:
    try:
        return zone_program_by_day(
            coordinator.data[serial]["zones"][zone_id].get("code_zone_programs")
        )
    except ValueError as err:
        raise HomeAssistantError(
            f"Programmazione non disponibile per la zona {zone_id}: {err}"
        ) from err


def _validate_day_temperatures(
    coordinator: Any,
    serial: str,
    zone_id: str,
    slots: list[dict[str, int]],
) -> None:
    gateway = coordinator.data[serial]["gateway"]
    try:
        min_temperature = (
            float(gateway["temp_min"]) / 10
            if gateway.get("temp_min") is not None
            else 5.0
        )
        max_temperature = (
            float(gateway["temp_max"]) / 10
            if gateway.get("temp_max") is not None
            else 30.0
        )
    except (TypeError, ValueError) as err:
        raise HomeAssistantError(
            f"Limiti di temperatura non validi per il gateway {serial}"
        ) from err
    for slot in slots:
        temperature = slot["temp_set"] / 10
        if not min_temperature <= temperature <= max_temperature:
            raise HomeAssistantError(
                f"La temperatura {temperature:g} °C della fascia non rientra "
                f"nei limiti {min_temperature:g}-{max_temperature:g} °C "
                f"del gateway {serial}"
            )


async def _async_write_day(
    coordinator: Any,
    serial: str,
    zone_id: str,
    day: int,
    slots: list[dict[str, int]],
) -> None:
    _validate_day_temperatures(coordinator, serial, zone_id, slots)
    path = (
        f"code/{quote(serial, safe='')}/zone/{quote(zone_id, safe='')}/"
        f"programming/day/{day}"
    )
    try:
        await coordinator.api.async_request("PUT", path, json_body=slots)
    except CaleffiApiError as err:
        raise HomeAssistantError(
            f"Errore aggiornando il giorno {day} della zona {zone_id}: {err}. "
            "Se l'operazione riguardava più giorni, quelli precedenti potrebbero "
            "essere già stati aggiornati."
        ) from err


async def _async_refresh(coordinators: set[Any]) -> None:
    for coordinator in coordinators:
        await coordinator.async_request_refresh()


async def _async_set_zone_schedule(call: ServiceCall) -> None:
    serial = call.data["gateway_serial"]
    zone_id = call.data["zone_id"]
    coordinator = _coordinator(call.hass, serial, zone_id)
    gateway = coordinator.data[serial]["gateway"]

    def temperature_limit(key: str, default: float) -> float:
        value = gateway.get(key)
        try:
            return float(value) / 10 if value is not None else default
        except (TypeError, ValueError):
            return default

    try:
        slots = create_day_program(
            call.data["day"],
            call.data["slots"],
            temperature_limit("temp_min", 5.0),
            temperature_limit("temp_max", 30.0),
        )
    except ValueError as err:
        raise HomeAssistantError(str(err)) from err

    await _async_write_day(coordinator, serial, zone_id, call.data["day"], slots)
    await coordinator.async_request_refresh()


async def _async_copy_zone_schedule(call: ServiceCall) -> None:
    source_serial = call.data["source_gateway_serial"]
    source_zone = call.data["source_zone_id"]
    target_serial = call.data["target_gateway_serial"]
    target_zone = call.data["target_zone_id"]
    if source_serial == target_serial and source_zone == target_zone:
        raise HomeAssistantError("La zona sorgente e quella destinazione coincidono")

    source_coordinator = _coordinator(call.hass, source_serial, source_zone)
    target_coordinator = _coordinator(call.hass, target_serial, target_zone)
    schedule = _zone_program(source_coordinator, source_serial, source_zone)
    if any(not schedule[day] for day in range(1, 8)):
        raise HomeAssistantError(
            "La zona sorgente non contiene una programmazione completa per tutti "
            "i sette giorni; nessuna modifica è stata inviata"
        )

    for day in range(1, 8):
        _validate_day_temperatures(
            target_coordinator, target_serial, target_zone, schedule[day]
        )
    for day in range(1, 8):
        await _async_write_day(
            target_coordinator, target_serial, target_zone, day, schedule[day]
        )
    await _async_refresh({target_coordinator})


async def _async_save_schedule_scene(call: ServiceCall) -> None:
    scope = call.data["scope"]
    day = call.data.get("day")
    slots = call.data.get("slots")
    days = call.data.get("days")
    serial = call.data.get("gateway_serial")
    zone_id = call.data.get("zone_id")
    has_source = serial is not None and zone_id is not None
    has_partial_source = (serial is None) != (zone_id is None)
    if has_partial_source:
        raise HomeAssistantError(
            "Per acquisire lo scenario da una zona specifica servono "
            "sia gateway_serial sia zone_id"
        )

    if scope == "day" and day is None:
        raise HomeAssistantError("Per uno scenario giornaliero specifica il giorno")
    if scope == "week" and day is not None:
        raise HomeAssistantError("Uno scenario settimanale non accetta il campo day")
    if scope == "day":
        if days is not None:
            raise HomeAssistantError(
                "Uno scenario giornaliero non accetta il campo days"
            )
        if slots is not None:
            if has_source:
                raise HomeAssistantError(
                    "Scegli se definire le fasce con slots o acquisirle da una zona"
                )
            try:
                scene_slots = create_day_program(day, slots, 5.0, 30.0)
            except ValueError as err:
                raise HomeAssistantError(str(err)) from err
        else:
            if not has_source:
                raise HomeAssistantError(
                    "Specifica slots oppure gateway_serial e zone_id per acquisire "
                    "la programmazione da una zona"
                )
            coordinator = _coordinator(call.hass, serial, zone_id)
            schedule = _zone_program(coordinator, serial, zone_id)
            scene_slots = schedule[day]
            if not scene_slots:
                raise HomeAssistantError(
                    f"Nessuna fascia programmata per il giorno {day}"
                )
        scene = {"scope": "day", "day": day, "slots": scene_slots}
    else:
        if slots is not None:
            raise HomeAssistantError(
                "Uno scenario settimanale non accetta il campo slots"
            )
        if days is not None:
            if has_source:
                raise HomeAssistantError(
                    "Scegli se definire le fasce con days o acquisirle da una zona"
                )
            if not isinstance(days, dict) or set(days) not in (
                {str(weekday) for weekday in range(1, 8)},
                set(range(1, 8)),
            ):
                raise HomeAssistantError(
                    "days deve contenere esattamente i giorni da 1 a 7"
                )
            scene_days: dict[str, list[dict[str, int]]] = {}
            for weekday in range(1, 8):
                day_slots = days.get(str(weekday), days.get(weekday))
                try:
                    scene_days[str(weekday)] = create_day_program(
                        weekday, day_slots, 5.0, 30.0
                    )
                except ValueError as err:
                    raise HomeAssistantError(
                        f"Programmazione non valida per il giorno {weekday}: {err}"
                    ) from err
        else:
            if not has_source:
                raise HomeAssistantError(
                    "Specifica days oppure gateway_serial e zone_id per acquisire "
                    "la programmazione da una zona"
                )
            coordinator = _coordinator(call.hass, serial, zone_id)
            schedule = _zone_program(coordinator, serial, zone_id)
            if any(not schedule[weekday] for weekday in range(1, 8)):
                raise HomeAssistantError(
                    "Per salvare uno scenario settimanale servono le fasce di tutti "
                    "i sette giorni"
                )
            scene_days = {
                str(weekday): schedule[weekday] for weekday in range(1, 8)
            }
        scene = {"scope": "week", "days": scene_days}

    storage: ScheduleSceneStorage = call.hass.data[_SCENE_STORE_KEY]
    await storage.async_save(call.data["name"], scene, call.data["overwrite"])


def _scene_day_slots(slots: Any, day: int, name: str) -> list[dict[str, int]]:
    if not isinstance(slots, list) or not slots:
        raise HomeAssistantError(f"Lo scenario '{name}' è vuoto o non valido")
    try:
        records = [
            {
                **slot,
                "day": day,
                "slot": index,
            }
            for index, slot in enumerate(slots)
            if isinstance(slot, dict)
        ]
        if len(records) != len(slots):
            raise ValueError("una fascia non è un oggetto valido")
        return zone_program_by_day(records)[day]
    except (TypeError, ValueError) as err:
        raise HomeAssistantError(
            f"Programmazione non valida nello scenario '{name}': {err}"
        ) from err


async def _async_apply_schedule_scene(call: ServiceCall) -> None:
    storage: ScheduleSceneStorage = call.hass.data[_SCENE_STORE_KEY]
    scene = storage.get(call.data["name"])
    if scene is None:
        raise HomeAssistantError(f"Scenario '{call.data['name']}' non trovato")
    serial = call.data["gateway_serial"]
    zone_id = call.data["zone_id"]
    coordinator = _coordinator(call.hass, serial, zone_id)

    if scene.get("scope") == "day":
        requested_day = call.data.get("day", scene.get("day"))
        if (
            isinstance(requested_day, bool)
            or not isinstance(requested_day, int)
            or not 1 <= requested_day <= 7
        ):
            raise HomeAssistantError("Giorno di applicazione non valido")
        payload = _scene_day_slots(
            scene.get("slots"), requested_day, call.data["name"]
        )
        await _async_write_day(coordinator, serial, zone_id, requested_day, payload)
    elif scene.get("scope") == "week":
        if call.data.get("day") is not None:
            raise HomeAssistantError(
                "Il campo day si usa solo applicando uno scenario giornaliero"
            )
        days = scene.get("days")
        if not isinstance(days, dict) or any(
            not isinstance(days.get(str(day)), list) or not days[str(day)]
            for day in range(1, 8)
        ):
            raise HomeAssistantError(f"Lo scenario '{call.data['name']}' è incompleto")
        payloads = {
            day: _scene_day_slots(days[str(day)], day, call.data["name"])
            for day in range(1, 8)
        }
        for slots in payloads.values():
            _validate_day_temperatures(coordinator, serial, zone_id, slots)
        for day in range(1, 8):
            await _async_write_day(
                coordinator, serial, zone_id, day, payloads[day]
            )
    else:
        raise HomeAssistantError(f"Lo scenario '{call.data['name']}' non è valido")

    await coordinator.async_request_refresh()


async def async_setup_services(hass: HomeAssistant) -> None:
    """Load stored scenes and register integration services."""
    if _SCENE_STORE_KEY in hass.data:
        return
    storage = ScheduleSceneStorage(hass)
    await storage.async_load()
    hass.data[_SCENE_STORE_KEY] = storage
    hass.data.setdefault(DOMAIN, {})
    handlers = {
        SERVICE_SET_ZONE_SCHEDULE: _async_set_zone_schedule,
        SERVICE_COPY_ZONE_SCHEDULE: _async_copy_zone_schedule,
        SERVICE_SAVE_SCHEDULE_SCENE: _async_save_schedule_scene,
        SERVICE_APPLY_SCHEDULE_SCENE: _async_apply_schedule_scene,
    }
    for service, handler in handlers.items():
        if not hass.services.has_service(DOMAIN, service):
            hass.services.async_register(
                DOMAIN, service, handler, schema=_SERVICE_SCHEMAS[service]
            )


def async_unload_services(hass: HomeAssistant) -> None:
    """Remove integration services after its last config entry unloads."""
    for service in _SERVICE_SCHEMAS:
        hass.services.async_remove(DOMAIN, service)
    hass.data.pop(_SCENE_STORE_KEY, None)
