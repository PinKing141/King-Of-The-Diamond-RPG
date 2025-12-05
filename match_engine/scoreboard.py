# match_engine/scoreboard.py
from __future__ import annotations

from typing import Any, Optional

from .commentary import commentary_enabled
from .confidence import get_confidence_trends

_POSITION_NUMBERS = {
    "pitcher": "1",
    "p": "1",
    "catcher": "2",
    "c": "2",
    "first base": "3",
    "first baseman": "3",
    "1b": "3",
    "second base": "4",
    "second baseman": "4",
    "2b": "4",
    "third base": "5",
    "third baseman": "5",
    "3b": "5",
    "shortstop": "6",
    "ss": "6",
    "left field": "7",
    "left fielder": "7",
    "lf": "7",
    "center field": "8",
    "center fielder": "8",
    "cf": "8",
    "right field": "9",
    "right fielder": "9",
    "rf": "9",
}


class Scoreboard:
    def __init__(self):
        # List of tuples (away_runs, home_runs) for each inning
        # e.g. [(0, 0), (1, 0), (0, 2)]
        self.innings = [] 
        self._weather_banner_done = False
        self.error_log = {"home": [], "away": []}

    def record_error(
        self,
        team_side: str,
        *,
        position: str | None,
        error_type: str | None,
        runs_scored: int = 0,
    ) -> None:
        key = "home" if (team_side or "").lower().startswith("home") else "away"
        tag = self._format_error_tag(position, error_type)
        entry = {
            "tag": tag,
            "position": position,
            "type": error_type,
            "rbis": max(0, int(runs_scored or 0)),
        }
        self.error_log.setdefault(key, []).append(entry)

    def _format_error_tag(self, position: str | None, error_type: str | None) -> str:
        if not position:
            number = "?"
        else:
            normalized = position.lower().strip().replace("-", " ")
            number = _POSITION_NUMBERS.get(normalized)
        number = number or "?"
        suffix = "(T)" if error_type == "E_THROW" else ""
        return f"E{number}{suffix}"

    def get_error_summary(self) -> dict[str, list[dict[str, object]]]:
        def _clone(entries):
            summary = []
            for entry in entries:
                summary.append(
                    {
                        "tag": entry.get("tag"),
                        "rbis": entry.get("rbis", 0),
                        "position": entry.get("position"),
                        "type": entry.get("type"),
                    }
                )
            return summary

        return {
            "home": _clone(self.error_log.get("home", [])),
            "away": _clone(self.error_log.get("away", [])),
        }

    def record_inning(self, inning_num, away_runs, home_runs):
        """
        Updates the scoreboard for a specific inning.
        """
        # Extend list if needed to reach the inning number
        while len(self.innings) < inning_num:
            self.innings.append([0, 0])
        
        # Inning num is 1-based, list is 0-based
        self.innings[inning_num-1] = [away_runs, home_runs]

    def get_inning_summary(self, inning_num: int | None = None) -> Optional[dict[str, Any]]:
        """Return a lightweight snapshot for telemetry consumers."""
        if not self.innings:
            return None
        inning_num = inning_num or len(self.innings)
        index = max(0, min(len(self.innings) - 1, inning_num - 1))
        away_runs, home_runs = self.innings[index]
        return {
            "inning": index + 1,
            "away_runs": away_runs,
            "home_runs": home_runs,
        }

    def print_board(self, state):
        """
        Prints the ASCII scoreboard to the console.
        """
        if not commentary_enabled():
            return
        weather = getattr(state, 'weather', None)
        if weather and not self._weather_banner_done:
            summary = weather.describe()
            wind = f"Wind {weather.wind_speed_mph:.1f} mph {weather.wind_direction}" if weather.wind_speed_mph is not None else "Wind calm"
            precip = weather.precipitation.title() if weather.precipitation != "none" else "Dry"
            print(f"\n{summary} | {precip} | {wind}")
            self._weather_banner_done = True
        print("\nSCOREBOARD")
        # Header: INN | 1 2 3 ... | R | H | E
        header_inn = "  ".join(f"{i+1}" for i in range(len(self.innings)))
        print(f"INN | {header_inn} | R  | H  | E")
        print("----|-" + "--" * len(self.innings) + "-|----|----|---")
        
        # Calculate totals
        total_away = sum(inn[0] for inn in self.innings if inn[0] is not None)
        total_home = sum(inn[1] for inn in self.innings if inn[1] is not None)
        
        # Away Row
        # If runs is None (e.g. bottom of 9th not played), show 'x' or ' '
        away_scores = "  ".join(f"{inn[0]}" if inn[0] is not None else " " for inn in self.innings)
        away_errors = len(self.error_log.get("away", []))
        home_errors = len(self.error_log.get("home", []))
        print(f"{state.away_team.name[:3]} | {away_scores} | {total_away:<2} | -- | {away_errors:<2}")
        
        # Home Row
        home_scores = "  ".join(f"{inn[1]}" if inn[1] is not None else " " for inn in self.innings)
        print(f"{state.home_team.name[:3]} | {home_scores} | {total_home:<2} | -- | {home_errors:<2}")
        trends = get_confidence_trends(state)
        if trends:
            rising = trends.get("rising")
            falling = trends.get("falling")
            parts = []
            if rising:
                parts.append(f"UP {rising['name']} {rising['value']:+.0f}")
            if falling:
                parts.append(f"DN {falling['name']} {falling['value']:+.0f}")
            if parts:
                print(f"Confidence trends: {' | '.join(parts)}")
        self._print_error_ledger()
        print("")

    def _print_error_ledger(self) -> None:
        if not any(self.error_log.values()):
            return
        if self.error_log.get("away"):
            tags = ", ".join(self._entry_label(entry) for entry in self.error_log["away"])
            print(f"   Away Errors: {tags}")
        if self.error_log.get("home"):
            tags = ", ".join(self._entry_label(entry) for entry in self.error_log["home"])
            print(f"   Home Errors: {tags}")

    def _entry_label(self, entry: dict) -> str:
        label = entry.get("tag", "E?")
        rbis = entry.get("rbis", 0) or 0
        if rbis:
            label = f"{label} ({rbis} RBI)"
        return label