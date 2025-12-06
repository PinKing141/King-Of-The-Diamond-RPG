from game.weekly_scheduler_core import WeekSummary
from world.media_engine import generate_weekly_news


def test_generate_weekly_news_prioritizes_headlines_and_matches():
    summary = WeekSummary(week_number=3)
    summary.match_outcomes = [
        {"slot": "MON Morning", "opponent": "Kosei", "result": "WON", "score": "5-2"}
    ]
    summary.highlights.append("Unlocked skill: Slider Master")
    summary.events_triggered.append("Exam Ace: 88 in Modern Lit")
    summary.warnings.append("Fatigue peaked at 91")

    headlines = ["Dark Horse Alert: Seiran WON vs Kosei (5-2)"]

    news = generate_weekly_news(
        summary,
        team_name="Seiran",
        week=3,
        headlines=headlines,
        prestige=72,
    )

    assert news[0] == headlines[0]
    assert any("Seiran WON vs Kosei" in line for line in news)
    assert any("Training Spotlight" in line for line in news)
    assert any("Red Flag" in line for line in news)
