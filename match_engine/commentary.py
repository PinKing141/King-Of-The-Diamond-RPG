from typing import List, Optional

from ui.ui_display import Colour
from game.rng import get_rng

rng = get_rng()

_COMMENTARY_ENABLED = True

CLUTCH_HERO_THRESHOLD = 72
CLUTCH_NERVES_THRESHOLD = 40
SLUMP_CONDITIONING_CUTOFF = 45
SLUMP_HITLESS_AB = 3
FATIGUE_THRESHOLDS = (85, 105)
WEATHER_ICONS = {
    "clear": "[SUN]",
    "muggy": "[HAZE]",
    "windy": "[WIND]",
    "rain": "[RAIN]",
    "heat": "[HEAT]",
}


def set_commentary_enabled(enabled: bool) -> None:
    """Globally enable or disable commentary generation."""
    global _COMMENTARY_ENABLED
    _COMMENTARY_ENABLED = bool(enabled)


def commentary_enabled() -> bool:
    """Return True when commentary output should be produced."""
    return _COMMENTARY_ENABLED


def _short_name(player) -> str:
    if not player:
        return "Player"
    return getattr(player, 'last_name', None) or getattr(player, 'name', None) or getattr(player, 'first_name', None) or "Player"


def _player_team_id(player) -> Optional[int]:
    if not player:
        return None
    return getattr(player, 'team_id', None) or getattr(player, 'school_id', None)


def _team_name_from_id(state, team_id: Optional[int]) -> str:
    if team_id is None:
        return "The dugout"
    if getattr(state.home_team, 'id', None) == team_id:
        return getattr(state.home_team, 'name', 'Home')
    if getattr(state.away_team, 'id', None) == team_id:
        return getattr(state.away_team, 'name', 'Away')
    return "The dugout"


def _queue_line(lines: List[str], memory: set, key: str, text: Optional[str]) -> None:
    if not text or key in memory:
        return
    memory.add(key)
    lines.append(text)


def _is_high_leverage(state) -> bool:
    inning = getattr(state, 'inning', 1)
    score_gap = abs((state.home_score or 0) - (state.away_score or 0))
    runners_in_scoring_pos = any(state.runners[1:]) if getattr(state, 'runners', None) else False
    return inning >= 7 and score_gap <= 2 and runners_in_scoring_pos


def _append_coach_strategy_notes(lines, memory, state, batter) -> None:
    team_id = _player_team_id(batter)
    if team_id is None:
        return
    mods = (getattr(state, 'team_mods', None) or {}).get(team_id, [])
    if not mods:
        return
    team_name = _team_name_from_id(state, team_id)
    for mod in mods:
        effect = mod.get('type') if isinstance(mod, dict) else None
        if effect == 'small_ball':
            _queue_line(lines, memory, f"mod_small_ball_{team_id}", f"{team_name} is embracing bunts and pressure after the coach's directive.")
        elif effect == 'power_focus':
            _queue_line(lines, memory, f"mod_power_focus_{team_id}", f"{team_name} was told to swing freely—no timid swings tonight.")
        elif effect == 'rest_player' and mod.get('target_player_id') == getattr(batter, 'id', None):
            _queue_line(lines, memory, f"mod_rest_{batter.id}", f"Coach nearly sat {_short_name(batter)}, but he's gutting it out despite the fatigue directive.")


def _append_rivalry_notes(lines, memory, state, pitcher, batter) -> None:
    hero_id = getattr(state, 'hero_player_id', None)
    rival_name = getattr(state, 'rival_name', None)
    if not hero_id or not rival_name:
        return
    rivalry_score = getattr(state, 'rivalry_score', None)
    rivalry_delta = getattr(state, 'rivalry_delta', 0.0) or 0.0
    hero_display = getattr(state, 'hero_name', None)
    def _rival_phrase() -> str:
        if rivalry_score is None:
            return ""
        adjective = "heated" if rivalry_score >= 55 else "simmering"
        return f" ({adjective} rivalry score {int(rivalry_score)})"

    if hero_id == getattr(batter, 'id', None):
        tone = "amped" if rivalry_delta >= 0 else "pressured"
        name = hero_display or _short_name(batter)
        note = f"{name} steps in {tone} after rival {rival_name} lit the fire{_rival_phrase()}"
        _queue_line(lines, memory, f"rival_batter_{hero_id}", note)
    elif hero_id == getattr(pitcher, 'id', None):
        tone = "channeling that grudge" if rivalry_delta >= 0 else "trying to drown out the doubts"
        name = hero_display or _short_name(pitcher)
        note = f"{name} is {tone} with {rival_name} watching from afar{_rival_phrase()}"
        _queue_line(lines, memory, f"rival_pitcher_{hero_id}", note)


