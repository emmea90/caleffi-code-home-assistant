"""Data coordinator for Caleffi CODE gateways and heating zones."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any
from urllib.parse import quote

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import CaleffiApi, CaleffiApiError
from .const import DOMAIN, UPDATE_INTERVAL_MINUTES


class CaleffiCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Fetch gateways and their zones from the Caleffi cloud."""

    def __init__(self, hass: HomeAssistant, api: CaleffiApi) -> None:
        self.api = api
        super().__init__(
            hass,
            logger=logging.getLogger(__name__),
            name=DOMAIN,
            update_interval=timedelta(minutes=UPDATE_INTERVAL_MINUTES),
        )

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        try:
            gateways = await self.api.async_request(
                "GET", "code", params={"my": "true"}
            )
            if not isinstance(gateways, list):
                raise CaleffiApiError("Caleffi CODE returned an invalid gateway list")

            data: dict[str, dict[str, Any]] = {}
            for gateway in gateways:
                if not isinstance(gateway, dict):
                    raise CaleffiApiError(
                        "Caleffi CODE returned an invalid gateway record"
                    )
                serial = self._field(gateway, "serial", "code_sn", "codeSn", "sn")
                if serial is None:
                    raise CaleffiApiError(
                        "A Caleffi CODE gateway is missing its serial number"
                    )
                serial = str(serial)
                zones = await self.api.async_request(
                    "GET", f"code/{quote(serial, safe='')}/zone"
                )
                if not isinstance(zones, list):
                    raise CaleffiApiError(
                        f"Caleffi CODE returned an invalid zone list for {serial}"
                    )

                zone_data: dict[str, dict[str, Any]] = {}
                for zone in zones:
                    if not isinstance(zone, dict):
                        raise CaleffiApiError(
                            f"Caleffi CODE returned an invalid zone for {serial}"
                        )
                    zone_id = self._field(zone, "zone", "zone_id", "zoneId")
                    if zone_id is None:
                        raise CaleffiApiError(
                            f"A Caleffi CODE zone on {serial} has no zone identifier"
                        )
                    zone_data[str(zone_id)] = zone

                data[serial] = {"gateway": gateway, "zones": zone_data}
            return data
        except CaleffiApiError as err:
            if err.status in (401, 403):
                raise ConfigEntryAuthFailed(
                    "Caleffi CODE authentication failed"
                ) from err
            raise UpdateFailed(str(err)) from err

    @staticmethod
    def _field(record: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            if record.get(key) is not None:
                return record[key]
        return None
