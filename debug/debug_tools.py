"""Developer cheat / debug console activated by entering the master code.

Type the master code anywhere an input is prompted to open the debug menu.
This is intended for testing and skips normal progression (creative mode).
"""
from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Optional

from ui.ui_display import Colour, clear_screen
from database.setup_db import School, Player
from match_engine.controller import run_match

DEBUG_CODE = "30062004"
_debug_enabled = False


def enable_debug_mode() -> None:
    global _debug_enabled
    _debug_enabled = True


def is_debug_enabled() -> bool:
    return _debug_enabled


def input_with_debug(prompt: str, *, context=None, session=None, state=None, raw_override: Optional[str] = None) -> Optional[str]:
    """Wrap input; if the master code is typed, open the debug menu and return None."""
    if raw_override is None:
        try:
            raw = input(prompt)
        except EOFError:
            return None
    else:
        raw = raw_override
    if raw.strip() == DEBUG_CODE:
        enable_debug_mode()
        open_debug_menu(context=context, session=session, state=state)
        return None
    return raw


def _get_player(context, session, state):
    if context and getattr(context, "session", None) and getattr(context, "player_id", None):
        try:
            return context.session.get(Player, context.player_id)
        except Exception as exc:
            print(f"[Debug] Failed to fetch player from context: {exc}")
    if session and state and getattr(state, "active_player_id", None):
        try:
            return session.get(Player, state.active_player_id)
        except Exception as exc:
            print(f"[Debug] Failed to fetch player from session: {exc}")
            return None
    return None


def _resolve_user_school_id(session, state):
    if session and state and getattr(state, "active_player_id", None):
        try:
            player = session.get(Player, state.active_player_id)
            if player:
                return getattr(player, "school_id", None)
        except Exception as exc:
            print(f"[Debug] Failed to resolve user school id: {exc}")
            return None
    return None


def _prompt_player_choice(matchup) -> str:
    """Simple CLI agency adapter for Batter's Eye prompts."""
    batter = getattr(matchup.batter, "last_name", "Batter") or "Batter"
    pitcher = getattr(matchup.pitcher, "last_name", "Pitcher") or "Pitcher"
    inning = getattr(matchup, "inning", 1)
    half = getattr(matchup, "half", "Top")
    print(f"\n[Batter's Eye] {batter} vs {pitcher} — {half} {inning}")
    print("  Options: react | guess_fastball | guess_breaker | guess_change | sit_fastball | sit_breaker | sit_change")
    choice = input("  Choice (default=react): ").strip().lower() or "react"
    return choice


def _set_player_stats(player, *, all_value: Optional[int] = None, **overrides):
    """Set a broad set of live stats to a single value (or individual overrides)."""
    if not player:
        return
    # Keep this list in sync with the Player model's core performance attributes.
    fields = [
        "velocity",
        "control",
        "command",
        "movement",
        "stamina",
        "fielding",
        "speed",
        "contact",
        "power",
        "throwing",
        "discipline",
        "clutch",
        "mental",
        "catcher_ability",
        "catcher_leadership",
    ]
    for field in fields:
        new_val = overrides.get(field, all_value)
        if new_val is None:
            continue
        try:
            setattr(player, field, int(new_val))
        except Exception:
            # Keep the debug menu resilient if a column is missing in a WIP save.
            continue


def _quick_exhibition(session, user_school_id: int, opponent_id: int):
    if not session or not user_school_id or not opponent_id:
        print("Missing session or school ids; cannot run exhibition.")
        time.sleep(1)
        return
    try:
        from world_sim.sim_utils import quick_resolve_match
    except Exception:
        print("quick_resolve_match unavailable.")
        time.sleep(1)
        return

    home_school = session.get(School, user_school_id)
    away_school = session.get(School, opponent_id)
    if not home_school or not away_school:
        print("Invalid school ids for exhibition.")
        time.sleep(1)
        return

    home = SimpleNamespace(id=home_school.id, name=home_school.name)
    away = SimpleNamespace(id=away_school.id, name=away_school.name)
    _, score, upset, *_ids = quick_resolve_match(session, home, away)
    print(f"Result: {home.name} vs {away.name} => {score} (upset={bool(upset)})")
    time.sleep(2)


