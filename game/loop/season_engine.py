import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from database.setup_db import (
    GameState,
    Player,
    PlayerGameStats,
    School,
)
from world_sim.services.sim_data import get_rosters, get_roster
from game.loop.offseason_engine import (
    apply_physical_growth,
    graduate_third_years,
    recruit_freshmen,
        owns_session = session is None
        session = session or get_session()
        try:
            user_graduated = False
            if user_player_id:
                user = session.get(Player, user_player_id)
                if user and user.year == 3:
                    user_graduated = True
                    school = user.school or session.get(School, user.school_id)
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
                {"text": f"{graduates} players tossed their caps.", "level": "detail"},
            )

            _emit_event(event_bus, events, "SEASON_LOG", {"text": "Offseason physical growth occurring...", "level": "info"})
            roster_map = get_rosters(session, [s.id for s in session.query(School.id).all()])
            players: Iterable[Player] = [p for roster in roster_map.values() for p in roster]
            apply_physical_growth(players)
            session.commit()

            _emit_event(
                event_bus,
                events,
                {"text": "Scouting new freshmen for 4000 schools (simulated)...", "level": "info"},
            )
            new_player_count = recruit_freshmen(session)
            _emit_event(
                event_bus,
                events,
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
                {"text": f"=== SEASON {state.current_year} START ===", "level": "success"},
            )
            return SeasonEndResult(False, events)
        finally:
            if owns_session:
                session.close()
    events: List[Dict[str, Any]],
    event_type: str,
    payload: Dict[str, Any],
) -> None:
    event = {"type": event_type, "payload": payload}
    user_graduated = False
    if user_player_id:
        user = session.get(Player, user_player_id)
        if user and user.year == 3:
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

    _emit_event(event_bus, events, "SEASON_LOG", {"text": "Offseason physical growth occurring...", "level": "info"})
    roster_map = get_rosters(session, [s.id for s in session.query(School.id).all()])
    players: Iterable[Player] = [p for roster in roster_map.values() for p in roster]
    apply_physical_growth(players)
    session.commit()

    _emit_event(
        event_bus,
        events,
        "SEASON_LOG",
        {"text": "Off-season begins.", "level": "header"},
    )
    offseason_result = run_offseason_sequence(session, event_bus=event_bus)
    events.extend(offseason_result.events)

    return SeasonEndResult(False, events)
    hits = sum(row.hits_batted or 0 for row in rows)

    era = None
    if innings > 0:
        era = (runs_allowed * 9.0) / innings

    batting_average = (hits / at_bats) if at_bats > 0 else 0.0

    return {
        "innings_pitched": innings,
        "runs_allowed": runs_allowed,
        "home_runs": home_runs,
        "at_bats": at_bats,
        "hits": hits,
        "era": era,
        "batting_average": batting_average,
    }


def _build_player_profile(player: Player, school: Optional[School], session) -> PlayerProfile:
    stats = _aggregate_player_stats(session, player)
    total_score = _estimate_total_score(player)
    prestige = int(school.prestige or 0) if school else 0
    growth_tag = getattr(player, "growth_tag", "Normal")

    is_two_way = bool(getattr(player, "is_two_way", False))
    secondary = getattr(player, "secondary_position", None)
    if secondary and secondary != player.position:
        is_two_way = True

    positions = {pos for pos in (player.position, secondary) if pos}

    return PlayerProfile(
        player=player,
        school=school,
        position=player.position,
        secondary_position=secondary,
        positions=positions,
        is_two_way=is_two_way,
        is_injured=(player.injury_status or "").lower() not in ("", "healthy"),
        growth_tag=growth_tag,
        total_score=total_score,
        prestige=prestige,
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
        innings_pitched=float(stats["innings_pitched"]),
        runs_allowed=stats["runs_allowed"],
        home_runs=stats["home_runs"],
        at_bats=stats["at_bats"],
        hits=stats["hits"],
        era=stats["era"],
        batting_average=stats["batting_average"],
    )


def _build_story_context(profile: PlayerProfile) -> Dict[str, Any]:
    player = profile.player
    school = profile.school
    first = player.first_name or (player.name.split(" ")[0] if player.name else "")
    last = player.last_name or (player.name.split(" ")[-1] if player.name else "Player")
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

    context = {
        "player_first": first or last,
        "player_last": last,
        "player_full": player.name or f"{first} {last}".strip(),
        "school_name": school_name,
        "titles_text": titles_text,
        "era_text": "N/A" if era is None else f"{era:.2f}",
        "innings_text": f"{innings:.1f}" if innings else "0.0",
        "hr_text": str(profile.home_runs),
        "avg_text": f"{batting_average:.3f}" if at_bats else ".000",
        "color_gold": Colour.gold,
        "color_reset": Colour.RESET,
    }
    return context


def _resolve_colour(code: Optional[str]) -> str:
    mapping = {
        "gold": Colour.gold,
        "cyan": Colour.CYAN,
        "green": Colour.GREEN,
        "blue": Colour.BLUE,
        "yellow": Colour.YELLOW,
        "red": Colour.RED,
        "reset": Colour.RESET,
        "fail": Colour.FAIL,
        "magenta": Colour.HEADER,
    }
    if not code:
        return Colour.RESET
    return mapping.get(code.lower(), Colour.RESET)


FIELD_MAP = {
    "total_score": "total_score",
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
    last_name = player.last_name or player.name or "Player"
    school_name = school.name if school else "his school"
    story = (
        f"With the final out of summer, {last_name} left his glove on the field.\n"
        f"He went on to university after graduating from {school_name}, studied economics, and became a salaryman.\n"
        "Sometimes, when drinking with colleagues, he talks about that one hot summer\n"
        "when he chased a dream at Koshien."
    )
    return ("RETIRED", "A fond memory of youth.", Colour.RESET, story)


def determine_career_outcome(player: Player, school: Optional[School], session) -> Tuple[str, str, str, str]:
    if not school and player.school_id:
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
    session,
    user_player_id: Optional[int] = None,
    *,
    event_bus: Optional[EventBus] = None,
) -> SeasonEndResult:
    events: List[Dict[str, Any]] = []
    session = get_session()
    try:
        user_graduated = False
        if user_player_id:
            user = session.get(Player, user_player_id)
            if user and user.year == 3:
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

        _emit_event(event_bus, events, "SEASON_LOG", {"text": "Offseason physical growth occurring...", "level": "info"})
        roster_map = get_rosters(session, [s.id for s in session.query(School.id).all()])
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
        user_graduated = False
        if user_player_id:
            user = session.get(Player, user_player_id)
            if user and user.year == 3:
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

        _emit_event(event_bus, events, "SEASON_LOG", {"text": "Off-season begins.", "level": "header"})
        offseason_result = run_offseason_sequence(session, event_bus=event_bus)
        events.extend(offseason_result.events)

        return SeasonEndResult(False, events)