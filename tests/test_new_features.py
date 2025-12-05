import unittest
from unittest.mock import patch
from core.event_bus import EventBus
from game.pitch_minigame import run_minigame, PitchMinigameContext

class TestEventBus(unittest.TestCase):
    def test_event_publish_and_subscribe(self):
        bus = EventBus()
        self.called = False
        def handler(payload):
            self.called = True
            self.payload = payload
        bus.subscribe('TEST_EVENT', handler)
        bus.publish('TEST_EVENT', {'foo': 'bar'})
        self.assertTrue(self.called)
        self.assertEqual(self.payload, {'foo': 'bar'})

class TestPitchMinigame(unittest.TestCase):
    @patch('builtins.input', return_value='')
    @patch('time.perf_counter', side_effect=[0.0, 0.5])
    def test_run_minigame_auto(self, mock_perf, mock_input):
        # Should return a PitchMinigameResult with quality between 0.0 and 1.0
        context = PitchMinigameContext(inning=1, half='Top', count='3-2', runners_on=1, score_diff=0, label='UnitTest')
        result = run_minigame(
            control_stat=80,
            fatigue_level=10,
            pitch_difficulty=0.5,
            context=context,
            auto_resolve=True,
        )
        self.assertIsNotNone(result)
        self.assertGreaterEqual(result.quality, 0.0)
        self.assertLessEqual(result.quality, 1.0)

if __name__ == "__main__":
    unittest.main()
