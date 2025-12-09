"""Tournament simulation for Koshien and Senbatsu tournaments (IO-light).

Presentation is routed through ``IOInterface`` when provided. Callers may also
pass an ``events`` list to collect structured snapshots for UI layers.
"""
import json
import logging
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import object_session

from core.io_interface import IOInterface
from core.paths import data_path, load_json_resource
from core.rng import get_rng
from database.setup_db import GameState, Player, PlayerRelationship, School, session_scope
from game.mechanics.pitch_minigame import (
    PitchMinigameContext,
    PitchMinigameResult,
    trigger_pitch_minigame,
)
from match_engine.resolver import resolve_match
from ui.ui_display import clear_screen
from world_sim.services.sim_data import get_strength_map, get_rosters, get_roster
from world_sim.services.sim_logging import log_event
from world_sim.strength_cache import strength_cache_scope
from .sim_utils import quick_resolve_match, clear_strength_cache


logger = logging.getLogger(__name__)


def _safe_input(prompt: str, default: str = "") -> str:
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt):
        return default


def _prompt(io: IOInterface | None, prompt: str, default: str = "") -> str:
    if io:
        try:
            return io.prompt(prompt)
        except (RuntimeError, ValueError, OSError) as exc:
            logger.warning("io prompt failed; falling back to stdin: %s", exc)
    return _safe_input(prompt, default=default)


def _log(io: IOInterface | None, message: str, *, level: str = "info") -> None:
    if io:
        io.log(message, level=level)
    else:
        getattr(logger, level, logger.info)(message)


def _clear(io: IOInterface | None) -> None:
    clear_fn = getattr(io, "clear", None) if io else None
    if callable(clear_fn):
        clear_fn()
    else:
        clear_screen()

rng = get_rng()
REGISTERED_DIALOGUE_IDS: Set[str] = set()
_DIALOGUE_LIBRARY: Dict[str, Dict[str, Any]] = {}
_DIALOGUE_PATH = data_path("dialogues.json")


def _register_dialogue(dialogue_id: str) -> str:
    REGISTERED_DIALOGUE_IDS.add(dialogue_id)
    return dialogue_id


DIALOGUE_COACH_MEETING = _register_dialogue("coach_meeting_strategy")
DIALOGUE_CAPTAIN_HIGH = _register_dialogue("captain_advice_high")
DIALOGUE_CAPTAIN_LOW = _register_dialogue("captain_advice_low")
DIALOGUE_TEAM_PRACTICE = _register_dialogue("teammate_practice_extra")
RIVAL_DIALOGUE_POOL = [
    _register_dialogue("rival_head_to_head"),
    _register_dialogue("rival_mind_games"),
]
DIALOGUE_CROWD_CHANTING = _register_dialogue("crowd_chanting_hero")
DIALOGUE_CROWD_SILENT = _register_dialogue("crowd_deadly_silent")


def _load_dialogues() -> None:
    global _DIALOGUE_LIBRARY
    if _DIALOGUE_LIBRARY:
        return
    payload = load_json_resource("data", "dialogues.json")
    if payload is None:
        try:
            with _DIALOGUE_PATH.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError, json.JSONDecodeError):
            _DIALOGUE_LIBRARY = {}
            return
    _DIALOGUE_LIBRARY = {entry.get("id"): entry for entry in payload if isinstance(entry, dict) and entry.get("id")}


def _get_dialogue(dialogue_id: str) -> Optional[Dict[str, Any]]:
    if not _DIALOGUE_LIBRARY:
        _load_dialogues()
    return _DIALOGUE_LIBRARY.get(dialogue_id)


def _play_dialogue(dialogue_id: str, *, io: IOInterface | None = None) -> None:
    dialogue = _get_dialogue(dialogue_id)
    if not dialogue:
        return
    speaker = dialogue.get("speaker", "Narrator")
    text = dialogue.get("text", "")
    _log(io, f"\n{speaker}: {text}\n")
    options = dialogue.get("options") or []
    if not options:
        _prompt(io, "Press Enter to continue...")
        return
    for idx, option in enumerate(options, start=1):
        _log(io, f"  {idx}. {option.get('text', '...')}")
    choice = 0
    while choice < 1 or choice > len(options):
        raw = _prompt(io, "Choose a response (default 1): ", default="1").strip()
        if not raw:
            choice = 1
            break
        if raw.isdigit():
            choice = int(raw)
    selected = options[choice - 1]
    response = selected.get("response")
    if response:
        _log(io, f"\n{response}\n")
    _prompt(io, "Press Enter to continue...")


