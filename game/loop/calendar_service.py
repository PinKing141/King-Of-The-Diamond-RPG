import json
import os
import logging
from typing import Dict, Iterable, List, Set

from config import DATA_FOLDER

logger = logging.getLogger(__name__)

SEASON_CALENDAR_PATH = os.path.join(DATA_FOLDER, "season_calendar.json")

DEFAULT_CALENDAR: Dict[str, Dict[str, List[int]]] = {
    "tournaments": {
        "summer_qualifiers": [15],
        "spring_koshien": [48],
    },
    "camps": {
        "winter": [40],
    },
    "interrupt_weeks": [15, 40, 48],
}


def _coerce_int_list(values: Iterable) -> List[int]:
    cleaned: List[int] = []
    for v in values:
        try:
            cleaned.append(int(v))
        except (TypeError, ValueError):
            continue
    return cleaned


def _load_calendar_file() -> Dict:
    try:
        with open(SEASON_CALENDAR_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
            return raw if isinstance(raw, dict) else {}
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Season calendar load failed; using defaults: %s", exc)
        return {}


def load_calendar() -> Dict[str, Dict[str, List[int]]]:
    """Load season calendar data, falling back to defaults on any error."""
    raw = _load_calendar_file()
    calendar: Dict[str, Dict[str, List[int]]] = {}

    tournaments = raw.get("tournaments", DEFAULT_CALENDAR["tournaments"])
    calendar["tournaments"] = {
        name: _coerce_int_list(weeks)
        for name, weeks in tournaments.items()
        if isinstance(weeks, (list, tuple))
    }

    camps = raw.get("camps", DEFAULT_CALENDAR["camps"])
    calendar["camps"] = {
        name: _coerce_int_list(weeks)
        for name, weeks in camps.items()
        if isinstance(weeks, (list, tuple))
    }

    interrupt_weeks = raw.get("interrupt_weeks", DEFAULT_CALENDAR.get("interrupt_weeks", []))
    calendar["interrupt_weeks"] = _coerce_int_list(interrupt_weeks)

    return calendar


_CALENDAR_CACHE: Dict[str, Dict[str, List[int]]] = {}


def _calendar() -> Dict[str, Dict[str, List[int]]]:
    global _CALENDAR_CACHE
    if not _CALENDAR_CACHE:
        _CALENDAR_CACHE = load_calendar()
    return _CALENDAR_CACHE


def _collect(section: str, name: str | None = None) -> Set[int]:
    data = _calendar().get(section, {})
    if name:
        return set(data.get(name, []))
    weeks: Set[int] = set()
    if isinstance(data, dict):
        for vals in data.values():
            weeks.update(vals)
    elif isinstance(data, list):
        weeks.update(data)
    return weeks


def get_tournament_weeks(name: str | None = None) -> Set[int]:
    return _collect("tournaments", name)


def get_camp_weeks(name: str | None = None) -> Set[int]:
    return _collect("camps", name)


def get_interrupt_weeks() -> Set[int]:
    explicit = set(_calendar().get("interrupt_weeks", []))
    # Ensure tournaments and camps also register as interrupt candidates.
    return explicit | get_tournament_weeks() | get_camp_weeks()


def is_summer_qualifiers_week(week: int) -> bool:
    return week in get_tournament_weeks("summer_qualifiers")


def is_spring_koshien_week(week: int) -> bool:
    return week in get_tournament_weeks("spring_koshien")


def is_winter_camp_week(week: int) -> bool:
    return week in get_camp_weeks("winter")


def refresh_calendar_cache() -> None:
    """Force reload from disk (useful in tests)."""
    global _CALENDAR_CACHE
    _CALENDAR_CACHE = {}
