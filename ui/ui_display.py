import json
import os
from typing import Optional, Tuple

from database.setup_db import Player

class Colour:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    RESET = '\033[0m'
    BOLD = '\033[1m'
    GOLD = '\033[93m'
    
    # Semantic Aliases
    FAIL = '\033[91m'    # RED
    WARNING = '\033[93m' # YELLOW
    
    # This was the missing line causing your crash:
    gold = '\033[93m'    # Yellow (used for trophies/titles)

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def render_screen(conn, player_data):
    """
    Renders the main game HUD for the provided player snapshot.
    """
    clear_screen()
    
    # --- HEADER ---
    print(f"{Colour.HEADER}{'='*60}")
    print(f"{'KOSHIEN: ROAD TO GLORY':^60}")
    print(f"{'='*60}{Colour.RESET}")
    
    # --- DATE & TIME ---
    date_str = f"Year {player_data['current_year']} | Month {player_data['current_month']} | Week {player_data['current_week']}"
    print(f"{Colour.CYAN}{date_str:^60}{Colour.RESET}")
    print("-" * 60)
    
    # --- PLAYER INFO ---
    name_display = f"{player_data['first_name']} {player_data['last_name']}"
    pos_display = f"{player_data['position']}"
    if player_data['jersey_number'] == 1: pos_display += " (ACE)"
    
    print(f" Name: {Colour.BOLD}{name_display:<20}{Colour.RESET} School: {player_data.get('school_name', 'Unknown')}")
    print(f" Role: {pos_display:<20} Grade:  Year {player_data['year']}")
    print("-" * 60)
    
    # --- ATTRIBUTES ---
    def fmt_stat(val):
        return f"{int(val):<3}" 

    print(f"{Colour.BLUE}[ PITCHING ]{Colour.RESET}            {Colour.GREEN}[ BATTING / FIELDING ]{Colour.RESET}")
    print(f" Control : {fmt_stat(player_data.get('control'))}             Power   : {fmt_stat(player_data.get('power'))}")
    print(f" Velocity: {fmt_stat(player_data.get('velocity'))} km/h        Contact : {fmt_stat(player_data.get('contact'))}")
    print(f" Stamina : {fmt_stat(player_data.get('stamina'))}             Speed   : {fmt_stat(player_data.get('running'))}")
    print(f" Break   : {fmt_stat(player_data.get('breaking_ball'))}             Defense : {fmt_stat(player_data.get('fielding'))}")
    
    # --- STATUS BARS ---
    fatigue = int(player_data.get('fatigue', 0))
    morale = int(player_data.get('morale', 50))
    
    if fatigue < 30: f_col = Colour.GREEN
    elif fatigue < 70: f_col = Colour.YELLOW
    else: f_col = Colour.RED
    
    if morale > 80: m_col = Colour.CYAN
    elif morale > 40: m_col = Colour.GREEN
    else: m_col = Colour.RED

    print("-" * 60)
    print(f" Fatigue: {f_col}{'|' * (fatigue // 5)}{Colour.RESET} ({fatigue}%)")
    print(f" Morale : {m_col}{'|' * (morale // 5)}{Colour.RESET} ({morale}%)")
    print("=" * 60)
    _render_team_load_widget(conn, player_data)

def display_menu():
    print("\nActions:")
    print(" 1. Plan Week")
    print(" 2. Scouting Report")
    print(" 3. Character Sheet")
    print(" 4. System / Save")


def render_clutch_banner(*, inning: int, half: str, count: str, score_diff: int, runners_on: int, label: str = "") -> None:
    """Show a dramatic banner describing the current leverage state."""

    inning_label = f"{half} {inning}"
    score_label = "Tie Game" if score_diff == 0 else ("Down" if score_diff > 0 else "Ahead")
    runner_icons = ["-", "1B", "1B/2B", "Bases Loaded"]
    runners = runner_icons[min(runners_on, 3)]
    heading = label or "High-Leverage Moment"
    print(f"\n{Colour.HEADER}{'=' * 60}{Colour.RESET}")
    print(f"{Colour.BOLD}{heading:^60}{Colour.RESET}")
    print(f"{Colour.CYAN}{inning_label:^60}{Colour.RESET}")
    print(f"Count {count} | {score_label} | Runners: {runners}")
    print(f"{Colour.HEADER}{'=' * 60}{Colour.RESET}")


