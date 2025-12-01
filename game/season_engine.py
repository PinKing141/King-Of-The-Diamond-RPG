import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# Ensure project root is importable
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.setup_db import (
    GameState,
    Player,
    PlayerGameStats,
    School,
    get_session,
)
from game.offseason_engine import (
    apply_physical_growth,
    graduate_third_years,
    recruit_freshmen,
)
from ui.ui_display import Colour, clear_screen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EPILOGUE_DATA_PATH = PROJECT_ROOT / "data" / "epilogues.json"
_EPILOGUE_CACHE: Optional[List[Dict[str, Any]]] = None

ATTRIBUTE_DEFAULTS = {
    "velocity": 0,
    "control": 50,
    "stamina": 50,
    "movement": 50,
    "contact": 50,
    "power": 50,
    "fielding": 50,
    "speed": 50,
    "throwing": 50,
    "command": 50,
    "catcher_leadership": 50,
    "mental": 50,
    "overall": 50,
    "clutch": 50,
}


def _safe_attr_value(player: Player, attr: str, default: int) -> int:
    value = getattr(player, attr, None)
    return value if value is not None else default


def _estimate_total_score(player: Player) -> int:
    return _safe_attr_value(player, "overall", 50)


def _estimate_titles(school: Optional[School]) -> int:
    if not school:
        return 0
    prestige = school.prestige or 0
    if prestige >= 80:
        return 2
    if prestige >= 60:
        return 1
    return 0


def _load_epilogue_templates() -> List[Dict[str, Any]]:
    global _EPILOGUE_CACHE
    if _EPILOGUE_CACHE is None:
        with EPILOGUE_DATA_PATH.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        # Highest priority first
        _EPILOGUE_CACHE = sorted(
            data,
            key=lambda item: item.get("priority", 0),
            reverse=True,
        )
    return _EPILOGUE_CACHE


def _aggregate_player_stats(session, player: Player) -> Dict[str, Any]:
    rows: Sequence[PlayerGameStats] = (
        session.query(PlayerGameStats)
        .filter(PlayerGameStats.player_id == player.id)
        .all()
    )

    innings = sum(row.innings_pitched or 0 for row in rows)
    runs_allowed = sum((row.runs_allowed if row.runs_allowed is not None else row.runs or 0) for row in rows)
    home_runs = sum(row.homeruns or 0 for row in rows)
    at_bats = sum(row.at_bats or 0 for row in rows)
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


def _build_player_profile(player: Player, school: Optional[School], session) -> Dict[str, Any]:
    stats = _aggregate_player_stats(session, player)
    total_score = _estimate_total_score(player)
    prestige = school.prestige if school else 0
    growth_tag = getattr(player, "growth_tag", "Normal")

    is_two_way = bool(getattr(player, "is_two_way", False))
    secondary = getattr(player, "secondary_position", None)
    if secondary and secondary != player.position:
        is_two_way = True

    return {
        "player": player,
        "school": school,
        "position": player.position,
        "secondary_position": secondary,
        "positions": {player.position, secondary} if secondary else {player.position},
        "is_two_way": is_two_way,
        "is_injured": (player.injury_status or "").lower() not in ("", "healthy"),
        "growth_tag": growth_tag,
        "total_score": total_score,
        "prestige": prestige or 0,
        "titles": _estimate_titles(school),
        "velocity": _safe_attr_value(player, "velocity", ATTRIBUTE_DEFAULTS["velocity"]),
        "control": _safe_attr_value(player, "control", ATTRIBUTE_DEFAULTS["control"]),
        "command": _safe_attr_value(player, "command", ATTRIBUTE_DEFAULTS["command"]),
        "movement": _safe_attr_value(player, "movement", ATTRIBUTE_DEFAULTS["movement"]),
        "stamina": _safe_attr_value(player, "stamina", ATTRIBUTE_DEFAULTS["stamina"]),
        "power": _safe_attr_value(player, "power", ATTRIBUTE_DEFAULTS["power"]),
        "contact": _safe_attr_value(player, "contact", ATTRIBUTE_DEFAULTS["contact"]),
        "fielding": _safe_attr_value(player, "fielding", ATTRIBUTE_DEFAULTS["fielding"]),
        "speed": _safe_attr_value(player, "speed", ATTRIBUTE_DEFAULTS["speed"]),
        "throwing": _safe_attr_value(player, "throwing", ATTRIBUTE_DEFAULTS["throwing"]),
        "catcher_leadership": _safe_attr_value(player, "catcher_leadership", ATTRIBUTE_DEFAULTS["catcher_leadership"]),
        "mental": _safe_attr_value(player, "mental", ATTRIBUTE_DEFAULTS["mental"]),
        "overall": _safe_attr_value(player, "overall", ATTRIBUTE_DEFAULTS["overall"]),
        "clutch": _safe_attr_value(player, "clutch", ATTRIBUTE_DEFAULTS["clutch"]),
        **stats,
    }