def _append_clutch_notes(lines, memory, state, batter) -> None:
    if not _is_high_leverage(state) or not batter:
        return
    clutch = getattr(batter, 'clutch', 50) or 50
    if clutch >= CLUTCH_HERO_THRESHOLD:
        note = f"Clutch spot now—{_short_name(batter)} lives for these moments (clutch {int(clutch)})."
        _queue_line(lines, memory, f"clutch_high_{batter.id}", note)
    elif clutch <= CLUTCH_NERVES_THRESHOLD:
        note = f"Late-inning stress test for {_short_name(batter)}, whose nerves can wobble (clutch {int(clutch)})."
        _queue_line(lines, memory, f"clutch_low_{batter.id}", note)


def _append_slump_notes(lines, memory, state, batter) -> None:
    if not batter:
        return
    stats = state.stats.get(batter.id, {})
    conditioning = getattr(batter, 'conditioning', 50) or 50
    fatigue = getattr(batter, 'fatigue', 0) or 0
    if conditioning <= SLUMP_CONDITIONING_CUTOFF:
        note = f"{_short_name(batter)} hasn't felt right lately (conditioning {int(conditioning)})."
        _queue_line(lines, memory, f"slump_form_{batter.id}", note)
    elif stats.get('at_bats', 0) >= SLUMP_HITLESS_AB and stats.get('hits', 0) == 0:
        note = f"{_short_name(batter)} is 0-for-{stats['at_bats']} today and searching for answers."
        _queue_line(lines, memory, f"slump_day_{batter.id}", note)
    if fatigue >= 75:
        note = f"Fatigue is creeping in for {_short_name(batter)} (fatigue {int(fatigue)})."
        _queue_line(lines, memory, f"slump_fatigue_{batter.id}", note)


def _append_fatigue_notes(lines, memory, state, pitcher) -> None:
    if not pitcher:
        return
    pitch_count = state.pitch_counts.get(pitcher.id, 0)
    for threshold in FATIGUE_THRESHOLDS:
        if pitch_count >= threshold:
            note = f"{_short_name(pitcher)} has thrown {pitch_count} pitches and is running on fumes."
            _queue_line(lines, memory, f"fatigue_{pitcher.id}_{threshold}", note)


def _emit_contextual_notes(state, pitcher, batter) -> None:
    memory = getattr(state, 'commentary_memory', None)
    if memory is None:
        memory = set()
        state.commentary_memory = memory
    lines: List[str] = []
    _append_coach_strategy_notes(lines, memory, state, batter)
    _append_rivalry_notes(lines, memory, state, pitcher, batter)
    _append_clutch_notes(lines, memory, state, batter)
    _append_slump_notes(lines, memory, state, batter)
    _append_fatigue_notes(lines, memory, state, pitcher)
    if lines:
        for line in lines:
            print(f"   >> {line}")


def _announce_weather_once(state) -> None:
    if not _COMMENTARY_ENABLED:
        return
    weather = getattr(state, 'weather', None)
    if not weather:
        return
    memory = getattr(state, 'commentary_memory', None)
    if memory is None:
        memory = set()
        state.commentary_memory = memory
    if 'weather_banner' in memory:
        return
    memory.add('weather_banner')
    icon = WEATHER_ICONS.get(weather.condition, WEATHER_ICONS['clear'])
    summary = weather.describe()
    hint = weather.commentary_hint or ""
    extra = f" {hint}" if hint else ""
    print(f"   >> {icon} Weather watch: {summary}.{extra}")

