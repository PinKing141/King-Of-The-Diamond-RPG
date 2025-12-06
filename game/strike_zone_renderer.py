"""
game/strike_zone_renderer.py

Renders a high-fidelity ASCII grid for the strike zone using box-drawing characters.
Supports 5x5 layout (Inner 3x3 Strikes + Outer Ball Ring).
"""
from typing import List, Optional, Union, Dict
from ui.ui_core import choose_theme, clear_screen, Colour, slide_in_panel

# ------------------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------------------

# Map (Row, Col) to Zone IDs
# Rows 0-4, Cols 0-4.
# Center (1,1) to (3,3) is the Strike Zone.
ZONE_MAP = {
    # --- Top Row (Balls) ---
    (0, 0): None, (0, 1): "O1", (0, 2): "O2", (0, 3): "O3", (0, 4): None,
    # --- Upper Middle (Strike Row 1) ---
    (1, 0): "O4", (1, 1): 1,    (1, 2): 2,    (1, 3): 3,    (1, 4): "O5",
    # --- Middle (Strike Row 2) ---
    (2, 0): "O6", (2, 1): 4,    (2, 2): 5,    (2, 3): 6,    (2, 4): "O7",
    # --- Lower Middle (Strike Row 3) ---
    (3, 0): "O8", (3, 1): 7,    (3, 2): 8,    (3, 3): 9,    (3, 4): "O9",
    # --- Bottom Row (Balls) ---
    (4, 0): None, (4, 1): "O10",(4, 2): "O11",(4, 3): "O12",(4, 4): None,
}

HEAT_COLORS = {
    "hot": Colour.RED,
    "warm": Colour.YELLOW,
    "cold": Colour.CYAN,
    "neutral": Colour.RESET,
}

# Use narrow ASCII symbols to avoid double-width glyphs that break alignment
STRIKE_SYMBOLS = {
    "hot": "#",
    "warm": "+",
    "cold": "-",
    "neutral": " ",
}

BALL_SYMBOLS = {
    "active": "o",
    "inactive": ".",
}

HIGHLIGHT_SYMBOL = "*"


def get_zone_id_grid() -> List[List[Union[int, str, None]]]:
    """Return the 5x5 zone layout as IDs so callers can render their own grid."""
    grid: List[List[Union[int, str, None]]] = []
    for r in range(5):
        row: List[Union[int, str, None]] = []
        for c in range(5):
            row.append(ZONE_MAP.get((r, c)))
        grid.append(row)
    return grid

# ------------------------------------------------------------------------------
# RENDERER
# ------------------------------------------------------------------------------

def _get_cell_content(
    zone_id: Union[int, str, None],
    heat_stats: Dict,
    highlight_zone: Union[int, str, None] = None,
    theme: Dict = None,
    *,
    color_reset: str = Colour.RESET,
) -> str:
    """Returns the colored string content for a single cell (3 chars wide)."""

    # 1. Empty/Corner zones
    if zone_id is None:
        return "   "

    # 2. Highlight Logic (e.g., Pitch Location Cursor)
    if zone_id == highlight_zone:
        # Flash this cell with a solid block or target
        return f" {HIGHLIGHT_SYMBOL} "

    # 3. Normal Stats Logic
    stat = heat_stats.get(zone_id, "neutral")
    color = HEAT_COLORS.get(stat, "")

    # Different symbols for Strikes vs Balls
    if isinstance(zone_id, int):
        # Strike Zone: Solid based on heat
        symbol = STRIKE_SYMBOLS.get(stat, " ")
        return f"{color} {symbol} {color_reset}"
    else:
        # Ball Zone: Lighter/Dimmer
        is_active = stat != "neutral"
        symbol = BALL_SYMBOLS["active"] if is_active else BALL_SYMBOLS["inactive"]
        c = color if is_active else theme["muted"]
        return f"{c} {symbol} {color_reset}"


def _draw_row_separator(row_idx: int, theme_color: str, reset: str = Colour.RESET) -> str:
    """Constructs the grid lines (┌───┬───┐) based on row position."""
    # Top of Grid
    if row_idx == 0:
        return f"   {theme_color}┌───┬───┬───┬───┬───┐{reset}"
    # Bottom of Grid
    elif row_idx == 5:
        return f"   {theme_color}└───┴───┴───┴───┴───┘{reset}"
    # Middle dividers
    else:
        return f"   {theme_color}├───┼───┼───┼───┼───┤{reset}"


