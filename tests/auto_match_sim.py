import unittest
from unittest.mock import patch
from world_sim.tournament_sim import TournamentSim
from match_engine.controller import MatchController
from database.setup_db import get_session, School
from game.pitch_minigame import trigger_pitch_minigame

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
        with patch('game.pitch_minigame.trigger_pitch_minigame', side_effect=fake_minigame):
            sim = TournamentSim(home, away, session, user_school_id=home.id)
            # Run innings until game ends
            try:
                while not sim.is_game_over():
                    sim.play_inning()
            except Exception as e:
                self.fail(f"Match simulation crashed: {e}")
            # Check final score
            self.assertIsNotNone(sim.scoreboard.innings)
            self.assertGreaterEqual(len(sim.scoreboard.innings), 1, "Game should record at least one inning.")

if __name__ == "__main__":
    unittest.main()
