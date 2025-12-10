"""End-of-season processing: graduations, growth, recruiting, and epilogues."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from core.event_bus import EventBus
from database.setup_db import GameState, Player, PlayerGameStats, School, get_session
from game.loop.offseason_engine import apply_physical_growth, graduate_third_years, recruit_freshmen
from ui.ui_display import Colour
from world_sim.services.sim_data import get_rosters

logger = logging.getLogger(__name__)


@dataclass
class SeasonEndResult:
    user_graduated: bool
    events: List[Dict[str, Any]]

    def __bool__(self) -> bool:  # Allows "if result:" style checks
        return self.user_graduated


@dataclass
class PlayerProfile:
    player: Player
    school: Optional[School]
    positions: Set[str]
    is_two_way: bool
    is_injured: bool
    growth_tag: Optional[str]
    prestige: int
    titles: int
    velocity: int
    control: int
    command: int
    movement: int
    stamina: int
    power: int
    contact: int
    fielding: int
    speed: int
    throwing: int
    catcher_leadership: int
    mental: int
    overall: int
    clutch: int
    innings_pitched: float
    runs_allowed: int
    home_runs: int
    at_bats: int
    hits: int
    era: Optional[float]
    batting_average: float


ATTRIBUTE_DEFAULTS: Dict[str, int] = {
    "velocity": 120,
    "control": 50,
    "command": 50,
    "movement": 50,
    "stamina": 50,
    "power": 50,
    "contact": 50,
    "fielding": 50,
    "speed": 50,
    "throwing": 50,
    "catcher_leadership": 50,
    "mental": 50,
    "overall": 50,
    "clutch": 50,
}


def _emit_event(
    event_bus: Optional[EventBus],
    events: List[Dict[str, Any]],
    event_name: str,
    payload: Dict[str, Any],
) -> None:
    enriched = {"event": event_name, **payload}
    events.append(enriched)
    try:
        if event_bus:
            event_bus.publish(event_name, enriched)
    except Exception:  # Analytics/logging should not block progression
        logger.warning("Event bus publish failed for %s", event_name, exc_info=True)


def _safe_attr_value(obj: Any, attr: str, default: int) -> int:
    value = getattr(obj, attr, None)
    return default if value is None else int(value)


def _compute_totals(stats: Sequence[PlayerGameStats]) -> Dict[str, Any]:
    innings_pitched = sum(float(s.innings_pitched or 0) for s in stats)
    runs_allowed = sum(int(s.runs_allowed or 0) for s in stats)
    home_runs = sum(int(s.homeruns or 0) for s in stats)
    at_bats = sum(int(s.at_bats or 0) for s in stats)
    hits = sum(int(s.hits_batted or 0) for s in stats)

    era = None
    if innings_pitched > 0:
        era = (runs_allowed * 9.0) / innings_pitched
    batting_average = hits / at_bats if at_bats else 0.0

    return {
        "innings_pitched": innings_pitched,
        "runs_allowed": runs_allowed,
        "home_runs": home_runs,
        "at_bats": at_bats,
        "hits": hits,
        "era": era,
        "batting_average": batting_average,
    }


def _estimate_titles(school: Optional[School]) -> int:
    if not school:
        return 0
    try:
        # Use prestige as a loose proxy for historical success.
        return max(0, int(getattr(school, "prestige", 0)) // 20)
    except Exception:
        return 0


def _build_player_profile(player: Player, school: Optional[School], session) -> PlayerProfile:
    stats: Sequence[PlayerGameStats] = (
        session.query(PlayerGameStats).filter_by(player_id=player.id).all()
        if session is not None and getattr(player, "id", None) is not None
        else []
    )
    totals = _compute_totals(stats)

    positions = set()
    try:
        raw_positions = getattr(player, "position", None) or getattr(player, "positions", "")
        if isinstance(raw_positions, str):
            positions = {p.strip() for p in raw_positions.split(",") if p.strip()}
        elif isinstance(raw_positions, Iterable):
            positions = {str(p) for p in raw_positions if p}
    except Exception:
        positions = set()

    return PlayerProfile(
        player=player,
        school=school,
        positions=positions,
        is_two_way=bool(getattr(player, "is_two_way", False)),
        is_injured=bool(getattr(player, "is_injured", False)),
        growth_tag=getattr(player, "growth_tag", None),
        prestige=int(getattr(school, "prestige", 0)) if school else 0,
        titles=_estimate_titles(school),
        velocity=_safe_attr_value(player, "velocity", ATTRIBUTE_DEFAULTS["velocity"]),
        control=_safe_attr_value(player, "control", ATTRIBUTE_DEFAULTS["control"]),
        command=_safe_attr_value(player, "command", ATTRIBUTE_DEFAULTS["command"]),
        movement=_safe_attr_value(player, "movement", ATTRIBUTE_DEFAULTS["movement"]),
        stamina=_safe_attr_value(player, "stamina", ATTRIBUTE_DEFAULTS["stamina"]),
        power=_safe_attr_value(player, "power", ATTRIBUTE_DEFAULTS["power"]),
        contact=_safe_attr_value(player, "contact", ATTRIBUTE_DEFAULTS["contact"]),
        fielding=_safe_attr_value(player, "fielding", ATTRIBUTE_DEFAULTS["fielding"]),
        speed=_safe_attr_value(player, "speed", ATTRIBUTE_DEFAULTS["speed"]),
        throwing=_safe_attr_value(player, "throwing", ATTRIBUTE_DEFAULTS["throwing"]),
        catcher_leadership=_safe_attr_value(player, "catcher_leadership", ATTRIBUTE_DEFAULTS["catcher_leadership"]),
        mental=_safe_attr_value(player, "mental", ATTRIBUTE_DEFAULTS["mental"]),
        overall=_safe_attr_value(player, "overall", ATTRIBUTE_DEFAULTS["overall"]),
        clutch=_safe_attr_value(player, "clutch", ATTRIBUTE_DEFAULTS["clutch"]),
        innings_pitched=float(totals["innings_pitched"]),
        runs_allowed=int(totals["runs_allowed"]),
        home_runs=int(totals["home_runs"]),
        at_bats=int(totals["at_bats"]),
        hits=int(totals["hits"]),
        era=totals["era"],
        batting_average=float(totals["batting_average"]),
    )


@lru_cache(maxsize=1)
def _load_epilogue_templates() -> List[Dict[str, Any]]:
    data_path = Path(__file__).resolve().parents[2] / "data" / "epilogues.json"
    if not data_path.exists():
        logger.warning("Epilogue template file missing at %s", data_path)
        return []
    try:
        with data_path.open("r", encoding="utf-8") as handle:
            return json.load(handle) or []
    except Exception:
        logger.exception("Failed to load epilogue templates")
        return []


def _build_story_context(profile: PlayerProfile) -> Dict[str, Any]:
    player = profile.player
    school = profile.school
    first = getattr(player, "first_name", None) or (player.name.split(" ")[0] if player.name else "")
    last = getattr(player, "last_name", None) or (player.name.split(" ")[-1] if player.name else "Player")
    school_name = school.name if school else "his school"

    innings = profile.innings_pitched
    era = profile.era
    batting_average = profile.batting_average
    titles = profile.titles
    at_bats = profile.at_bats

    if titles <= 0:
        titles_text = "no"
    elif titles == 1:
        titles_text = "one"
    else:
        titles_text = str(titles)

    return {
        "player_first": first or last,
        "player_last": last,
        "player_full": player.name or f"{first} {last}".strip(),
        "school_name": school_name,
        "titles_text": titles_text,
        "era_text": "N/A" if era is None else f"{era:.2f}",
        "innings_text": f"{innings:.1f}" if innings else "0.0",
        "hr_text": str(profile.home_runs),
        "avg_text": f"{batting_average:.3f}" if at_bats else ".000",
        "color_gold": getattr(Colour, "gold", Colour.GOLD if hasattr(Colour, "GOLD") else Colour.YELLOW),
        "color_reset": Colour.RESET,
    }


def _resolve_colour(code: Optional[str]) -> str:
    mapping = {
        "gold": getattr(Colour, "gold", getattr(Colour, "GOLD", Colour.YELLOW)),
        "cyan": Colour.CYAN,
        "green": Colour.GREEN,
        "blue": Colour.BLUE,
        "yellow": Colour.YELLOW,
        "red": Colour.RED,
        "reset": Colour.RESET,
        "fail": getattr(Colour, "FAIL", Colour.RED),
        "magenta": getattr(Colour, "HEADER", Colour.MAG if hasattr(Colour, "MAG") else Colour.RESET),
    }
    if not code:
        return Colour.RESET
    return mapping.get(code.lower(), Colour.RESET)


FIELD_MAP = {
    "total_score": "overall",
    "prestige": "prestige",
    "titles": "titles",
    "hr": "home_runs",
    "innings": "innings_pitched",
    "era": "era",
    "batting_avg": "batting_average",
    "velocity": "velocity",
    "control": "control",
    "command": "command",
    "movement": "movement",
    "stamina": "stamina",
    "power": "power",
    "contact": "contact",
    "fielding": "fielding",
    "speed": "speed",
    "throwing": "throwing",
    "catcher_leadership": "catcher_leadership",
    "mental": "mental",
    "overall": "overall",
    "clutch": "clutch",
}


def _template_matches(template: Dict[str, Any], profile: PlayerProfile) -> bool:
    conditions = template.get("conditions") or {}
    if not conditions:
        return True

    for key, requirement in conditions.items():
        if key == "positions":
            if not any(pos in profile.positions for pos in requirement):
                return False
            continue
        if key == "requires_two_way":
            if requirement and not profile.is_two_way:
                return False
            continue
        if key == "requires_injured":
            if requirement and not profile.is_injured:
                return False
            continue
        if key == "growth_tags":
            if profile.growth_tag not in requirement:
                return False
            continue

        if key.startswith("min_") or key.startswith("max_"):
            prefix, field_key = key.split("_", 1)
            mapped = FIELD_MAP.get(field_key)
            if not mapped:
                continue
            value = getattr(profile, mapped, None)
            if value is None:
                return False
            if prefix == "min" and value < requirement:
                return False
            if prefix == "max" and value > requirement:
                return False
            continue

    return True


def _select_epilogue_template(profile: PlayerProfile) -> Optional[Dict[str, Any]]:
    for template in _load_epilogue_templates():
        if _template_matches(template, profile):
            return template
    return None


def _format_story(template: Dict[str, Any], context: Dict[str, Any]) -> str:
    lines = template.get("story", [])
    formatted = [line.format(**context) for line in lines]
    return "\n".join(formatted)


def _fallback_story(player: Player, school: Optional[School]) -> Tuple[str, str, str, str]:
    last_name = getattr(player, "last_name", None) or player.name or "Player"
    school_name = school.name if school else "his school"
    story = (
        f"With the final out of summer, {last_name} left his glove on the field.\n"
        f"He went on to university after graduating from {school_name}, studied economics, and became a salaryman.\n"
        "Sometimes, when drinking with colleagues, he talks about that one hot summer\n"
        "when he chased a dream at Koshien."
    )
    return ("RETIRED", "A fond memory of youth.", Colour.RESET, story)


def determine_career_outcome(player: Player, school: Optional[School], session) -> Tuple[str, str, str, str]:
    if not school and getattr(player, "school_id", None):
        school = session.query(School).get(player.school_id)

    profile = _build_player_profile(player, school, session)
    template = _select_epilogue_template(profile)
    if template:
        context = _build_story_context(profile)
        story = _format_story(template, context)
        color = _resolve_colour(template.get("color"))
        return (
            template.get("title", "EPILOGUE"),
            template.get("summary", ""),
            color,
            story,
        )

    return _fallback_story(player, school)


def play_ending_sequence(
    title: str,
    desc: str,
    color: str,
    story: str,
    *,
    event_bus: Optional[EventBus] = None,
    events: Optional[List[Dict[str, Any]]] = None,
) -> None:
    events = events if events is not None else []
    _emit_event(
        event_bus,
        events,
        "SEASON_EPILOGUE",
        {
            "title": title,
            "description": desc,
            "color": color,
            "story_lines": story.split("\n"),
        },
    )


def _ensure_game_state(session) -> GameState:
    state = session.query(GameState).first()
    if state:
        return state
    state = GameState(current_year=2024, current_month=4, current_week=1)
    session.add(state)
    session.commit()
    return state


def run_end_of_season_logic(
    session: Optional[Any] = None,
    user_player_id: Optional[int] = None,
    *,
    event_bus: Optional[EventBus] = None,
) -> SeasonEndResult:
    events: List[Dict[str, Any]] = []
    owns_session = session is None
    session = session or get_session()

    try:
        user_graduated = False
        if user_player_id:
            user = session.get(Player, user_player_id)
            if user and getattr(user, "year", None) == 3:
                user_graduated = True
                school = user.school or session.query(School).get(user.school_id)
                title, desc, color, story = determine_career_outcome(user, school, session)
                play_ending_sequence(title, desc, color, story, event_bus=event_bus, events=events)

        if user_graduated:
            return SeasonEndResult(True, events)

        _emit_event(
            event_bus,
            events,
            "SEASON_LOG",
            {"text": "=== END OF SEASON PROCESSING ===", "level": "header"},
        )

        _emit_event(event_bus, events, "SEASON_LOG", {"text": "3rd Years are graduating...", "level": "info"})
        graduates = graduate_third_years(session)
        session.commit()
        _emit_event(
            event_bus,
            events,
            "SEASON_LOG",
            {"text": f"{graduates} players tossed their caps.", "level": "detail"},
        )

        _emit_event(
            event_bus,
            events,
            "SEASON_LOG",
            {"text": "Offseason physical growth occurring...", "level": "info"},
        )
        roster_map = get_rosters(session, [sid for (sid,) in session.query(School.id).all()])
        players: Iterable[Player] = [p for roster in roster_map.values() for p in roster]
        apply_physical_growth(players)
        session.commit()

        _emit_event(
            event_bus,
            events,
            "SEASON_LOG",
            {"text": "Scouting new freshmen for 4000 schools (simulated)...", "level": "info"},
        )
        new_player_count = recruit_freshmen(session)
        _emit_event(
            event_bus,
            events,
            "SEASON_LOG",
            {"text": f"Welcome to {new_player_count} new freshmen.", "level": "detail"},
        )

        state = _ensure_game_state(session)
        state.current_year = (state.current_year or 2024) + 1
        state.current_month = 4
        state.current_week = 1
        session.commit()

        _emit_event(
            event_bus,
            events,
            "SEASON_LOG",
            {"text": f"=== SEASON {state.current_year} START ===", "level": "success"},
        )
        return SeasonEndResult(False, events)
    finally:
        if owns_session:
            session.close()
