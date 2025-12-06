# battery_system/battery_negotiation.py
from dataclasses import dataclass

from match_engine.pitch_logic import describe_batter_tells
from match_engine.states import EventType
from ui.ui_display import Colour

from game.catcher_ai import generate_catcher_sign, get_or_create_catcher_memory

from .battery_trust import adjust_battery_sync, get_battery_sync, get_trust_snapshot
from .pitcher_personality import does_pitcher_accept
from game.relationship_manager import seed_relationships


def _player_team_id(player): 
    return getattr(player, 'team_id', getattr(player, 'school_id', None))


def _maybe_flag_synchronized_pitch(state, pitcher, catcher, trust_snapshot: int) -> bool:
    """Check battery bond and mark a one-per-game Synchronized Pitch."""

    pitcher_id = getattr(pitcher, "id", None)
    catcher_id = getattr(catcher, "id", None)
    if not pitcher_id or not catcher_id:
        return False
    used = getattr(state, "sync_pitch_used", None)
    if not isinstance(used, set):
        used = set()
        state.sync_pitch_used = used
    key = (pitcher_id, catcher_id)
    if key in used:
        return False

    bond_high = trust_snapshot >= 95
    if not bond_high:
        session = getattr(state, "db_session", None)
        if session:
            try:
                rel = seed_relationships(session, pitcher)
                partner_id = getattr(rel, "battery_partner_id", None)
                bond_high = bool(partner_id == catcher_id and (getattr(rel, "battery_rel", 0) or 0) >= 95)
            except Exception:
                bond_high = False
    if not bond_high:
        return False

    used.add(key)
    return True


@dataclass
class NegotiatedPitchCall:
    pitch: object
    location: str
    intent: str = "Normal"
    shakes: int = 0
    trust: int = 50
    forced: bool = False
    sync: float = 0.0
    perfect_location: bool = False  # Synchronized Pitch: guarantees paint once per game