def render_minigame_ui(cursor_position: float | None, target_window: float, *, show_target: bool = False, quality: float | None = None) -> None:
    """Render the reflex slider bar with optional cursor and quality readout."""

    bar_len = 32
    bar = ["-"] * bar_len
    center_idx = bar_len // 2
    window_half = max(1, int(target_window * bar_len))
    if show_target:
        for idx in range(center_idx - window_half, center_idx + window_half + 1):
            if 0 <= idx < bar_len:
                bar[idx] = "="
    if cursor_position is not None:
        cursor_idx = max(0, min(bar_len - 1, int(cursor_position * (bar_len - 1))))
        bar[cursor_idx] = f"{Colour.BOLD}|{Colour.RESET}"
    print(f"[{''.join(bar)}]")
    if quality is not None:
        color = Colour.GREEN if quality >= 0.7 else Colour.YELLOW if quality >= 0.4 else Colour.RED
        print(f" Quality: {color}{quality:.2f}{Colour.RESET}")


def _format_sync(sync: float | None) -> str:
    if sync is None:
        return "+0.00"
    return f"{sync:+.2f}"


def _format_trust(trust: float | None) -> str:
    if trust is None:
        return "??"
    return f"{int(trust):d}"


def render_battery_call_banner(
    payload: dict,
    *,
    pitcher_name: str = "Pitcher",
    catcher_name: str = "Catcher",
) -> None:
    """Display a short blurb describing the catcher sign that was just offered."""

    phase = (payload.get("phase") or "initial").lower()
    prefix_map = {
        "initial": "[Catcher Sign]",
        "retry": "[New Sign]",
        "locked": "[Pitch Locked]",
        "forced": "[Forced Sign]",
    }
    color_map = {
        "initial": Colour.CYAN,
        "retry": Colour.YELLOW,
        "locked": Colour.GREEN,
        "forced": Colour.RED,
    }
    prefix = prefix_map.get(phase, "[Battery]")
    color = color_map.get(phase, Colour.CYAN)
    pitch_name = payload.get("pitch_name") or "Pitch"
    location = payload.get("location") or "Zone"
    intent = payload.get("intent") or "Normal"
    shakes_allowed = int(payload.get("shakes_allowed", 0) or 0)
    shakes_used = int(payload.get("shakes_used", 0) or 0)
    shakes_left = max(0, shakes_allowed - shakes_used)
    trust_display = _format_trust(payload.get("trust"))
    sync_display = _format_sync(payload.get("sync"))
    reason = payload.get("reason") or ""
    reason_suffix = f" — {reason}" if reason else ""
    print(
        f" {color}{prefix}{Colour.RESET} {catcher_name} wants {pitch_name} ({location}, {intent}){reason_suffix}"
    )
    print(
        f"        Trust {trust_display} | Sync {sync_display} | Shakes left {shakes_left} | Battery with {pitcher_name}"
    )


def render_battery_shake_banner(
    payload: dict,
    *,
    pitcher_name: str = "Pitcher",
    catcher_name: str = "Catcher",
) -> None:
    """Show feedback when the pitcher shakes off the catcher."""

    shakes_allowed = int(payload.get("shakes_allowed", 0) or 0)
    shakes_used = int(payload.get("shakes_used", 0) or 0)
    sync_display = _format_sync(payload.get("sync"))
    print(
        f" {Colour.YELLOW}[Shake-Off]{Colour.RESET} {pitcher_name} waves off {catcher_name}. "
        f"Shakes {shakes_used}/{shakes_allowed} | Sync {sync_display}"
    )


def render_battery_forced_banner(
    payload: dict,
    *,
    pitcher_name: str = "Pitcher",
    catcher_name: str = "Catcher",
) -> None:
    """Highlight when the catcher has to force a pitch after too many shakes."""

    sync_display = _format_sync(payload.get("sync"))
    print(
        f" {Colour.RED}[Forced Call]{Colour.RESET} {catcher_name} overrules {pitcher_name}! "
        f"This one rides despite tension (sync {sync_display})."
    )


def _normalize_error_summary(summary):
    if summary is None:
        return {"home": [], "away": []}
    if isinstance(summary, str):
        try:
            summary = json.loads(summary)
        except (ValueError, json.JSONDecodeError):
            return {"home": [], "away": []}
    if not isinstance(summary, dict):
        return {"home": [], "away": []}
    return {
        "home": summary.get("home", []) or [],
        "away": summary.get("away", []) or [],
    }


def _format_error_list(entries):
    if not entries:
        return "None"
    labels = []
    for entry in entries:
        if isinstance(entry, dict):
            tag = entry.get("tag") or entry.get("position") or "E?"
            rbis = entry.get("rbis") or entry.get("runs") or 0
            labels.append(f"{tag} ({rbis} RBI)" if rbis else tag)
        else:
            labels.append(str(entry))
    return ", ".join(labels) if labels else "None"


