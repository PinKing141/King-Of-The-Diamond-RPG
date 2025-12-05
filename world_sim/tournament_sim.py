# world_sim/tournament_sim.py
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from database.setup_db import GameState, Player, PlayerRelationship, School, session_scope
from game.pitch_minigame import (
    PitchMinigameContext,
    PitchMinigameResult,
    trigger_pitch_minigame,
)
from game.rng import get_rng
from match_engine import resolve_match
from ui.ui_display import Colour, clear_screen
from .sim_utils import quick_resolve_match

rng = get_rng()
REGISTERED_DIALOGUE_IDS: Set[str] = set()
_DIALOGUE_LIBRARY: Dict[str, Dict[str, Any]] = {}
_DIALOGUE_PATH = Path(__file__).resolve().parents[1] / "data" / "dialogues.json"


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


def _play_dialogue(dialogue_id: str) -> None:
    dialogue = _get_dialogue(dialogue_id)
    if not dialogue:
        return
    speaker = dialogue.get("speaker", "Narrator")
    text = dialogue.get("text", "")
    print(f"\n{Colour.BOLD}{speaker}:{Colour.RESET} {text}\n")
    options = dialogue.get("options") or []
    if not options:
        input("Press Enter to continue...")
        return
    for idx, option in enumerate(options, start=1):
        print(f"  {idx}. {option.get('text', '...')}")
    choice = 0
    while choice < 1 or choice > len(options):
        raw = input("Choose a response (default 1): ").strip()
        if not raw:
            choice = 1
            break
        if raw.isdigit():
            choice = int(raw)
    selected = options[choice - 1]
    response = selected.get("response")
    if response:
        print(f"\n{response}\n")
    input("Press Enter to continue...")

def run_koshien_tournament(user_school_id, participants=None):
    """
    Summer Koshien: 49 Teams (Qualifiers Winners).
    """
    with session_scope() as session:
        _run_generic_tournament("SUMMER KOSHIEN", user_school_id, participants, session)

def run_spring_koshien(user_school_id):
    """
    Spring Koshien (Senbatsu): 32 Teams (Invitational).
    Selection is based on Prestige and Fall Performance (Simulated by Prestige here).
    """
    clear_screen()
    print(f"{Colour.HEADER}=== SPRING SENBATSU (INVITATIONAL) SELECTION ==={Colour.RESET}\n")
    
    with session_scope() as session:
        # 1. Select Top 32 Schools by Prestige
        # We exclude the user school initially to see if they make the cut naturally
        all_schools = session.query(School).order_by(School.prestige.desc()).all()
        
        # The cut-off line
        participants = all_schools[:32]
        
        # Check if user made it
        user_school = session.get(School, user_school_id)
        user_qualified = user_school in participants
        
        if user_qualified:
            print(f"{Colour.gold}INVITATION RECEIVED!{Colour.RESET}")
            print(f"The committee has selected {user_school.name} for the Spring Tournament.")
        else:
            print(f"{Colour.FAIL}No invitation received.{Colour.RESET}")
            print(f"Your prestige ({user_school.prestige}) was not high enough to impress the committee.")
            print("You watch the Spring tournament from home...")
        
        input("Press Enter to continue...")
        
        # Run the bracket
        _run_generic_tournament("SPRING SENBATSU", user_school_id, participants, session)

def _run_generic_tournament(title, user_school_id, participants, session):
    """
    Shared logic for running any bracket.
    """
    clear_screen()
    print(f"{Colour.HEADER}=== {title} BEGINS ==={Colour.RESET}\n")
    
    user_school = session.get(School, user_school_id)
    
    if not participants:
        # Fallback if None passed
        npcs = session.query(School).filter(School.id != user_school_id).all()
        participants = rng.sample(npcs, 15)
        participants.append(user_school)
        
    current_bracket = list(participants) # Copy
    rng.shuffle(current_bracket)
    
    # Trim to power of 2
    if len(current_bracket) > 32: current_bracket = current_bracket[:32]
    elif len(current_bracket) > 16: current_bracket = current_bracket[:16]
        
    round_num = 1
    
    while len(current_bracket) > 1:
        next_round = []
        print(f"\n{Colour.CYAN}--- ROUND {round_num} ({len(current_bracket)} Teams) ---{Colour.RESET}")
        
        matchups = []
        for i in range(0, len(current_bracket), 2):
            if i+1 < len(current_bracket):
                matchups.append((current_bracket[i], current_bracket[i+1]))
            
        for home, away in matchups:
            is_user_match = (home.id == user_school_id or away.id == user_school_id)
            
            print(f" > Match: {home.name} vs {away.name}")

            if is_user_match:
                _run_pre_match_story(round_num, user_school)
                opponent = away if home.id == user_school_id else home
                _maybe_inject_rival_dialogue(session, user_school_id, opponent)
            
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
                )
                clutch_payload = _build_clutch_payload(leverage_result, user_school_id, home, away)

            if is_user_match:
                print(f"{Colour.GREEN}   *** YOUR MATCH ***{Colour.RESET}")
                if leverage_result:
                    winner, score = resolve_match(
                        home,
                        away,
                        f"{title} Round {round_num}",
                        mode="standard",
                        silent=False,
                        clutch_pitch=clutch_payload,
                    )
                else:
                    winner, score = resolve_match(
                        home,
                        away,
                        f"{title} Round {round_num}",
                        mode="fast",
                    )
                    print(f"   Result: {winner.name} wins! ({score})")
            else:
                winner, score, upset = quick_resolve_match(session, home, away)
                note = " (UPSET)" if upset else ""
                print(f"   Result: {winner.name} wins! ({score}){note}")
            
            next_round.append(winner)
            
            if is_user_match and winner.id != user_school_id:
                print(f"\n{Colour.FAIL}You have been eliminated.{Colour.RESET}")
                input("Press Enter...")
                return 
                
        current_bracket = next_round
        _handle_between_round_story(session, user_school_id, current_bracket)
        round_num += 1
        
    winner = current_bracket[0]
    
    if winner.id == user_school_id:
        print(f"\n{Colour.gold}🏆 CONGRATULATIONS! YOU WON {title}! 🏆{Colour.RESET}")
        user_school.prestige += 15
        session.commit()
    else:
        print(f"\nWinner: {winner.name}")


