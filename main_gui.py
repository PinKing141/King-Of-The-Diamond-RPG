"""
Ursina-powered entry point for King of the Diamond.
"""
from __future__ import annotations

try:
    from ursina import Ursina, Button, Entity, Text, camera, color, window
except ImportError as exc:  # pragma: no cover - only raised when ursina missing
    raise SystemExit("Ursina is required. Install with `pip install ursina`." ) from exc

from game.ursina_bridge import GameRunner


app = Ursina(title="King of the Diamond RPG", borderless=False)

camera.orthographic = True
camera.fov = 10
window.color = color.dark_gray

runner = GameRunner()


def start_game() -> None:
    menu.enabled = False
    runner.start_match(home_id=1, away_id=2)


menu = Entity()
Text(parent=menu, text="KING OF THE DIAMOND", scale=3, origin=(0, 0), position=(0, 0.3))
Button(parent=menu, text="PLAY BALL", scale=(0.3, 0.1), position=(0, 0), on_click=start_game)

app.run()