def _tilt_counts(state) -> tuple[str, str] | None:
    tilt = getattr(state, "umpire_call_tilt", None) or {}
    home_id = getattr(state.home_team, "id", None)
    away_id = getattr(state.away_team, "id", None)
    home = tilt.get(home_id, {})
    away = tilt.get(away_id, {})
    if not any(home.values()) and not any(away.values()):
        return None
    def _fmt(entry):
        favored = entry.get("favored", 0)
        squeezed = entry.get("squeezed", 0)
        return f"+{favored}/-{squeezed}"
    return _fmt(home), _fmt(away)


def render_box_score_panel(scoreboard, state) -> None:
    """Print a condensed box-score style panel with inning totals and error tags."""

    if not scoreboard or not getattr(scoreboard, "innings", None):
        return

    innings = scoreboard.innings
    away_name = getattr(state.away_team, "name", "Away")
    home_name = getattr(state.home_team, "name", "Home")
    inning_header = "  ".join(f"{i + 1:>2}" for i in range(len(innings)))
    away_scores = []
    home_scores = []
    for away_runs, home_runs in innings:
        away_scores.append(f"{(away_runs if away_runs is not None else ' '):>2}")
        if home_runs is None:
            home_scores.append(" X")
        else:
            home_scores.append(f"{home_runs:>2}")
    total_away = sum(r or 0 for r, _ in innings if r is not None)
    total_home = sum(r or 0 for _, r in innings if r is not None)

    summary = getattr(state, "error_summary", None)
    if not summary and hasattr(scoreboard, "get_error_summary"):
        summary = scoreboard.get_error_summary()
    normalized = _normalize_error_summary(summary)
    away_errors = _format_error_list(normalized.get("away"))
    home_errors = _format_error_list(normalized.get("home"))

    print(f"\n{Colour.HEADER}{'=' * 60}{Colour.RESET}")
    print(f"{Colour.BOLD}POSTGAME BOX SCORE{Colour.RESET}")
    print(f"      INN | {inning_header} |  R |  E")
    print(f"      ----|-{'--' * len(innings)}-|----|----")
    print(
        f"{away_name[:3].upper():>5} | {' '.join(away_scores)} | {total_away:>2} | {len(normalized.get('away', [])):>2}"
    )
    print(
        f"{home_name[:3].upper():>5} | {' '.join(home_scores)} | {total_home:>2} | {len(normalized.get('home', [])):>2}"
    )
    if away_errors != "None" or home_errors != "None":
        print(f" Errors: {away_name[:3]} {away_errors} | {home_name[:3]} {home_errors}")
    tilt_snapshot = _tilt_counts(state)
    if tilt_snapshot:
        home_tilt, away_tilt = tilt_snapshot
        print(f" Umpire Tilt: {away_name[:3]} {away_tilt} | {home_name[:3]} {home_tilt}")
    print(f"{Colour.HEADER}{'=' * 60}{Colour.RESET}")

    rivalry_summary = getattr(state, "rival_postgame", None)
    if rivalry_summary:
        hero_name = rivalry_summary.get("hero_name") or getattr(state, "hero_name", "Hero")
        rival_name = rivalry_summary.get("rival_name") or getattr(state, "rival_name", "Rival")
        record = rivalry_summary.get("record", {})
        wins = record.get("wins", 0)
        losses = record.get("losses", 0)
        heat = rivalry_summary.get("heat_level", 0)
        adaptation = rivalry_summary.get("active_adaptation")
        result = rivalry_summary.get("result", "draw")
        result_map = {
            "hero_win": "Hero Victory",
            "rival_win": "Rival Strikes Back",
            "draw": "Stalemate",
            "other_win": "Neutral Outcome",
        }
        result_label = result_map.get(result, result.title())
        print(f"{Colour.GOLD}*** RIVALRY REPORT ***{Colour.RESET}")
        print(f" {hero_name} vs {rival_name}: {wins}-{losses} | Heat {heat:.1f}")
        print(f" Result: {result_label}")
        if adaptation:
            print(f" Next Counter: +20% recognition on {adaptation.replace('_', ' ').title()}")
        print(f"{Colour.HEADER}{'=' * 60}{Colour.RESET}")