def _edit_pitch_shapes(session, player):
    """Interactive editor for a pitcher's per-pitch shape/release/extension."""
    if not player:
        print("No active player.")
        time.sleep(1)
        return
    if getattr(player, "position", None) != "Pitcher":
        print("Active player is not a pitcher.")
        time.sleep(1)
        return
    pitches = list(getattr(player, "pitch_repertoire", []) or [])
    if not pitches:
        print("No pitches found on this player.")
        time.sleep(1)
        return

    while True:
        clear_screen()
        print(f"{Colour.CYAN}{Colour.BOLD}Pitch Arsenal Editor{Colour.RESET}")
        for idx, p in enumerate(pitches, start=1):
            print(
                f"{idx}) {p.pitch_name or 'Pitch'} | Q {getattr(p, 'quality', '?')}"
                f" BL {getattr(p, 'break_level', '?')}"
                f" | H {getattr(p, 'h_break_mult', 1.0):.2f} V {getattr(p, 'v_break_mult', 1.0):.2f}"
                f" | Rel {getattr(p, 'release_height', 6.0):.2f} Ext {getattr(p, 'extension', 6.0):.2f}"
            )
        print("0) Back")
        sel = input("Select pitch to edit: ").strip()
        if sel == "0" or sel.lower() == "exit":
            return
        try:
            choice_idx = int(sel)
        except ValueError:
            continue
        if choice_idx < 1 or choice_idx > len(pitches):
            continue

        pitch = pitches[choice_idx - 1]
        try:
            h_val = input(f"H break mult [{pitch.h_break_mult:.2f}]: ").strip()
            v_val = input(f"V break mult [{pitch.v_break_mult:.2f}]: ").strip()
            rel_val = input(f"Release height ft [{pitch.release_height:.2f}]: ").strip()
            ext_val = input(f"Extension ft [{pitch.extension:.2f}]: ").strip()
            qual_val = input(f"Quality [{pitch.quality}]: ").strip()
            brk_val = input(f"Break level [{pitch.break_level}]: ").strip()

            if h_val:
                pitch.h_break_mult = float(h_val)
            if v_val:
                pitch.v_break_mult = float(v_val)
            if rel_val:
                pitch.release_height = float(rel_val)
            if ext_val:
                pitch.extension = float(ext_val)
            if qual_val:
                pitch.quality = int(qual_val)
            if brk_val:
                pitch.break_level = int(brk_val)

            if session:
                session.add(pitch)
                session.commit()
            print("Pitch updated.")
            time.sleep(1)
        except Exception as exc:
            print(f"Update failed: {exc}")
            time.sleep(1)
            continue