def run_battery_negotiation(pitcher, catcher, batter, state, *, decision_override=None, sign_override=None):
    """
    The Pre-Pitch Loop.
    Exchange signs until an agreement is reached or limit exceeded.
    Returns: (Pitch, Location) to be passed to resolve_pitch.
    """

    # 1. Identify Roles
    user_is_pitcher = (_player_team_id(pitcher) == 1)  # User controls Pitcher
    # User-as-catcher support lands in a later phase; ignore for now.

    pitcher_id = getattr(pitcher, "id", None)
    catcher_id = getattr(catcher, "id", None)
    batter_id = getattr(batter, "id", None)

    # In fast sims we skip DB-backed trust lookups to avoid lock contention during bulk NPC games.
    if getattr(state, "fast_sim", False):
        trust = 50
    else:
        trust = get_trust_snapshot(state, pitcher_id, catcher_id)

    presence_map = getattr(state, 'pitcher_presence', {}) or {}
    dominance = presence_map.get(pitcher_id, 0.0)
    memory = get_or_create_catcher_memory(state)
    sign_func = sign_override or generate_catcher_sign

    pitch_call = sign_func(catcher, pitcher, batter, state, memory=memory)
    suggestion, location, intent = pitch_call.pitch, pitch_call.location, pitch_call.intent

    bus = getattr(state, "event_bus", None)
    sync = 0.0 if getattr(state, "fast_sim", False) else get_battery_sync(state, pitcher_id, catcher_id)

    def _publish(event_type: EventType, extra: dict | None = None) -> None:
        if not bus:
            return
        payload = {
            "pitcher_id": pitcher_id,
            "catcher_id": catcher_id,
            "batter_id": batter_id,
            "pitch_name": getattr(suggestion, "pitch_name", None),
            "location": location,
            "intent": intent,
            "trust": trust,
            "dominance": dominance,
            "shakes_used": shakes,
            "shakes_allowed": max_shake_offs,
            "forced": forced,
            "sync": sync,
            "confidence": getattr(pitch_call, "confidence", 0.0),
            "reason": getattr(pitch_call, "reason", ""),
        }
        if extra:
            payload.update(extra)
        bus.publish(event_type.value, payload)

    # --- NEGOTIATION LOOP ---
    max_shake_offs = 2
    if trust >= 65:
        max_shake_offs += 1
    if dominance >= 1.5:
        max_shake_offs += 1
    if sync >= 1.5:
        max_shake_offs += 1
    elif sync <= -1.5:
        max_shake_offs -= 1
    max_shake_offs = max(1, min(4, max_shake_offs))
    shakes = 0
    forced = False

    _publish(
        EventType.BATTERY_SIGN_CALLED,
        {
            "phase": "initial",
        },
    )

    decision_func = decision_override or does_pitcher_accept

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
            sync = adjust_battery_sync(state, pitcher_id, catcher_id, -0.2)
            _publish(
                EventType.BATTERY_SHAKE,
                {
                    "forced": False,
                    "sync": sync,
                },
            )
            print("   (Shaking off...)")
            if shakes >= max_shake_offs:
                forced = True
                _publish(EventType.BATTERY_FORCED_CALL, {"forced": True, "sync": sync})
                break
            pitch_call = sign_func(
                catcher,
                pitcher,
                batter,
                state,
                memory=memory,
                exclude_pitch_name=suggestion.pitch_name,
            )
            suggestion, location, intent = pitch_call.pitch, pitch_call.location, pitch_call.intent
            _publish(EventType.BATTERY_SIGN_CALLED, {"phase": "retry"})
            continue

        # AI-controlled pitcher branch
        if decision_func(pitcher, suggestion, trust, dominance=dominance):
            break

        shakes += 1
        sync = adjust_battery_sync(state, pitcher_id, catcher_id, -0.2)
        _publish(
            EventType.BATTERY_SHAKE,
            {
                "forced": False,
                "sync": sync,
            },
        )
        if shakes >= max_shake_offs:
            forced = True
            _publish(EventType.BATTERY_FORCED_CALL, {"forced": True, "sync": sync})
            break
        pitch_call = sign_func(
            catcher,
            pitcher,
            batter,
            state,
            memory=memory,
            exclude_pitch_name=suggestion.pitch_name,
        )
        suggestion, location, intent = pitch_call.pitch, pitch_call.location, pitch_call.intent
        _publish(EventType.BATTERY_SIGN_CALLED, {"phase": "retry"})

    final_phase = "forced" if forced else "locked"
    if not forced:
        sync = adjust_battery_sync(state, pitcher_id, catcher_id, 0.15 if shakes == 0 else -0.05 * shakes)

    call_snapshot = {
        "pitcher_id": pitcher_id,
        "catcher_id": catcher_id,
        "batter_id": batter_id,
        "pitch_name": getattr(suggestion, "pitch_name", None),
        "location": location,
        "intent": intent,
        "trust": trust,
        "dominance": dominance,
        "shakes": shakes,
        "forced": forced,
        "sync": sync,
        "confidence": getattr(pitch_call, "confidence", 0.0),
        "reason": getattr(pitch_call, "reason", ""),
        "phase": final_phase,
    }
    setattr(state, "last_battery_call", call_snapshot)
    _publish(EventType.BATTERY_SIGN_CALLED, {"phase": final_phase, "forced": forced, "sync": sync})

    perfect_location = False
    try:
        perfect_location = _maybe_flag_synchronized_pitch(state, pitcher, catcher, trust)
    except Exception:
        perfect_location = False

    if perfect_location:
        call_snapshot["perfect_location"] = True
        if isinstance(getattr(state, "logs", None), list):
            state.logs.append("[Battery Bond] Synchronized Pitch primed — perfect spot locked in.")

    return NegotiatedPitchCall(
        pitch=suggestion,
        location=location,
        intent=intent,
        shakes=shakes,
        trust=trust,
        forced=forced,
        sync=sync,
        perfect_location=perfect_location,
    )