def _run_pre_match_story(round_num: int, user_school: Optional[School]) -> None:
    if not user_school:
        return
    if round_num <= 1:
        _play_dialogue(DIALOGUE_COACH_MEETING)
        return
    prestige = getattr(user_school, "prestige", 0) or 0
    dialogue_id = DIALOGUE_CAPTAIN_HIGH if prestige >= 55 else DIALOGUE_CAPTAIN_LOW
    _play_dialogue(dialogue_id)


def _handle_between_round_story(session, user_school_id: int, bracket: List[School]) -> None:
    if not bracket or len(bracket) <= 1:
        return
    if not any(getattr(school, "id", None) == user_school_id for school in bracket):
        return
    snapshot = _team_fatigue_snapshot(session, user_school_id)
    if not snapshot:
        return
    avg_fatigue, avg_stamina = snapshot
    if avg_fatigue >= 65 and avg_stamina <= 55:
        print(
            f"\n{Colour.WARNING}Players are gassed after that last round. Coaches cancel optional reps to preserve arms.{Colour.RESET}"
        )
        print(
            f"   Avg fatigue: {avg_fatigue:.1f}% | Avg stamina: {avg_stamina:.1f}"
        )
        input("Press Enter to continue...")
        return
    _play_dialogue(DIALOGUE_TEAM_PRACTICE)


def _team_fatigue_snapshot(session, school_id: int) -> Optional[Tuple[float, float]]:
    try:
        players = session.query(Player).filter_by(school_id=school_id).all()
    except Exception:
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
) -> Optional[PitchMinigameResult]:
    inning = rng.choice([6, 7, 8, 9])
    half = rng.choice(["Top", "Bot"])
    runners_on = rng.choice([0, 1, 2, 3])
    score_diff = rng.choice([0, 1])
    if not _is_high_leverage(inning, score_diff, runners_on):
        return None
    if not _is_user_pitching(user_school_id, home, away, half):
        return None

    print(
        f"   {Colour.CYAN}High leverage moment! Coach signals for the pitch minigame.{Colour.RESET}"
    )

    scenario = PitchMinigameContext(
        inning=inning,
        half=half,
        count=rng.choice(["3-2", "2-2", "1-2"]),
        runners_on=runners_on,
        score_diff=score_diff,
        label=f"{title} Round {round_num}",
    )
    _maybe_play_bottom9_story(scenario)
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
    _announce_minigame_outcome(result)
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
    try:
        candidates = [
            player
            for player in getattr(school, "players", []) or []
            if (getattr(player, "position", "") or "").lower() == "pitcher"
        ]
    except Exception:
        candidates = []
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


def _announce_minigame_outcome(result: PitchMinigameResult) -> None:
    color = Colour.GREEN if result.quality >= 0.7 else Colour.YELLOW if result.quality >= 0.4 else Colour.RED
    print(
        f"   Pitch Quality: {color}{result.quality:.2f}{Colour.RESET} | "
        f"{result.feedback} (cursor delta {result.deviation:.2f})"
    )


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


def _maybe_inject_rival_dialogue(session, user_school_id: int, opponent: School) -> None:
    rival_school_id = _determine_rival_school_id(session)
    if not rival_school_id or opponent.id != rival_school_id:
        return
    dialogue_id = rng.choice(RIVAL_DIALOGUE_POOL)
    _play_dialogue(dialogue_id)


def _maybe_play_bottom9_story(context: PitchMinigameContext) -> None:
    if context.inning < 9 or (context.half or "").lower() != "bot":
        return
    if context.score_diff <= 0:
        _play_dialogue(DIALOGUE_CROWD_CHANTING)
    else:
        _play_dialogue(DIALOGUE_CROWD_SILENT)