import unittest
from unittest.mock import patch

from database.setup_db import School, get_session
from game.mechanics.pitch_minigame import trigger_pitch_minigame
from battery_system import battery_negotiation
from match_engine.resolver import resolve_match

class TestMatchSimulationStress(unittest.TestCase):
    def test_match_simulation_stress(self):
        session = get_session()
        schools = session.query(School).order_by(School.id).limit(2).all()
        self.assertGreaterEqual(len(schools), 2, "Need at least two schools for match simulation.")
        home, away = schools[0], schools[1]
        # Patch pitch minigame to always return a high quality result
        def fake_minigame(**kwargs):
            result = trigger_pitch_minigame(
                inning=kwargs.get('inning', 9),
                half=kwargs.get('half', 'Bot'),
                count=kwargs.get('count', '3-2'),
                runners_on=kwargs.get('runners_on', 3),
                score_diff=kwargs.get('score_diff', 0),
                label=kwargs.get('label', 'AutoTest'),
                control_stat=80,
                fatigue_level=10,
                difficulty=0.4,
                auto_resolve=True,
            )
            result.quality = 0.8
            return result
        def fake_negotiation(pitcher, catcher, batter, state, **kwargs):
            pitch = type("_P", (), {"pitch_name": "Auto", "break_level": 50})()
            return battery_negotiation.NegotiatedPitchCall(
                pitch=pitch,
                location="Zone",
                intent="Normal",
                shakes=0,
                trust=60,
                forced=False,
                sync=0.0,
            )

        with patch('game.mechanics.pitch_minigame.trigger_pitch_minigame', side_effect=fake_minigame), \
             patch('builtins.input', return_value='1'), \
             patch('battery_system.battery_negotiation.input', return_value='1'), \
             patch('battery_system.battery_negotiation.print', lambda *args, **kwargs: None), \
             patch('player_roles.pitcher_controls.prompt_runner_threat_controls', return_value=None), \
             patch('battery_system.battery_negotiation.run_battery_negotiation', side_effect=fake_negotiation):
            try:
                winner, score = resolve_match(home, away, "AutoTest", mode="fast", silent=True)
            except Exception as e:
                self.fail(f"Match simulation crashed: {e}")
            self.assertIsNotNone(score)
            self.assertIsNotNone(winner)

if __name__ == "__main__":
    unittest.main()
