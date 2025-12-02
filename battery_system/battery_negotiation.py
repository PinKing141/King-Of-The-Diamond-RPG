# battery_system/battery_negotiation.py
from dataclasses import dataclass
from ui.ui_display import Colour
from match_engine.pitch_logic import describe_batter_tells
from .battery_trust import get_trust
from .pitcher_personality import does_pitcher_accept
from .catcher_ai import suggest_pitch_logic


def _player_team_id(player):
    return getattr(player, 'team_id', getattr(player, 'school_id', None))


@dataclass
class NegotiatedPitchCall:
    pitch: object
    location: str
    intent: str = "Normal"
    shakes: int = 0
    trust: int = 50
    forced: bool = False

def run_battery_negotiation(pitcher, catcher, batter, state):
    """
    The Pre-Pitch Loop.
    Exchange signs until an agreement is reached or limit exceeded.
    Returns: (Pitch, Location) to be passed to resolve_pitch.
    """
    
    # 1. Identify Roles
    user_is_pitcher = (_player_team_id(pitcher) == 1) # User controls Pitcher
    user_is_catcher = (_player_team_id(catcher) == 1) # User controls Catcher (Future feature)
    
    # For now, we assume User is Pitcher OR User watches AI vs AI.
    # If User is Catcher (Phase 5), we'd swap the logic.
    
    trust = get_trust(pitcher.id, catcher.id)
    
    presence_map = getattr(state, 'pitcher_presence', {}) or {}
    dominance = presence_map.get(getattr(pitcher, 'id', None), 0.0)
    suggestion, location, intent = suggest_pitch_logic(catcher, pitcher, batter, state)
    
    # --- NEGOTIATION LOOP ---
    max_shake_offs = 2
    if trust >= 65:
        max_shake_offs += 1
    if dominance >= 1.5:
        max_shake_offs += 1
    max_shake_offs = min(4, max_shake_offs)
    shakes = 0
    forced = False
    
    while True:
        if user_is_pitcher:
            print(f"\n{Colour.BLUE}[Catcher Sign] {suggestion.pitch_name} ({location}){Colour.RESET}")
            print(f"   (Trust: {trust} | Dominance: {dominance:+.1f} | Shakes left: {max_shake_offs - shakes})")
            intel = describe_batter_tells(state, batter)
            if intel:
                print(f"   Intel: {' | '.join(intel)}")

            print("   1. Accept Sign")
            print("   2. Shake Off")
            choice = input("   >> ")

            if choice == '1':
                break

            shakes += 1
            print("   (Shaking off...)")
            if shakes >= max_shake_offs:
                forced = True
                break
            suggestion, location, intent = suggest_pitch_logic(
                catcher,
                pitcher,
                batter,
                state,
                exclude_pitch_name=suggestion.pitch_name,
            )
            continue

        # AI-controlled pitcher branch
        if does_pitcher_accept(pitcher, suggestion, trust, dominance=dominance):
            break

        shakes += 1
        if shakes >= max_shake_offs:
            forced = True
            break
        suggestion, location, intent = suggest_pitch_logic(
            catcher,
            pitcher,
            batter,
            state,
            exclude_pitch_name=suggestion.pitch_name,
        )

    return NegotiatedPitchCall(
        pitch=suggestion,
        location=location,
        intent=intent,
        shakes=shakes,
        trust=trust,
        forced=forced,
    )
