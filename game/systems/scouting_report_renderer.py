"""
Team scouting renderer using ui_core primitives.
Supports knowledge levels 0-3 with simple, themeable output.
Adds optional Textual panel rendering (USE_TUI_SCOUTING_PANEL=1).
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional

from database.setup_db import School, Player
from world_sim.services.sim_data import get_roster
from game.battery_profiles import analyze_battery_chemistry
from battery_system.battery_profiles import get_battery_identity
from battery_system.battery_trust import summarize_battery_pair
from ui.ui_core import clear_screen, colored_bar, simple_bar, panel, BAR_WIDTH
from ui.ui_display import Colour


def _team_overview_lines(name: str, prefecture: str, style: str, rank_text: str) -> List[str]:
    return [f"{name} — Prefecture: {prefecture}", f"Style: {style}    Rank: {rank_text}"]


def _report_lines_level0(school: School) -> List[str]:
    return [
        f"SCOUT REPORT — {school.name}",
        "Prefecture: ???",
        "",
        "No intel available. Purchase scouting to begin.",
        "Fog of War: TOTAL BLACKOUT",
    ]


def _report_lines_level1(school: School, est: Dict[str, int]) -> List[str]:
    lines = [
        f"SCOUT REPORT — {school.name}",
        f"Prefecture: {school.prefecture or '??'}",
        "",
        "TEAM OVERVIEW (Basic)",
    ]
    for k, v in est.items():
        lines.append(f"{k.title():<12} ~{v}")
    lines.append("")
    lines.append("Roster: Locked. Purchase more intel to unlock names and stats.")
    return lines


def _report_lines_level2(school: School, est: Dict[str, int], partial_roster: List[Dict], tendencies_hint: List[str]) -> List[str]:
    lines = [
        f"SCOUT REPORT — {school.name} (PARTIAL)",
        f"Prefecture: {school.prefecture or '??'}    Style: {getattr(school, 'philosophy', '???')}",
        "",
        "TEAM RATINGS (Partial)",
    ]
    for k, v in est.items():
        lines.append(f"{k.title():<12} ~{(v//10)*10}-{(v//10)*10 + 20}")
    lines.append("")
    lines.append("PARTIAL ROSTER (Names visible, stats fuzzy)")
    lines.append(" # | POS | NAME")
    for p in partial_roster:
        lines.append(f" {p.get('jersey','--'):>2} | {p.get('position','?'):<3} | {p.get('name','?')}")
    lines.append("")
    lines.append("KNOWN TENDENCIES (Hints)")
    for t in tendencies_hint:
        lines.append(f" - {t}")
    return lines


def _report_lines_level3(school: School, full_ratings: Dict[str, int], roster: List[Dict], tendencies: Dict[str, List[str]]) -> List[str]:
    lines = [
        f"SCOUT REPORT — {school.name} (FULL)",
        f"Prefecture: {school.prefecture or '??'}    Style: {getattr(school, 'philosophy', '???')}",
        "",
        "TEAM RATINGS (Full)",
    ]
    for k, v in full_ratings.items():
        lines.append(f"{k.title():<12} {v}")
    lines.append("")
    lines.append("ROSTER (Full)")
    lines.append(" # | POS | NAME                   | KEY ATTRS")
    for p in roster:
        pos = p.get("position", "?")
        nm = p.get("name", "?")
        jersey = p.get("jersey", "--")
        if pos == "Pitcher":
            attrs = f"VEL {p.get('velocity','--')} | CTRL {p.get('control','--')} | MOV {p.get('movement','--')}"
        else:
            attrs = f"CON {p.get('contact','--')} | POW {p.get('power','--')} | SPD {p.get('speed','--')}"
        lines.append(f" {jersey:<2} | {pos:<3} | {nm:<22} | {attrs}")
    if tendencies:
        lines.append("")
        if tendencies.get("strengths"):
            lines.append("STRENGTHS")
            for t in tendencies.get("strengths", []):
                lines.append(f" - {t}")
        if tendencies.get("weaknesses"):
            lines.append("WEAKNESSES")
            for t in tendencies.get("weaknesses", []):
                lines.append(f" - {t}")
    return lines


def render_level_0(school: School, theme_name: Optional[str] = None) -> None:
    clear_screen()
    lines = _team_overview_lines(school.name, "???", "???", "???")
    panel(f"SCOUT REPORT — {school.name}", [" "] + lines + [" ", "No intel available. Purchase scouting to begin."], theme=theme_name)
    print("\nFog of War: TOTAL BLACKOUT")
    input("Press Enter...")


def render_level_1(school: School, est: Dict[str, int], theme_name: Optional[str] = None) -> None:
    clear_screen()
    lines = _team_overview_lines(school.name, school.prefecture or "??", "???", "??")
    panel(f"SCOUT REPORT — {school.name}", lines, theme=theme_name)
    print("\nTEAM OVERVIEW (Basic)")
    for k, v in est.items():
        bar = colored_bar(v, 100, theme_name)
        print(f" {k.title():<12} {bar}   {v if v is not None else '--'}")
    print("\nRoster: Locked. Purchase more intel to unlock names and stats.")
    input("Press Enter...")


def render_level_2(school: School, est: Dict[str, int], partial_roster: List[Dict], tendencies_hint: List[str], theme_name: Optional[str] = None) -> None:
    clear_screen()
    lines = _team_overview_lines(school.name, school.prefecture or "??", getattr(school, "philosophy", "??"), f"~{getattr(school, 'prestige', '?')}?")
    panel(f"SCOUT REPORT — {school.name} (PARTIAL)", lines, theme=theme_name)
    print("\nTEAM RATINGS (Partial)")
    for k, v in est.items():
        rng = f"~{(v//10)*10}-{(v//10)*10 + 20}?" if v is not None else "~?"
        print(f" {k.title():<12} {colored_bar(v,100,theme_name)}   {rng}")
    print("\nPARTIAL ROSTER (Names visible, stats fuzzy)")
    print(" # | POS | NAME                   | ATTR (Fuzzy)")
    for p in partial_roster:
        pos = p.get("position","?")
        nm = p.get("name","?")
        jersey = p.get("jersey", "--")
        attrs = "VEL/CON: C~A | CTRL/PWR: C~A"
        print(f" {jersey:<2} | {pos:<3} | {nm:<22} | {attrs}")
    print("\nKNOWN TENDENCIES (Hints)")
    for t in tendencies_hint:
        print(f"  - {t}")
    input("Press Enter...")


def render_level_3(school: School, full_ratings: Dict[str, int], roster: List[Dict], tendencies: Dict[str, List[str]], theme_name: Optional[str] = None) -> None:
    clear_screen()
    lines = _team_overview_lines(school.name, school.prefecture or "??", getattr(school, "philosophy", "??"), str(getattr(school, "prestige", "?")))
    panel(f"SCOUT REPORT — {school.name} (FULL)", lines, theme=theme_name)
    print("\nTEAM RATINGS (Full)")
    for k, v in full_ratings.items():
        print(f" {k.title():<12} {colored_bar(v,100,theme_name)}   {v}")
    print("\nROSTER (Full)")
    print(" # | POS | NAME                   | KEY ATTRS")
    for p in roster:
        pos = p.get("position","?")
        nm = p.get("name","?")
        jersey = p.get("jersey","--")
        if pos == "Pitcher":
            attrs = f"VEL {p.get('velocity','--')} | CTRL {p.get('control','--')} | MOV {p.get('movement','--')}"
        else:
            attrs = f"CON {p.get('contact','--')} | POW {p.get('power','--')} | SPD {p.get('speed','--')}"
        print(f" {jersey:<2} | {pos:<3} | {nm:<22} | {attrs}")

    # Battery spotlight: pick a pitcher/catcher and surface chemistry title.
    pitcher = next((p for p in roster if p.get("position") == "Pitcher"), None)
    catcher = next((p for p in roster if p.get("position") == "Catcher"), None)
    if pitcher and catcher:
        class _Stub:
            pass
        p_stub = _Stub()
        c_stub = _Stub()
        for key, val in pitcher.items():
            setattr(p_stub, key, val)
        for key, val in catcher.items():
            setattr(c_stub, key, val)
        state_stub = _Stub()
        state_stub.fast_sim = True  # avoid DB lookups during scouting render
        chemistry = summarize_battery_pair(state_stub, p_stub, c_stub)
        trust_val = chemistry.get("trust", 50) if chemistry else 50
        title, desc, color = analyze_battery_chemistry(p_stub, c_stub, trust_score=trust_val, mech_profile=None)
        identity_title, identity_color = get_battery_identity(p_stub, c_stub, trust_val, None)
        print("\nBATTERY CHEMISTRY")
        print(f"  {title}")
        print(f"  {desc}")
        if identity_title:
            col = identity_color or Colour.RESET
            print(f"  Archetype: {col}{identity_title}{Colour.RESET}")
        if chemistry:
            label = chemistry.get("label", "Unfamiliar")
            trust = chemistry.get("trust", 50)
            wall = chemistry.get("wall", 0)
            sync = chemistry.get("sync", 0.0)
            print(f"  Sync: {label} | Trust {int(trust)} | Wall {int(wall)} | Sync {sync:+.2f}")
    print("\nMATCHUP STRENGTHS")
    for s in tendencies.get("strengths", []):
        print(f"  - {s}")
    print("\nMATCHUP WEAKNESSES")
    for s in tendencies.get("weaknesses", []):
        print(f"  - {s}")
    input("Press Enter...")


def render_team_report(session, school_id: int, knowledge_level: int = 0, theme_name: Optional[str] = None) -> None:
    school = session.get(School, school_id)
    if not school:
        print("School not found.")
        return

    knowledge_level = max(0, min(3, knowledge_level))
    players = get_roster(session, school.id)
    players.sort(key=lambda p: getattr(p, "jersey_number", 0) or 0)

    use_tui = os.environ.get("USE_TUI_SCOUTING_PANEL", "").lower() in {"1", "true", "yes"}
    lines_for_tui: Optional[List[str]] = None

    if knowledge_level == 0:
        if use_tui:
            lines_for_tui = _report_lines_level0(school)
        else:
            return render_level_0(school, theme_name)
    elif knowledge_level == 1:
        est = {
            "offense": 55,
            "pitching": 52,
            "defense": 50,
            "speed": 58,
            "coach": getattr(school, "prestige", 50),
        }
        if players:
            pitch_count = len([p for p in players if p.position == "Pitcher"])
            hitter_count = len([p for p in players if p.position != "Pitcher"])
            est["pitching"] = int(sum((p.velocity or 50) for p in players if p.position == "Pitcher") / max(1, pitch_count))
            est["offense"] = int(sum(((p.contact or 50) + (p.power or 50)) // 2 for p in players if p.position != "Pitcher") / max(1, hitter_count))
        if use_tui:
            lines_for_tui = _report_lines_level1(school, est)
        else:
            return render_level_1(school, est, theme_name)
    elif knowledge_level == 2:
        est = {
            "offense": 60,
            "pitching": 62,
            "defense": 58,
            "speed": 63,
            "coach": getattr(school, "prestige", 55),
        }
        partial = [
            {"name": p.name, "position": p.position, "jersey": p.jersey_number or "--"}
            for p in players[:12]
        ]
        tendencies_hint = ["Aggressive batting approach", "Fastball heavy pitching", "Moderate base-stealing"]
        if use_tui:
            lines_for_tui = _report_lines_level2(school, est, partial, tendencies_hint)
        else:
            return render_level_2(school, est, partial, tendencies_hint, theme_name)
    else:
        full_ratings = {
            "offense": 68,
            "pitching": 72,
            "defense": 63,
            "speed": 64,
            "coach": getattr(school, "prestige", 60),
        }
        roster = [
            {
                "name": p.name,
                "position": p.position,
                "jersey": p.jersey_number or "--",
                "velocity": getattr(p, "velocity", "--"),
                "control": getattr(p, "control", "--"),
                "movement": getattr(p, "movement", "--"),
                "contact": getattr(p, "contact", "--"),
                "power": getattr(p, "power", "--"),
                "speed": getattr(p, "speed", "--"),
            }
            for p in players
        ]
        tendencies = {
            "strengths": ["Strong starting rotation", "Above-average base-running"],
            "weaknesses": ["Inconsistent defense", "Bullpen depth issues"],
        }
        if use_tui:
            lines_for_tui = _report_lines_level3(school, full_ratings, roster, tendencies)
        else:
            return render_level_3(school, full_ratings, roster, tendencies, theme_name)

    if use_tui and lines_for_tui is not None:
        try:
            from ui.tui_panels import run_tui_panel
            run_tui_panel(title="Scouting Report", lines=lines_for_tui)
            return
        except Exception:
            pass

    # Fallback if TUI failed mid-way
    return render_level_0(school, theme_name)


__all__ = [
    "render_team_report",
]
