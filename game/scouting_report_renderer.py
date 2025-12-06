"""
Team scouting renderer using ui_core primitives.
Supports knowledge levels 0-3 with simple, themeable output.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from database.setup_db import School, Player
from ui.ui_core import clear_screen, colored_bar, simple_bar, panel, BAR_WIDTH


def _team_overview_lines(name: str, prefecture: str, style: str, rank_text: str) -> List[str]:
    return [f"{name} — Prefecture: {prefecture}", f"Style: {style}    Rank: {rank_text}"]


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
        attrs = "VEL/CON: C–A? | CTRL/PWR: C–A?"
        print(f" {jersey:<2} | {pos:<3} | {nm:<22} | {attrs}")
    print("\nKNOWN TENDENCIES (Hints)")
    for t in tendencies_hint:
        print(f"  • {t}")
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
    print("\nMATCHUP STRENGTHS")
    for s in tendencies.get("strengths", []):
        print(f"  • {s}")
    print("\nMATCHUP WEAKNESSES")
    for s in tendencies.get("weaknesses", []):
        print(f"  • {s}")
    input("Press Enter...")


def render_team_report(session, school_id: int, knowledge_level: int = 0, theme_name: Optional[str] = None) -> None:
    school = session.get(School, school_id)
    if not school:
        print("School not found.")
        return

    knowledge_level = max(0, min(3, knowledge_level))
    players = session.query(Player).filter_by(school_id=school.id).order_by(Player.jersey_number).all()

    if knowledge_level == 0:
        return render_level_0(school, theme_name)

    if knowledge_level == 1:
        est = {
            "offense": 55,
            "pitching": 52,
            "defense": 50,
            "speed": 58,
            "coach": getattr(school, "prestige", 50),
        }
        if players:
            est["pitching"] = int(sum((p.velocity or 50) for p in players if p.position == "Pitcher") / max(1, len([p for p in players if p.position == "Pitcher"])))
            est["offense"] = int(sum(((p.contact or 50) + (p.power or 50)) // 2 for p in players if p.position != "Pitcher") / max(1, len([p for p in players if p.position != "Pitcher"])))
        return render_level_1(school, est, theme_name)

    if knowledge_level == 2:
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
        return render_level_2(school, est, partial, tendencies_hint, theme_name)

    # knowledge_level == 3
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
    return render_level_3(school, full_ratings, roster, tendencies, theme_name)


__all__ = [
    "render_team_report",
]