def run_koshien_tournament(
    user_school_id,
    participants=None,
    *,
    session,
    context=None,
    io: IOInterface | None = None,
    events: Optional[List[Dict[str, object]]] = None,
):
    """Summer Koshien: 49 Teams (qualifier winners).

    Requires a caller-managed session to avoid spawning nested connections mid-season.
    """

    if session is None:
        raise ValueError("session is required when running Koshien tournaments")

    return _run_generic_tournament(
        "SUMMER KOSHIEN",
        user_school_id,
        participants,
        session,
        context=context,
        io=io,
        events=events,
    )


def run_spring_koshien(
    user_school_id,
    *,
    session,
    context=None,
    qualifiers=None,
    io: IOInterface | None = None,
    events: Optional[List[Dict[str, object]]] = None,
):
    """Spring Koshien (Senbatsu): invitational 32-team tournament.

    Requires a caller-managed session to stay aligned with the game loop's connection.
    """

    if session is None:
        raise ValueError("session is required when running Spring Koshien")

    _clear(io)
    _log(io, "=== SPRING SENBATSU (INVITATIONAL) SELECTION ===\n")

    qualifier_ids = qualifiers or []
    if isinstance(qualifier_ids, str):
        try:
            qualifier_ids = json.loads(qualifier_ids)
        except ValueError:
            qualifier_ids = []
    if not qualifier_ids and context:
        qualifier_ids = context.get_temp_effect("spring_qualifier_ids", [])

    participants = _load_spring_invitees(session, qualifier_ids, user_school_id)
    user_school = session.get(School, user_school_id)
    user_qualified = any(s.id == user_school_id for s in participants)

    if qualifier_ids:
        if user_qualified:
            _log(io, "Invitation secured via Autumn Regionals!")
        else:
            _log(io, "Autumn run fell short; prestige may still earn a bid.")
    else:
        if user_qualified:
            _log(io, "INVITATION RECEIVED! The committee selected your school.")
        else:
            _log(io, f"No invitation received. Prestige {getattr(user_school, 'prestige', 0)} was not enough.")
            _log(io, "You watch the Spring tournament from home...")

    _prompt(io, "Press Enter to continue...")

    return _run_generic_tournament(
        "SPRING SENBATSU",
        user_school_id,
        participants,
        session,
        context=context,
        io=io,
        events=events,
    )


def _load_spring_invitees(session, qualifier_ids: Optional[List[int]], user_school_id: int) -> List[School]:
    """Load Spring invitees; pad with prestige seeds if needed."""

    if qualifier_ids:
        qualifiers = session.query(School).filter(School.id.in_(qualifier_ids)).all()
    else:
        qualifiers = []

    invited_ids = {s.id for s in qualifiers}
    if len(qualifiers) < 32:
        needed = 32 - len(qualifiers)
        extras = (
            session.query(School)
            .filter(~School.id.in_(invited_ids))
            .order_by(School.prestige.desc())
            .limit(needed)
            .all()
        )
        qualifiers.extend(extras)

    return qualifiers[:32]