def _build_story_context(player: Player, school: Optional[School], profile: Dict[str, Any]) -> Dict[str, Any]:
    first = player.first_name or (player.name.split(" ")[0] if player.name else "")
    last = player.last_name or (player.name.split(" ")[-1] if player.name else "Player")
    school_name = school.name if school else "his school"

    innings = profile.get("innings_pitched", 0)
    era = profile.get("era")
    batting_average = profile.get("batting_average", 0.0)
    titles = profile.get("titles", 0)
    at_bats = profile.get("at_bats", 0)

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
        "hr_text": str(profile.get("home_runs", 0)),
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


def _template_matches(template: Dict[str, Any], profile: Dict[str, Any]) -> bool:
    conditions = template.get("conditions") or {}
    if not conditions:
        return True

    for key, requirement in conditions.items():
        if key == "positions":
            if not any(pos in profile["positions"] for pos in requirement):
                return False
            continue
        if key == "requires_two_way":
            if requirement and not profile.get("is_two_way"):
                return False
            continue
        if key == "requires_injured":
            if requirement and not profile.get("is_injured"):
                return False
            continue
        if key == "growth_tags":
            if profile.get("growth_tag") not in requirement:
                return False
            continue

        if key.startswith("min_") or key.startswith("max_"):
            prefix, field_key = key.split("_", 1)
            mapped = FIELD_MAP.get(field_key)
            if not mapped:
                continue
            value = profile.get(mapped)
            if value is None:
                return False
            if prefix == "min" and value < requirement:
                return False
            if prefix == "max" and value > requirement:
                return False
            continue

    return True


def _select_epilogue_template(profile: Dict[str, Any]) -> Optional[Dict[str, Any]]:
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
        context = _build_story_context(player, school, profile)
        story = _format_story(template, context)
        color = _resolve_colour(template.get("color"))
        return (
            template.get("title", "EPILOGUE"),
            template.get("summary", ""),
            color,
            story,
        )

    return _fallback_story(player, school)


def play_ending_sequence(title: str, desc: str, color: str, story: str) -> None:
    clear_screen()
    print("\n\n")
    time.sleep(1)
    print(f"    {color}--- EPILOGUE ---{Colour.RESET}")
    time.sleep(2)
    print(f"\n    {title}")
    time.sleep(1.5)
    print(f"    {desc}")
    time.sleep(2)
    print("\n" + "=" * 60 + "\n")
    for line in story.split("\n"):
        print(f"    {line}")
        time.sleep(2.5)
    print("\n" + "=" * 60 + "\n")
    time.sleep(3)
    input("    [Press Enter to close the book on this legend...]")


def _ensure_game_state(session) -> GameState:
    state = session.query(GameState).first()
    if state:
        return state
    state = GameState(current_year=2024, current_month=4, current_week=1)
    session.add(state)
    session.commit()
    return state


def run_end_of_season_logic(user_player_id: Optional[int] = None) -> bool:
    session = get_session()
    try:
        user_graduated = False
        if user_player_id:
            user = session.query(Player).get(user_player_id)
            if user and user.year == 3:
                user_graduated = True
                school = user.school or session.query(School).get(user.school_id)
                title, desc, color, story = determine_career_outcome(user, school, session)
                play_ending_sequence(title, desc, color, story)

        if user_graduated:
            return True

        print(f"\n{Colour.HEADER}=== END OF SEASON PROCESSING ==={Colour.RESET}")

        print(" > 3rd Years are graduating...")
        graduates = graduate_third_years(session)
        session.commit()
        print(f"   ({graduates} players tossed their caps.)")

        print(" > Offseason physical growth occurring...")
        players: Iterable[Player] = session.query(Player).all()
        apply_physical_growth(players)
        session.commit()

        print(" > Scouting new freshmen for 4000 schools (simulated)...")
        new_player_count = recruit_freshmen(session)
        print(f"   (Welcome to {new_player_count} new freshmen.)")

        state = _ensure_game_state(session)
        state.current_year = (state.current_year or 2024) + 1
        state.current_month = 4
        state.current_week = 1
        session.commit()

        print(f"\n{Colour.gold}=== SEASON {state.current_year} START ==={Colour.RESET}")
        return False
    finally:
        session.close()