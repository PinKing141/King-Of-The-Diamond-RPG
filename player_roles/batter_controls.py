import sys
from ui.ui_display import Colour
from match_engine.states import EventType


_BATTERS_EYE_CHOICES = {
    '1': {"kind": "family", "value": "fastball", "label": "Fastball"},
    '2': {"kind": "family", "value": "breaker", "label": "Breaking Ball"},
    '3': {"kind": "family", "value": "offspeed", "label": "Offspeed (Change/Split)"},
    '4': {"kind": "location", "value": "zone", "label": "In the Zone"},
    '5': {"kind": "location", "value": "chase", "label": "Out of Zone"},
}


def _prompt_batters_eye() -> dict | None:
    """Optional pre-pitch guess that fuels the Batter's Eye mechanic."""
    print(f"\n{Colour.GOLD}Batter's Eye — Sit on something?{Colour.RESET}")
    print(" Enter to skip if you want to stay reactive.")
    print(" 1. Fastball family")
    print(" 2. Breaking ball")
    print(" 3. Offspeed / Splitter")
    print(" 4. Zone attack (strike)")
    print(" 5. Waste pitch (outside zone)")
    while True:
        choice = input("Sit on: ").strip().lower()
        if choice in {"", "0", "skip"}:
            return None
        payload = _BATTERS_EYE_CHOICES.get(choice)
        if payload:
            print(f" Locking in on {payload['label']}.")
            data = payload.copy()
            data['source'] = 'user'
            return data
        print(" Invalid guess. Enter 1-5 or press Enter to skip.")


def _ensure_standing_orders(state):
    if not hasattr(state, "standing_orders") or not isinstance(getattr(state, "standing_orders", None), dict):
        state.standing_orders = {"offense": "Work the Count", "defense": "Attack Zone"}


def _orders_summary(state) -> str:
    _ensure_standing_orders(state)
    orders = getattr(state, "standing_orders", {}) or {}
    offense = orders.get("offense", "Work the Count")
    defense = orders.get("defense", "Attack Zone")
    hero_setting = getattr(state, "hero_setting", "key")
    play_mode = getattr(state, "play_mode", "SIM")
    cooldown_until = getattr(state, "hero_cooldown_until", 0)
    pa_counter = getattr(state, "pa_counter", 0)
    cd = max(0, cooldown_until - pa_counter)
    cd_label = f"cd {cd} PA" if cd > 0 else "ready"
    return f"Offense: {offense} | Defense: {defense} | HERO: {hero_setting} | Mode: {play_mode} | {cd_label}"


def _emit_setting_event(state, hero_setting: str) -> None:
    bus = getattr(state, "event_bus", None)
    if not bus:
        return
    bus.publish(EventType.HERO_MODE_SETTING.value, {"hero_setting": hero_setting})


def _standing_orders_menu(state) -> None:
    _ensure_standing_orders(state)
    orders = state.standing_orders
    hero_setting = getattr(state, "hero_setting", "key").lower()
    while True:
        print(f"\n{Colour.CYAN}--- Standing Orders / HERO Menu ---{Colour.RESET}")
        print(_orders_summary(state))
        print(" 1. Offense: Work the Count")
        print(" 2. Offense: Swing Early / Attack")
        print(" 3. Offense: Protect with Two Strikes")
        print(" 4. Defense: Attack Zone")
        print(" 5. Defense: Pitch Around / Nibble")
        print(" 6. Defense: Nibble Edges (soft nibble)")
        print(" 7. HERO Frequency: cycle (never / key / often)")
        print(" Q. Close menu")
        choice = input(" Orders cmd: ").strip().lower()
        if choice in {"q", "", "exit"}:
            return
        if choice == "1":
            orders["offense"] = "Work the Count"
        elif choice == "2":
            orders["offense"] = "Swing Early"
        elif choice == "3":
            orders["offense"] = "Protect Two Strikes"
        elif choice == "4":
            orders["defense"] = "Attack Zone"
        elif choice == "5":
            orders["defense"] = "Pitch Around"
        elif choice == "6":
            orders["defense"] = "Nibble Edges"
        elif choice == "7":
            hero_setting = {
                "never": "key",
                "key": "often",
                "often": "never",
            }.get(hero_setting, "key")
            state.hero_setting = hero_setting
            _emit_setting_event(state, hero_setting)
            print(f" HERO frequency set to {hero_setting}.")
        else:
            print(" Invalid choice.")
            continue
        state.standing_orders = orders
        logs = getattr(state, "logs", None)
        if isinstance(logs, list):
            logs.append(f"[Orders] Offense: {orders.get('offense')} | Defense: {orders.get('defense')} | HERO: {hero_setting}")
        print(f" Updated: {_orders_summary(state)}")

def player_bat_turn(pitcher, batter, state):
    """
    Handles the User Interaction for a batting turn.
    Returns: (Action String, Modifier Dictionary)
    """
    print(f"\n{Colour.HEADER}--- BATTER INTERFACE ---{Colour.RESET}")
    print(f"Pitcher: {pitcher.name} | Stamina: {getattr(pitcher, 'fatigue', 0)}% Tired")
    print(f"Count: {state.balls}-{state.strikes} | Outs: {state.outs}")
    print(f"Orders: {_orders_summary(state)}")
    
    # Display Options
    print(f"{Colour.CYAN}Select Approach:{Colour.RESET}")
    print(" 1. NORMAL SWING (Balanced)")
    print(" 2. POWER SWING  (High Risk, High Power)")
    print(" 3. CONTACT SWING (Bonus to hit, less Power)")
    print(" 4. TAKE PITCH   (Do not swing)")
    print(" 5. BUNT (Sacrifice for runner)")
    print(" 6. SACRIFICE FLY (Aim for outfield depth)")
    print(" 7. WAIT FOR WALK (Intentionally passive)")
    print(" 8. Standing Orders / HERO menu")
    
    action = "Normal"
    mods = {}
    
    valid = False
    while not valid:
        choice = input("Command: ").strip().lower()
        
        if choice in {'8', 'o'}:
            _standing_orders_menu(state)
            print(f"\n{Colour.CYAN}Back to at-bat. Current orders: {_orders_summary(state)}{Colour.RESET}")
            continue

        if choice == '1':
            action = "Swing"
            mods = {'contact_mod': 0, 'power_mod': 0, 'eye_mod': 0}
            valid = True
            
        elif choice == '2':
            action = "Power"
            mods = {'contact_mod': -20, 'power_mod': +25, 'eye_mod': -10}
            valid = True
            
        elif choice == '3':
            action = "Contact"
            mods = {'contact_mod': +20, 'power_mod': -30, 'eye_mod': +10}
            valid = True
            
        elif choice == '4':
            action = "Take"
            mods = {} # No swing
            valid = True

        elif choice == '5':
            action = "Bunt"
            # Bunt logic: Sacrifice power completely for high contact on ground
            mods = {'contact_mod': +40, 'power_mod': -100, 'eye_mod': 0, 'bunt_flag': True}
            valid = True

        elif choice == '6':
            action = "SacFly"
            # Aim for fly ball: Moderate power, slight contact penalty
            mods = {'contact_mod': -5, 'power_mod': 0, 'eye_mod': 0, 'fly_bias': True}
            valid = True

        elif choice == '7':
            action = "Wait"
            # Boost eye significantly, penalize swing chance if forced
            mods = {'contact_mod': -50, 'power_mod': 0, 'eye_mod': +30}
            valid = True
            
        else:
            print("Invalid command.")
            
    guess_payload = _prompt_batters_eye()
    if guess_payload:
        mods['guess_payload'] = guess_payload
    return action, mods