def _run_generic_tournament(
    title,
    user_school_id,
    participants,
    session,
    context=None,
    *,
    io: IOInterface | None = None,
    events: Optional[List[Dict[str, object]]] = None,
):
    """Shared logic for running any single-elimination bracket."""

    with strength_cache_scope() as cache:
        _clear(io)
        _log(io, f"=== {title} BEGINS ===\n")

        clear_strength_cache(cache)

        user_school = session.get(School, user_school_id)
        listeners: Optional[Sequence] = getattr(context, "match_event_listeners", None) if context else None

        if not participants:
            npcs = session.query(School).filter(School.id != user_school_id).all()
            participants = rng.sample(npcs, 15)
            participants.append(user_school)

        current_bracket = list(participants)
        rng.shuffle(current_bracket)

        if len(current_bracket) > 32:
            current_bracket = current_bracket[:32]
        elif len(current_bracket) > 16:
            current_bracket = current_bracket[:16]

        roster_map = get_rosters(session, [sid for s in current_bracket if (sid := getattr(s, "id", None)) is not None])
        strength_map = get_strength_map(
            session,
            school_ids=[sid for s in current_bracket if (sid := getattr(s, "id", None)) is not None],
            cache=cache,
        )

        if events is not None:
            events.append({"type": "tournament_start", "title": title, "participants": len(current_bracket)})

        round_num = 1

        while len(current_bracket) > 1:
            next_round: List[School] = []
            _log(io, f"\n--- ROUND {round_num} ({len(current_bracket)} Teams) ---")

            matchups = []
            for i in range(0, len(current_bracket), 2):
                if i + 1 < len(current_bracket):
                    matchups.append((current_bracket[i], current_bracket[i + 1]))

            for home, away in matchups:
                is_user_match = (home.id == user_school_id or away.id == user_school_id)

                _log(io, f" > Match: {home.name} vs {away.name}")

                rival_ctx = context.get_temp_effect("rival_match_context") if context else None
                rival_presentation = context.get_temp_effect("rival_presentation") if context else None

                if is_user_match:
                    _run_pre_match_story(round_num, user_school, io=io)
                    opponent = away if home.id == user_school_id else home
                    _maybe_inject_rival_dialogue(session, user_school_id, opponent, io=io)

                winner = None
                score = ""

                leverage_result: Optional[PitchMinigameResult] = None
                clutch_payload: Optional[Dict[str, Any]] = None
                if is_user_match:
                    leverage_result = _maybe_trigger_pitch_minigame(
                        home,
                        away,
                        user_school_id,
                        round_num,
                        title,
                        io=io,
                    )
                    clutch_payload = _build_clutch_payload(leverage_result, user_school_id, home, away)

                if is_user_match:
                    _log(io, "   *** YOUR MATCH ***")
                    if leverage_result:
                        winner, score = resolve_match(
                            home,
                            away,
                            f"{title} Round {round_num}",
                            mode="standard",
                            silent=False,
                            clutch_pitch=clutch_payload,
                            rival_match_context=rival_ctx,
                            rival_presentation=rival_presentation,
                            session=session,
                            event_listeners=listeners,
                        )
                    else:
                        winner, score = resolve_match(
                            home,
                            away,
                            f"{title} Round {round_num}",
                            mode="fast",
                            rival_match_context=rival_ctx,
                            rival_presentation=rival_presentation,
                            session=session,
                            event_listeners=listeners,
                        )
                        _log(io, f"   Result: {winner.name} wins! ({score})")
                else:
                    winner, score, upset, *_ids = quick_resolve_match(
                        session,
                        home,
                        away,
                        strength_map=strength_map,
                        cache=cache,
                    )
                    note = " (UPSET)" if upset else ""
                    _log(io, f"   Result: {winner.name} wins! ({score}){note}")

                log_event(
                    "tournament_match_resolved",
                    title=title,
                    round=round_num,
                    home_id=getattr(home, "id", None),
                    away_id=getattr(away, "id", None),
                    winner_id=getattr(winner, "id", None),
                    score=score,
                    user_match=is_user_match,
                    upset=bool(locals().get("upset", False)),
                )

                next_round.append(winner)

                if events is not None:
                    events.append(
                        {
                            "type": "tournament_match",
                            "title": title,
                            "round": round_num,
                            "home": getattr(home, "id", None),
                            "away": getattr(away, "id", None),
                            "winner": getattr(winner, "id", None),
                            "score": score,
                            "user_match": is_user_match,
                        }
                    )

                if is_user_match and winner.id != user_school_id:
                    _log(io, "\nYou have been eliminated.")
                    _prompt(io, "Press Enter...")
                    if events is not None:
                        events.append({"type": "tournament_elimination", "title": title, "round": round_num})
                    return winner

            current_bracket = next_round

            # Refresh rosters and strengths each round to reflect fatigue/injuries from resolved matches.
            roster_map = get_rosters(
                session,
                [sid for s in current_bracket if (sid := getattr(s, "id", None)) is not None],
            )
            strength_map = get_strength_map(
                session,
                school_ids=[sid for s in current_bracket if (sid := getattr(s, "id", None)) is not None],
                cache=cache,
            )

            _handle_between_round_story(session, user_school_id, current_bracket, roster_map=roster_map, io=io)

            round_num += 1

        winner = current_bracket[0]

        if winner.id == user_school_id:
            _log(io, f"\nCONGRATULATIONS! YOU WON {title}!")
            user_school.prestige += 15
            session.commit()
        else:
            _log(io, f"\nWinner: {winner.name}")

        if events is not None:
            events.append({"type": "tournament_complete", "title": title, "champion": getattr(winner, "id", None)})
        log_event("tournament_complete", title=title, champion_id=getattr(winner, "id", None))
        return winner


