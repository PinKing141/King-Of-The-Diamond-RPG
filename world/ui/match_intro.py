from __future__ import annotations

from typing import Iterable, List, Optional

from game.story.captain_speech import run_team_huddle

from ui.ui_display import Colour, clear_screen


def _support_tier(team, tournament_name: Optional[str]) -> int:
    if not team:
        return 0
    tourney = (tournament_name or "")
    if "koshien" in str(tourney).lower():
        return 3
    prestige = getattr(team, "prestige", 0) or 0
    era = getattr(team, "current_era", "REBUILDING") or "REBUILDING"
    tier = 0
    if prestige >= 20:
        tier = 1
    if prestige >= 45:
        tier = 2
    if prestige >= 75:
        tier = 3
    if era == "DARK_HORSE":
        tier = min(3, tier + 1)
    elif era == "SLEEPING_LION":
        tier = max(1, tier - 1)
    return tier


def _star_player(lineup: Iterable) -> Optional[str]:
    best = None
    best_score = -1
    for p in lineup or []:
        if p is None:
            continue
        score = getattr(p, "overall", 0) or 0
        if score > best_score:
            best_score = score
            best = p
    if not best:
        return None
    name = getattr(best, "last_name", None) or getattr(best, "name", "Star")
    return f"{name} (OVR {best_score})"


def _lineup_blurb(team, lineup, tournament_name: Optional[str]) -> str:
    name = getattr(team, "name", "Team")
    era = getattr(team, "current_era", "REBUILDING") or "REBUILDING"
    prestige = getattr(team, "prestige", None)
    prestige_txt = f"Prestige {prestige}" if prestige is not None else "Prestige ?"
    tier = _support_tier(team, tournament_name)
    star = _star_player(lineup)
    star_txt = f" | Star: {star}" if star else ""
    return f"{name} — Era: {era} | Band Tier: {tier} | {prestige_txt}{star_txt}"


def _scouting_logs(state) -> List[str]:
    logs = getattr(state, "logs", None)
    if not isinstance(logs, list):
        return []
    return [line for line in logs if isinstance(line, str) and line.startswith("[Scouting Card]")]


def _should_trigger_huddle(state, mode: str) -> bool:
    if mode == "never":
        return False
    if mode == "always":
        return True

    tournament = getattr(state, "tournament_name", None) or getattr(state, "tournament", None) or ""
    round_name = getattr(state, "round_name", None) or getattr(state, "stage", None) or ""
    elimination = bool(getattr(state, "is_elimination", False))
    rivalry = bool(getattr(state, "rival_name", None))

    t_lower = str(tournament).lower()
    r_lower = str(round_name).lower()
    if "koshien" in t_lower or "national" in t_lower:
        return True
    if elimination:
        return True
    if any(tag in r_lower for tag in ["final", "semi", "quarter"]):
        return True
    if rivalry:
        return True
    return False


def render_match_intro(
    state,
    *,
    echo: bool = True,
    show_huddle: bool = False,
    huddle_pause: bool = False,
    huddle_trigger: str = "auto",
    skip_huddle: bool = False,
    allow_identity_pack: bool = False,
) -> List[str]:
    """Render a pre-game scouting card style intro and return lines.

    Huddle shows when show_huddle is True and trigger passes; skip_huddle force-disables.
    """

    lines: List[str] = []
    home = getattr(state, "home_team", None)
    away = getattr(state, "away_team", None)
    home_lineup = getattr(state, "home_lineup", [])
    away_lineup = getattr(state, "away_lineup", [])
    tournament = getattr(state, "tournament_name", None) or getattr(state, "tournament", None)

    header = f"{getattr(away, 'name', 'Away')} @ {getattr(home, 'name', 'Home')}"
    if tournament:
        header = f"{tournament} — {header}"
    lines.append(header)

    hero = getattr(state, "hero_name", None)
    rival = getattr(state, "rival_name", None)
    if hero or rival:
        matchup = f"Face-off: {hero or 'Hero'} vs {rival or 'Rival'}"
        lines.append(matchup)

    weather = getattr(state, "weather", None)
    if weather and hasattr(weather, "describe"):
        lines.append(f"Weather: {weather.describe()}")

    umpire = getattr(state, "umpire", None)
    if umpire:
        ump_name = getattr(umpire, "name", "Umpire")
        ump_desc = getattr(umpire, "description", None)
        desc = f" — {ump_desc}" if ump_desc else ""
        lines.append(f"Plate: {ump_name}{desc}")

    lines.append(_lineup_blurb(home, home_lineup, tournament))
    lines.append(_lineup_blurb(away, away_lineup, tournament))

    lines.extend(_scouting_logs(state))

    if show_huddle and not skip_huddle and _should_trigger_huddle(state, huddle_trigger):
        captain = getattr(state, "captain", None)
        if not captain:
            home_lineup = getattr(state, "home_lineup", [])
            captain = home_lineup[0] if home_lineup else None
        huddle_school = home
        huddle_lines, _ = run_team_huddle(
            captain,
            huddle_school,
            echo=False,
            pause=huddle_pause,
            use_identity_pack=allow_identity_pack,
        )
        if huddle_lines:
            lines.append("Captain's Huddle:")
            lines.extend(huddle_lines)

    if echo:
        clear_screen()
        print(f"{Colour.HEADER}=== MATCH INTRO ==={Colour.RESET}")
        for line in lines:
            print(f" {Colour.CYAN}•{Colour.RESET} {line}")
        print("")

    return lines


__all__ = ["render_match_intro"]