def render_grid(
    heat_stats: Dict,
    theme_name: Optional[str] = None,
    highlight_zone: Union[int, str, None] = None,
    *,
    color: bool = True,
):
    """Main entry point to draw the 5x5 ASCII grid."""
    theme = choose_theme(theme_name)
    accent = theme["accent"] if color else ""
    reset = Colour.RESET if color else ""
    muted = theme["muted"] if color else ""
    theme_for_cells = dict(theme)
    theme_for_cells["muted"] = muted

    # Draw Top Line
    print(_draw_row_separator(0, accent, reset))

    sep = f"{accent}│{reset}" if color else "│"
    for row in range(5):
        line_parts = []
        for col in range(5):
            zone_id = ZONE_MAP.get((row, col))
            content = _get_cell_content(
                zone_id,
                heat_stats,
                highlight_zone,
                theme_for_cells,
                color_reset=reset,
            )
            line_parts.append(content)

        # Assemble the row with consistent-width separators so ANSI content stays aligned
        row_str = sep.join(line_parts)
        print(f"   {accent}│{reset}{row_str}{accent}│{reset}")

        # Draw Divider Line (except after the very last row)
        print(_draw_row_separator(row + 1, accent, reset))

# ------------------------------------------------------------------------------
# PUBLIC API
# ------------------------------------------------------------------------------

def render_pitch_visual(
    pitch_type: str,
    velocity: int,
    zone: Union[int, str],
    theme_name: str = "persona"
):
    """
    Visualizes a pitch coming in and hitting a specific zone.
    """
    clear_screen()
    th = choose_theme(theme_name)

    print(f"\n{th['accent']}>> {pitch_type} ({velocity} mph) <<{Colour.RESET}\n")

    # 1. Draw "Blank" Grid
    stats = {}
    render_grid(stats, theme_name, highlight_zone=None)

    # 2. Flash Impact (Simple Animation)
    # In a real terminal, we might use time.sleep and reprint.
    # Here we simulate the final frame.
    print(f"\033[13A", end="")  # Move cursor up 13 lines (VT100 code) to overwrite
    render_grid(stats, theme_name, highlight_zone=zone)

    # Footer
    label = "STRIKE" if isinstance(zone, int) else "BALL"
    print(f"\n   Call: {label} {zone}")
    input("   [Press Enter]")


def render_scouting_report(
    player_name: str,
    heat_stats: Dict,
    theme_name: str = "persona"
):
    """
    Displays the static heatmap for a player.
    """
    clear_screen()
    th = choose_theme(theme_name)

    slide_in_panel([
        f"SCOUTING REPORT: {player_name}",
        "■ = Hot Zone (High Contact)",
        "□ = Cold Zone (Whiff Risk)"
    ], width=40, theme=theme_name)

    print()
    render_grid(heat_stats, theme_name)
    print()
    input(f"{th['muted']}[Press Enter to close]{Colour.RESET}")


def describe_location(location: str) -> Dict[str, Union[str, bool]]:
    """Return label and default highlight for a location tag (Zone/Chase)."""
    in_zone = location == "Zone"
    return {
        "label": "IN (strike zone)" if in_zone else "OUT (chase/off)",
        "highlight": 5 if in_zone else "O11",
        "in_zone": in_zone,
    }


def build_grid_lines(
    heat_stats: Dict,
    *,
    theme_name: Optional[str] = None,
    highlight_zone: Union[int, str, None] = None,
    color: bool = True,
) -> List[str]:
    """Return the grid as a list of strings (no clearing/pausing)."""
    theme = choose_theme(theme_name)
    accent = theme["accent"] if color else ""
    reset = Colour.RESET if color else ""
    muted = theme["muted"] if color else ""
    theme_for_cells = dict(theme)
    theme_for_cells["muted"] = muted

    lines: List[str] = []
    lines.append(_draw_row_separator(0, accent, reset))
    sep = f"{accent}│{reset}" if color else "│"

    for row in range(5):
        line_parts = []
        for col in range(5):
            zone_id = ZONE_MAP.get((row, col))
            content = _get_cell_content(
                zone_id,
                heat_stats,
                highlight_zone,
                theme_for_cells,
                color_reset=reset,
            )
            line_parts.append(content)
        row_str = sep.join(line_parts)
        lines.append(f"   {accent}│{reset}{row_str}{accent}│{reset}")
        lines.append(_draw_row_separator(row + 1, accent, reset))

    return lines


def build_pitch_snapshot_lines(
    location: str,
    *,
    heat_stats: Optional[Dict] = None,
    highlight_zone: Union[int, str, None] = None,
    theme_name: Optional[str] = None,
    color: bool = False,
) -> List[str]:
    """Convenience: grid + label for a pitch location (Zone vs Chase)."""
    heat_stats = heat_stats or {}
    info = describe_location(location)
    if highlight_zone is None:
        highlight_zone = info["highlight"]
    lines = build_grid_lines(heat_stats, theme_name=theme_name, highlight_zone=highlight_zone, color=color)
    label = info["label"]
    lines.append(f"   Location: {label}")
    return lines