def _render_team_load_widget(conn, player_data) -> None:
    snapshot = _team_fatigue_snapshot(conn, player_data)
    if not snapshot:
        return
    avg_fatigue, avg_stamina = snapshot
    rest_lock = avg_fatigue >= 65.0 and avg_stamina <= 55.0
    caution = avg_fatigue >= 60.0 or avg_stamina <= 58.0
    if rest_lock:
        badge = f"{Colour.FAIL}[REST]{Colour.RESET}"
        status = "Optional practice locked"
    elif caution:
        badge = f"{Colour.WARNING}[EDGE]{Colour.RESET}"
        status = "Workload nearing rest threshold"
    else:
        badge = f"{Colour.GREEN}[READY]{Colour.RESET}"
        status = "Team cleared for optional reps"
    print(f" Team Load {badge}  Fatigue {avg_fatigue:5.1f}% | Stamina {avg_stamina:5.1f}")
    if rest_lock:
        print("  Threshold met (>=65 fatigue & <=55 stamina). Coaches will skip optional workouts.")
    else:
        fatigue_cushion = max(0.0, 65.0 - avg_fatigue)
        stamina_cushion = max(0.0, avg_stamina - 55.0)
        print(
            f"  Cushion to lock: {fatigue_cushion:4.1f} fatigue pts / {stamina_cushion:4.1f} stamina pts"
        )


def _team_fatigue_snapshot(conn, player_data) -> Optional[Tuple[float, float]]:
    if conn is None or player_data is None:
        return None
    session = conn if hasattr(conn, "query") else None
    if session is None:
        return None
    school_id = player_data.get("school_id") if isinstance(player_data, dict) else None
    if not school_id:
        player_id = player_data.get("player_id") if isinstance(player_data, dict) else None
        if player_id:
            try:
                player = session.get(Player, player_id)
            except Exception:
                player = None
            if player:
                school_id = getattr(player, "school_id", None)
    if not school_id:
        return None
    try:
        players = session.query(Player).filter(Player.school_id == school_id).all()
    except Exception:
        return None
    if not players:
        return None
    total_fatigue = 0.0
    total_stamina = 0.0
    count = 0
    for athlete in players:
        total_fatigue += float(getattr(athlete, "fatigue", 0) or 0)
        total_stamina += float(getattr(athlete, "stamina", 0) or 0)
        count += 1
    if count == 0:
        return None
    return (total_fatigue / count, total_stamina / count)


def _format_stat_map(stat_map):
    if not stat_map:
        return "-"
    entries = []
    for stat, value in sorted(stat_map.items()):
        label = stat.replace('_', ' ').title()
        entries.append(f"{label} +{value:.1f}")
    return ", ".join(entries)


def render_weekly_dashboard(summary, *, clear: bool = True) -> None:
    """Present a compact Persona-style report card for completed weeks."""

    if clear:
        clear_screen()

    print(f"{Colour.HEADER}=== WEEK {summary.week_number} REPORT ==={Colour.RESET}")

    if summary.schedule_notes:
        for note in summary.schedule_notes:
            print(f" {Colour.CYAN}•{Colour.RESET} {note}")

    if summary.newsletter:
        print(f"\n{Colour.GREEN}[WEEKLY NEWS]{Colour.RESET}")
        for line in summary.newsletter:
            print(f"  • {line}")

    print(f"\n{Colour.CYAN}[TRAINING RESULTS]{Colour.RESET}")
    print(f"  {_format_stat_map(summary.stat_gains)}")
    if summary.xp_gains:
        print(f"  XP: {_format_stat_map(summary.xp_gains)}")

    if summary.match_outcomes:
        print(f"\n{Colour.YELLOW}[MATCH RESULTS]{Colour.RESET}")
        for match in summary.match_outcomes:
            slot = match.get("slot", "?")
            opponent = match.get("opponent", "Opponent")
            result = match.get("result", "-")
            score = match.get("score", "-")
            color = Colour.GREEN if result == 'WON' else Colour.FAIL if result == 'LOST' else Colour.YELLOW
            print(f"  {slot}: vs {opponent} -> {color}{result}{Colour.RESET} ({score})")

    if summary.events_triggered or summary.highlights:
        print(f"\n{Colour.PURPLE}[NEWS FEED]{Colour.RESET}")
        for event in summary.events_triggered:
            print(f"  ! {event}")
        for highlight in summary.highlights:
            print(f"  ★ {highlight}")

    if summary.warnings:
        print(f"\n{Colour.WARNING}[WARNINGS]{Colour.RESET}")
        for warn in summary.warnings:
            print(f"  ! {warn}")

    if summary.stopped_by_interrupt:
        print(f"\n{Colour.FAIL}[AUTO-SIM INTERRUPTED]{Colour.RESET}")
        for reason in summary.interrupt_reasons:
            print(f"  → {reason}")

    print("\nPress Enter to continue...", end="")
