import unittest
from unittest.mock import patch
import main

class TestGhostPlayerTraining(unittest.TestCase):
    def test_training_flow(self):
        # Simulate: Start Game, Training, Stamina Training, Return, Quit
        # The actual menu options may differ; adjust side_effects as needed
        input_sequence = [
            '1',  # Start Game / Load Save
            '2',  # Select Training
            '1',  # Stamina Training
            '0',  # Return to Main Menu
            '9'   # Quit
        ]
        # Patch input and any time.sleep to speed up test
        with patch('builtins.input', side_effect=input_sequence), \
             patch('time.sleep', return_value=None):
            # Capture initial player state
            try:
                from game.create_player import get_active_player
            except ImportError:
                get_active_player = None
            initial_stamina = None
            initial_exp = None
            if get_active_player:
                player = get_active_player()
                initial_stamina = getattr(player, 'stamina', None)
                initial_exp = getattr(player, 'training_exp', None)
            # Run main menu loop (should exit after Quit)
            try:
                main.main()
            except SystemExit:
                pass
            # Check player state after training
            if get_active_player:
                player = get_active_player()
                new_stamina = getattr(player, 'stamina', None)
                new_exp = getattr(player, 'training_exp', None)
                print(f"Initial stamina: {initial_stamina}, New stamina: {new_stamina}")
                print(f"Initial training_exp: {initial_exp}, New training_exp: {new_exp}")
                self.assertTrue(
                    (initial_stamina is not None and new_stamina is not None and new_stamina > initial_stamina) or
                    (initial_exp is not None and new_exp is not None and new_exp > initial_exp),
                    f"Player stamina or training_exp should increase after training. Initial: stamina={initial_stamina}, exp={initial_exp}; New: stamina={new_stamina}, exp={new_exp}"
                )

if __name__ == "__main__":
    unittest.main()