def open_debug_menu(*, context=None, session=None, state=None):
    enable_debug_mode()
    if session is None and context is not None:
        session = getattr(context, "session", None)

    while True:
        clear_screen()
        print(f"{Colour.MAGENTA}{Colour.BOLD}=== DEBUG MASTER MODE (30062004) ==={Colour.RESET}")
        print("1) Set date (year/month/week)")
        print("2) Fast set all player stats (value)")
        print("3) Add ability points / trust / morale / fatigue")
        print("4) Jump to key weeks (15 qualifiers / 48 spring)")
        print("5) Quick exhibition vs school id")
        print("6) Give max stats (99) + full stamina")
        print("7) Play full match vs school id (turn-based)")
        print("8) Edit pitch shape / release / extension (pitchers)")
        print("0) Exit debug menu")
        choice = input(">> ").strip().lower()

        if choice == "0":
            return

        if choice == "1":
            if not state:
                print("No game state loaded.")
                time.sleep(1)
                continue
            try:
                year = int(input("Year: ").strip() or state.current_year)
                month = int(input("Month (1-12): ").strip() or state.current_month)
                week = int(input("Week (1-50): ").strip() or state.current_week)
                state.current_year = max(1, year)
                state.current_month = max(1, min(12, month))
                state.current_week = max(1, min(50, week))
                if session:
                    session.add(state)
                    session.commit()
                print("Date updated.")
            except Exception as exc:
                print(f"Failed to update date: {exc}")
            time.sleep(1)
            continue

        if choice == "2":
            player = _get_player(context, session, state)
            if not player:
                print("No active player.")
                time.sleep(1)
                continue
            try:
                val = int(input("Set all core stats to: ").strip() or 99)
                _set_player_stats(player, all_value=val)
                if session:
                    session.add(player)
                    session.commit()
                print("Stats updated.")
            except Exception as exc:
                print(f"Failed: {exc}")
            time.sleep(1)
            continue

        if choice == "3":
            player = _get_player(context, session, state)
            if not player:
                print("No active player.")
                time.sleep(1)
                continue
            try:
                ap = input("Add ability points: ").strip()
                trust = input("Set trust baseline (leave blank to skip): ").strip()
                morale = input("Set morale (0-100, blank skip): ").strip()
                fatigue = input("Set fatigue (0-100, blank skip): ").strip()
                if ap:
                    player.ability_points = (player.ability_points or 0) + int(ap)
                if trust:
                    player.trust_baseline = int(trust)
                if morale:
                    player.morale = int(morale)
                if fatigue:
                    player.fatigue = int(fatigue)
                if session:
                    session.add(player)
                    session.commit()
                print("Player state updated.")
            except Exception as exc:
                print(f"Failed: {exc}")
            time.sleep(1)
            continue

        if choice == "4":
            if not state:
                print("No game state loaded.")
                time.sleep(1)
                continue
            jump = input("Jump to 15 (qualifiers) or 48 (spring) or custom week: ").strip()
            try:
                target = int(jump or 15)
                state.current_week = max(1, min(50, target))
                state.current_month = max(1, min(12, ((state.current_week - 1) // 4) + 1))
                if session:
                    session.add(state)
                    session.commit()
                print(f"Jumped to week {state.current_week}.")
            except Exception as exc:
                print(f"Failed: {exc}")
            time.sleep(1)
            continue

        if choice == "5":
            if not session or not state:
                print("Need an active session and state.")
                time.sleep(1)
                continue
            try:
                user_school_id = input("Your school id (blank = active player's school): ").strip()
                if not user_school_id:
                    user_school_id = _resolve_user_school_id(session, state)
                else:
                    user_school_id = int(user_school_id)
                opp = int(input("Opponent school id: ").strip())
                _quick_exhibition(session, user_school_id, opp)
            except Exception as exc:
                print(f"Failed: {exc}")
                time.sleep(1)
            continue

        if choice == "6":
            player = _get_player(context, session, state)
            if not player:
                print("No active player.")
                time.sleep(1)
                continue
            _set_player_stats(player, all_value=99)
            try:
                player.fatigue = 0
                player.stamina = 99
                player.morale = 100
                if session:
                    session.add(player)
                    session.commit()
                print("Maxed stats and refreshed player.")
            except Exception as exc:
                print(f"Failed: {exc}")
            time.sleep(1)
            continue

        if choice == "7":
            if not session or not state:
                print("Need an active session and state.")
                time.sleep(1)
                continue
            try:
                home_id_raw = input("Your school id (blank = active player's school): ").strip()
                home_id = int(home_id_raw) if home_id_raw else _resolve_user_school_id(session, state)
                if not home_id:
                    print("Could not resolve your school id.")
                    time.sleep(1)
                    continue
                away_id = int(input("Opponent school id: ").strip())
                persist = input("Save results to DB? (y/N): ").strip().lower() == "y"
                manual_fielding = input("Manual fielding prompts? (y/N): ").strip().lower() == "y"
                print("Starting full match (turn-based)...")
                run_match(
                    home_id,
                    away_id,
                    fast=False,
                    persist_results=persist,
                    human_team_ids=[home_id],
                    hero_setting="often",
                    force_hero=True,
                    manual_pitch_calls=True,
                    manual_swing_prompts=True,
                    manual_fielding_prompts=manual_fielding,
                    session=session,
                )
                input("Match finished. Press Enter to return to debug menu...")
            except Exception as exc:
                print(f"Failed: {exc}")
                time.sleep(1)
            continue

        if choice == "8":
            player = _get_player(context, session, state)
            if not player:
                print("No active player.")
                time.sleep(1)
                continue
            _edit_pitch_shapes(session, player)
            continue