def _run_pre_match_story(round_num: int, user_school: Optional[School], *, io: IOInterface | None = None) -> None:
    if not user_school:
        return
    if round_num <= 1:
        _play_dialogue(DIALOGUE_COACH_MEETING, io=io)
        return
    prestige = getattr(user_school, "prestige", 0) or 0
    dialogue_id = DIALOGUE_CAPTAIN_HIGH if prestige >= 55 else DIALOGUE_CAPTAIN_LOW
    _play_dialogue(dialogue_id, io=io)


def _handle_between_round_story(
    session,
    user_school_id: int,
    bracket: List[School],
    *,
    roster_map: Optional[Dict[int, Sequence[Player]]] = None,
    io: IOInterface | None = None,
) -> None:
    if not bracket or len(bracket) <= 1:
        return
    if not any(getattr(school, "id", None) == user_school_id for school in bracket):
        return
    snapshot = _team_fatigue_snapshot(session, user_school_id, roster_map=roster_map)
    if not snapshot:
        return
    avg_fatigue, avg_stamina = snapshot
    if avg_fatigue >= 65 and avg_stamina <= 55:
        _log(io, "\nPlayers are gassed after that last round. Coaches cancel optional reps to preserve arms.")
        _log(io, f"   Avg fatigue: {avg_fatigue:.1f}% | Avg stamina: {avg_stamina:.1f}")
        _prompt(io, "Press Enter to continue...")
        return
    _play_dialogue(DIALOGUE_TEAM_PRACTICE, io=io)


def _team_fatigue_snapshot(
    session,
    school_id: int,
    *,
    roster_map: Optional[Dict[int, Sequence[Player]]] = None,
) -> Optional[Tuple[float, float]]:
    players = roster_map.get(school_id) if roster_map else None
    if players is None:
        try:
            players = get_roster(session, school_id)
        except SQLAlchemyError as exc:
            logger.warning("fatigue snapshot failed for school %s: %s", school_id, exc)
            return None
    if not players:
        return None
    total_fatigue = sum(max(0, getattr(player, "fatigue", 0) or 0) for player in players)
    total_stamina = sum(max(0, getattr(player, "stamina", 0) or 0) for player in players)
    count = len(players)
    return (total_fatigue / count, total_stamina / count)


def _maybe_trigger_pitch_minigame(
    home: School,
    away: School,
    user_school_id: int,
    round_num: int,
    title: str,
    *,
    io: IOInterface | None = None,
) -> Optional[PitchMinigameResult]:
    inning = rng.choice([6, 7, 8, 9])
    half = rng.choice(["Top", "Bot"])
    runners_on = rng.choice([0, 1, 2, 3])
    score_diff = rng.choice([0, 1])
    if not _is_high_leverage(inning, score_diff, runners_on):
        return None
    if not _is_user_pitching(user_school_id, home, away, half):
        return None

    _log(io, "   High leverage moment! Coach signals for the pitch minigame.")

    scenario = PitchMinigameContext(
        inning=inning,
        half=half,
        count=rng.choice(["3-2", "2-2", "1-2"]),
        runners_on=runners_on,
        score_diff=score_diff,
        label=f"{title} Round {round_num}",
    )
    _maybe_play_bottom9_story(scenario, io=io)
    school = home if home.id == user_school_id else away
    control, fatigue = _estimate_pitcher_profile(school)
    difficulty = _clamp(0.35 + (round_num - 1) * 0.08, 0.2, 1.0)
    result = trigger_pitch_minigame(
        inning=scenario.inning,
        half=scenario.half,
        count=scenario.count,
        runners_on=scenario.runners_on,
        score_diff=scenario.score_diff,
        label=scenario.label,
        control_stat=control,
        fatigue_level=fatigue,
        difficulty=difficulty,
    )
    _announce_minigame_outcome(result, io=io)
    return result