# --- COMMENTARY POOLS ---
STRIKEOUT_PHRASES = [
    "He froze him with a backdoor slider!",
    "Swung at a high heater! Sit down!",
    "Got him looking! A absolute painting on the corner.",
    "Three pitches, three strikes. Good morning, good afternoon, good night!",
    "He chased the breaking ball in the dirt."
]

HOMERUN_PHRASES = [
    "IT IS HIGH! IT IS FAR! IT IS GONE!",
    "That ball was absolutely crushed! A no-doubter!",
    "Goodbye baseball! A moonshot to left field!",
    "Upper deck! What power!",
    "The outfielder didn't even move. Home Run!"
]

HIT_PHRASES = [
    "A sharp liner into the gap!",
    "Hard ground ball past the diving shortstop.",
    "He bloops it over the infield for a base hit.",
    "Smoked down the line! Fair ball!",
    "A rocket off the wall!"
]

def type_writer(text, speed=0.01):
    """Effect to print text slightly like a typewriter."""
    if not _COMMENTARY_ENABLED:
        return
    print(text)
    # Uncomment for slow effect (can be annoying in long games)
    # for char in text:
    #     sys.stdout.write(char)
    #     sys.stdout.flush()
    #     time.sleep(speed)
    # print("")

def display_state(state, pitcher, batter):
    """
    Visualizes the current game state: Inning, Score, Diamond, Count.
    """
    if not _COMMENTARY_ENABLED:
        return
    print("\n" + "="*60)
    # Use 'name' attribute for V2 Schema compatibility
    away_name = getattr(state.away_team, 'name', 'Away')
    home_name = getattr(state.home_team, 'name', 'Home')
    
    print(f" {away_name[:3]} {state.away_score}  -  {state.home_score} {home_name[:3]}   |   {state.top_bottom} {state.inning}")
    print("="*60)
    
    # Diamond Visualization
    r1 = f"{Colour.RED}X{Colour.RESET}" if state.runners[0] else " "
    r2 = f"{Colour.RED}X{Colour.RESET}" if state.runners[1] else " "
    r3 = f"{Colour.RED}X{Colour.RESET}" if state.runners[2] else " "
    
    print(f"      [{r2}]")
    print(f"     /   \\")
    print(f"   [{r3}]   [{r1}]")
    print(f"     \\   /")
    print(f"      [ ]")
    
    # Matchup Info
    # Check conditioning for flavor text (Optional)
    p_cond = ""
    if hasattr(pitcher, 'conditioning') and pitcher.conditioning > 70:
        p_cond = f"{Colour.GREEN}(Sharp){Colour.RESET}"
    
    b_cond = ""
    if hasattr(batter, 'conditioning') and batter.conditioning > 70:
        b_cond = f"{Colour.GREEN}(Focused){Colour.RESET}"

    # Pitcher info (Arm slot might be missing in V2 schema if not generated, handle gracefully)
    arm_slot = getattr(pitcher, 'arm_slot', 'Three-Quarters') 
    
    # Use 'name' or 'last_name' depending on schema. V2 uses 'name' as full name usually.
    p_name = getattr(pitcher, 'name', getattr(pitcher, 'last_name', 'Pitcher'))
    b_name = getattr(batter, 'name', getattr(batter, 'last_name', 'Batter'))
    
    print(f"\n PITCHER: {p_name} {p_cond} ({arm_slot})")
    print(f" BATTER:  {b_name} {b_cond} (Pow {batter.power} / Con {batter.contact})")
    print(f" COUNT:   {state.balls}-{state.strikes}  |  OUTS: {state.outs}")
    print("-" * 60)
    _announce_weather_once(state)
    _emit_contextual_notes(state, pitcher, batter)

