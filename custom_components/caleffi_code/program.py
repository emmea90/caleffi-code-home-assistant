"""Helpers for reading and writing Caleffi CODE weekly programs."""

from __future__ import annotations

import math
import re
from typing import Any

DAYS = (
    "domenica",
    "lunedi",
    "martedi",
    "mercoledi",
    "giovedi",
    "venerdi",
    "sabato",
)
_TIME_PATTERN = re.compile(r"(?:[01]\d|2[0-3]):[0-5]\d|24:00")
_MAX_SLOTS_PER_DAY = 8


def weekly_schedule(programs: Any) -> dict[str, list[dict[str, Any]]]:
    """Convert API schedule records to display-friendly weekday attributes."""
    schedule: dict[str, list[dict[str, Any]]] = {day: [] for day in DAYS}
    if not isinstance(programs, list):
        return schedule

    for program in programs:
        if not isinstance(program, dict):
            continue
        try:
            day = int(program["day"])
            slot = int(program["slot"])
            seconds = int(program["duration_sec"])
            temperature = float(program["temp_set"]) / 10
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if (
            not 1 <= day <= len(DAYS)
            or seconds < 0
            or not math.isfinite(temperature)
        ):
            continue
        minutes = seconds // 60
        hours, minute = divmod(minutes, 60)
        schedule[DAYS[day - 1]].append(
            {
                "slot": slot,
                "ora_fine": f"{hours:02}:{minute:02}",
                "temperatura": temperature,
            }
        )

    for entries in schedule.values():
        entries.sort(key=lambda entry: (entry["slot"], entry["ora_fine"]))
    return schedule


def create_day_program(
    day: int,
    slots: Any,
    min_temperature: float,
    max_temperature: float,
) -> list[dict[str, int]]:
    """Validate user-provided schedule slots and create the API payload."""
    if (
        isinstance(day, bool)
        or not isinstance(day, int)
        or not 1 <= day <= len(DAYS)
    ):
        raise ValueError(
            "Il giorno deve essere un numero da 1 (domenica) a 7 (sabato)"
        )
    if not isinstance(slots, list) or not 1 <= len(slots) <= _MAX_SLOTS_PER_DAY:
        raise ValueError("Inserisci da 1 a 8 fasce orarie per il giorno")

    result: list[dict[str, int]] = []
    previous_seconds = 0
    for index, slot in enumerate(slots):
        if (
            not isinstance(slot, dict)
            or "time" not in slot
            or "temperature" not in slot
        ):
            raise ValueError(
                "Ogni fascia deve contenere 'time' (HH:MM) e 'temperature' (°C)"
            )
        time_value = slot["time"]
        if not isinstance(time_value, str) or not _TIME_PATTERN.fullmatch(time_value):
            raise ValueError("L'orario deve essere HH:MM; è ammesso anche 24:00")
        hours, minutes = (int(part) for part in time_value.split(":"))
        seconds = hours * 3600 + minutes * 60
        if seconds <= previous_seconds:
            raise ValueError("Gli orari devono essere in ordine crescente e dopo 00:00")
        previous_seconds = seconds

        try:
            temperature = float(slot["temperature"])
        except (TypeError, ValueError, OverflowError) as err:
            raise ValueError("La temperatura deve essere un numero") from err
        if not math.isfinite(temperature) or not (
            min_temperature <= temperature <= max_temperature
        ):
            raise ValueError(
                f"La temperatura deve essere tra {min_temperature:g} e "
                f"{max_temperature:g} °C"
            )
        result.append(
            {
                "day": day,
                "slot": index,
                "duration_sec": seconds,
                "temp_set": round(temperature * 10),
            }
        )
    return result


def zone_program_by_day(programs: Any) -> dict[int, list[dict[str, int]]]:
    """Validate API schedule records and group them by Caleffi weekday."""
    if not isinstance(programs, list):
        raise ValueError("la zona non contiene una lista di fasce")

    schedule: dict[int, list[dict[str, int]]] = {
        day: [] for day in range(1, len(DAYS) + 1)
    }
    for program in programs:
        if not isinstance(program, dict):
            raise ValueError("una fascia non è un oggetto valido")
        try:
            day = program["day"]
            slot = program["slot"]
            seconds = program["duration_sec"]
            temperature = program["temp_set"]
            if any(
                isinstance(value, bool) for value in (day, slot, seconds, temperature)
            ):
                raise ValueError
            day = int(day)
            slot = int(slot)
            seconds = int(seconds)
            temperature = int(temperature)
        except (KeyError, TypeError, ValueError, OverflowError) as err:
            raise ValueError("una fascia contiene campi non validi") from err
        if not 1 <= day <= len(DAYS):
            raise ValueError(f"giorno non valido: {day}")
        if not 0 <= slot < _MAX_SLOTS_PER_DAY:
            raise ValueError(f"numero fascia non valido: {slot}")
        if not 0 < seconds <= 86400:
            raise ValueError(f"orario di fine fascia non valido: {seconds}")
        schedule[day].append(
            {
                "day": day,
                "slot": slot,
                "duration_sec": seconds,
                "temp_set": temperature,
            }
        )

    for day, entries in schedule.items():
        entries.sort(key=lambda entry: entry["slot"])
        if [entry["slot"] for entry in entries] != list(range(len(entries))):
            raise ValueError(f"numerazione fasce non valida per il giorno {day}")
        if any(
            earlier["duration_sec"] >= later["duration_sec"]
            for earlier, later in zip(entries, entries[1:])
        ):
            raise ValueError(f"orari non crescenti per il giorno {day}")
    return schedule