def _build_clutch_payload(
    result: Optional[PitchMinigameResult],
    user_school_id: int,
    home: School,
    away: School,
) -> Optional[Dict[str, Any]]:
    if not result:
        return None
    if home.id == user_school_id:
        team = home
        side = "home"
    elif away.id == user_school_id:
        team = away
        side = "away"
    else:
        return None
    context = result.context
    quality = result.quality
    force_result = None
    if quality >= 0.9:
        force_result = "strikeout"
        quality = max(quality, 0.98)
    elif quality >= 0.8:
        force_result = "strike"
        quality = max(quality, 0.93)

    payload = {
        "team_id": getattr(team, "id", None),
        "team_name": getattr(team, "name", None),
        "team_side": side,
        "quality": round(quality, 3),
        "feedback": result.feedback,
        "deviation": result.deviation,
        "difficulty": result.difficulty,
        "target_window": result.target_window,
        "context": {
            "inning": context.inning,
            "half": context.half,
            "count": context.count,
            "runners_on": context.runners_on,
            "score_diff": context.score_diff,
            "label": context.label,
        },
    }
    if force_result:
        payload["force_result"] = force_result
    return payload


def _estimate_pitcher_profile(school: School) -> tuple[int, int]:
    candidates = []
    try:
        candidates = [
            player
            for player in getattr(school, "players", []) or []
            if (getattr(player, "position", "") or "").lower() in {"pitcher", "two-way", "two way"}
        ]
    except (AttributeError, TypeError) as exc:
        logger.warning("pitcher profile: failed to read related players for school %s: %s", getattr(school, "id", None), exc)

    if not candidates:
        try:
            sess = object_session(school)
            sid = getattr(school, "id", None)
            if sess and sid is not None:
                roster = get_roster(sess, sid)
                candidates = [
                    p
                    for p in roster
                    if (getattr(p, "position", "") or "").lower() in {"pitcher", "two-way", "two way"}
                ]
        except SQLAlchemyError as exc:
            logger.warning("pitcher profile: DB fallback failed for school %s: %s", getattr(school, "id", None), exc)

    if not candidates:
        return 60, 20
    ace = max(
        candidates,
        key=lambda player: (getattr(player, "control", 50) or 50) + (getattr(player, "stamina", 50) or 50),
    )
    return (getattr(ace, "control", 60) or 60), (getattr(ace, "fatigue", 0) or 0)


def _is_high_leverage(inning: int, score_diff: int, runners_on: int) -> bool:
    late = inning >= 7
    close = abs(score_diff) <= 1
    traffic = runners_on >= 2
    sudden_death = inning >= 9 and abs(score_diff) <= 2
    return (late and close) or traffic or sudden_death


def _is_user_pitching(user_school_id: int, home: School, away: School, half: str) -> bool:
    if (half or "Top").lower().startswith("t"):
        pitcher_school = home
    else:
        pitcher_school = away
    return getattr(pitcher_school, "id", None) == user_school_id


def _announce_minigame_outcome(result: PitchMinigameResult, *, io: IOInterface | None = None) -> None:
    _log(io, f"   Pitch Quality: {result.quality:.2f} | {result.feedback} (cursor delta {result.deviation:.2f})")


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _determine_rival_school_id(session) -> Optional[int]:
    state = session.query(GameState).first()
    if not state or not state.active_player_id:
        return None
    rel = session.query(PlayerRelationship).filter_by(player_id=state.active_player_id).one_or_none()
    if not rel or not rel.rival_id:
        return None
    rival = session.get(Player, rel.rival_id)
    return getattr(rival, "school_id", None)


def _maybe_inject_rival_dialogue(session, user_school_id: int, opponent: School, *, io: IOInterface | None = None) -> None:
    rival_school_id = _determine_rival_school_id(session)
    if not rival_school_id or opponent.id != rival_school_id:
        return
    dialogue_id = rng.choice(RIVAL_DIALOGUE_POOL)
    _play_dialogue(dialogue_id, io=io)


def _maybe_play_bottom9_story(context: PitchMinigameContext, *, io: IOInterface | None = None) -> None:
    if context.inning < 9 or (context.half or "").lower() != "bot":
        return
    if context.score_diff <= 0:
        _play_dialogue(DIALOGUE_CROWD_CHANTING, io=io)
    else:
        _play_dialogue(DIALOGUE_CROWD_SILENT, io=io)