def announce_pitch(pitch_result):
    if not _COMMENTARY_ENABLED:
        return
    vel_str = f"{pitch_result.velocity:.1f} km/h"
    
    if pitch_result.outcome == "Ball":
        print(f" > {pitch_result.pitch_name} ({vel_str}) ... Ball {pitch_result.description}.")
        
    elif pitch_result.outcome == "Strike":
        desc = pitch_result.description
        if desc == "Swinging Miss":
            desc = f"{Colour.YELLOW}Swinging Miss{Colour.RESET}"
        elif desc == "Looking":
            desc = f"{Colour.CYAN}Looking{Colour.RESET}"
            
        print(f" > {pitch_result.pitch_name} ({vel_str}) ... STRIKE! ({desc})")
        
    elif pitch_result.outcome == "Foul":
        print(f" > {pitch_result.pitch_name} ... Fouled off.")
        
    elif pitch_result.outcome == "InPlay":
        print(f" > {pitch_result.pitch_name} ... {Colour.BOLD}CONTACT!{Colour.RESET}")

def announce_play(contact_result):
    if not _COMMENTARY_ENABLED:
        return
    if getattr(contact_result, 'error_on_play', False):
        print(f"   >> {contact_result.description}")
        return
    if contact_result.hit_type == "Out":
        print(f"   >> {contact_result.description}")
        
        # Add flavor for strikeouts
        if "Strikeout" in contact_result.description:
             print(f"   >> {rng.choice(STRIKEOUT_PHRASES)}")

    elif contact_result.hit_type == "HR":
        # ASCII Art for Home Run
        print(f"\n{Colour.RED}")
        print(r"       _   _  ____  __  __  ___   ____  _   _  _   _ ")
        print(r"      | | | |/ __ \|  \/  || __| |  _ \| | | || \ | |")
        print(r"      | |_| | |  | | \  / || _|  | |_) | | | ||  \| |")
        print(r"      |  _  | |__| | |\/| || |__ |  _ <| |_| || |\  |")
        print(r"      |_| |_|\____/|_|  |_||___| |_| \_\\___/ |_| \_|")
        print(f"{Colour.RESET}")
        print(f"   >> ** {rng.choice(HOMERUN_PHRASES)} **")
        
    elif contact_result.hit_type in ["1B", "2B", "3B"]:
        base = contact_result.hit_type
        print(f"   >> {Colour.GREEN}{base}! {rng.choice(HIT_PHRASES)}{Colour.RESET}")
    else:
        print(f"   >> {contact_result.description}")

def announce_score_change(runs, batting_team_name):
    if not _COMMENTARY_ENABLED:
        return
    if runs > 0:
        print(f"   !! {Colour.gold}{runs} RUN(S) SCORED for {batting_team_name}!{Colour.RESET} !!")

def game_over(state, winner):
    if not _COMMENTARY_ENABLED:
        return
    print("\n" + "#"*60)
    print(f"{Colour.HEADER} GAME OVER {Colour.RESET}")
    
    away_name = getattr(state.away_team, 'name', 'Away')
    home_name = getattr(state.home_team, 'name', 'Home')
    winner_name = getattr(winner, 'name', 'Winner')
    
    print(f" Final Score: {away_name} {state.away_score} - {state.home_score} {home_name}")
    print(f" Winner: {Colour.gold}{winner_name}{Colour.RESET}")
    umpire = getattr(state, 'umpire', None)
    if umpire:
        desc = umpire.description or "Neutral strike zone."
        home_id = getattr(state.home_team, 'id', None)
        away_id = getattr(state.away_team, 'id', None)
        tilt = getattr(state, 'umpire_call_tilt', {}) or {}
        home_tilt = tilt.get(home_id, {"favored": 0, "squeezed": 0})
        away_tilt = tilt.get(away_id, {"favored": 0, "squeezed": 0})
        zone = getattr(umpire, 'zone_bias', 0.0) or 0.0
        home_bias = getattr(umpire, 'home_bias', 0.0) or 0.0
        print(f" Plate Umpire: {umpire.name} — {desc}")
        print(f"   Zone bias {zone:+.2f} | Home lean {home_bias:+.2f}")
        print(f"   Calls: Home +{home_tilt.get('favored', 0)} / -{home_tilt.get('squeezed', 0)} | Away +{away_tilt.get('favored', 0)} / -{away_tilt.get('squeezed', 0)}")
    print("#"*60 + "\n")