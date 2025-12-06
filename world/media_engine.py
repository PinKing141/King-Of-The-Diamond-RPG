from __future__ import annotations

from typing import List, Optional, Sequence

from game.weekly_scheduler_core import WeekSummary


def _dedupe(lines: List[str]) -> List[str]:
    seen = set()
    ordered: List[str] = []
    for line in lines:
        if line and line not in seen:
            ordered.append(line)
            seen.add(line)
    return ordered


def _format_match_story(summary: WeekSummary, team_name: str) -> Optional[str]:
    if not summary.match_outcomes:
        return None
    entry = summary.match_outcomes[0]
    slot = entry.get("slot", "Match")
    opponent = entry.get("opponent", "Opponent")
    result = (entry.get("result", "-") or "-").upper()
    score = entry.get("score", "-")
    return f"{team_name} {result} vs {opponent} ({score}) in {slot}."


def generate_weekly_news(
    summary: WeekSummary,
    *,
    team_name: str,
    week: int,
    headlines: Optional[Sequence[str]] = None,
    prestige: Optional[int] = None,
    league_rank: Optional[int] = None,
) -> List[str]:
    """Build a compact set of news blurbs for the week.

    The generator is deterministic given its inputs to keep tests stable.
    """

    lines: List[str] = []
    for headline in headlines or []:
        if headline:
            lines.append(str(headline))

    match_story = _format_match_story(summary, team_name)
    if match_story:
        lines.append(match_story)

    if summary.highlights:
        lines.append(f"Training Spotlight: {summary.highlights[0]}")
    if summary.events_triggered:
        lines.append(f"Campus Buzz: {summary.events_triggered[0]}")
    if summary.warnings:
        lines.append(f"Red Flag: {summary.warnings[0]}")

    if not lines:
        hook = "steady tune-up" if (prestige or 0) >= 60 else "quiet rebuild"
        lines.append(f"Week {week}: {team_name} stays focused — {hook} continues.")

    return _dedupe(lines)[:5]
