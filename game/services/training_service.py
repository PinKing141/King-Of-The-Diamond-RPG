import random
from dataclasses import dataclass, field
from typing import Optional

from core.game_context import GameContext
from game import training_logic
from game.services import mappers
from game.services.dtos import PlayerTrainingDTO


@dataclass
class TrainingService:
    """Deterministic wrapper for training actions with injected RNG."""

    rng: random.Random = field(default_factory=random.Random)

    @classmethod
    def with_seed(cls, seed: Optional[int]) -> "TrainingService":
        rng = random.Random(seed) if seed is not None else random.Random()
        return cls(rng=rng)

    def apply_action(
        self,
        context: GameContext,
        action_type: str,
        *,
        commit: bool = True,
        progression_state: Optional[dict] = None,
    ) -> dict:
        state = progression_state or {}
        return training_logic.apply_scheduled_action(
            context,
            action_type,
            commit=commit,
            progression_state=state,
            rng=self.rng,
        )

    def apply_action_dto(
        self,
        player_dto: PlayerTrainingDTO,
        action_type: str,
        *,
        progression_state: Optional[dict] = None,
        progression_service=None,
    ):
        from game.services.training_domain import apply_training_action_dto

        return apply_training_action_dto(
            player_dto,
            action_type,
            rng=self.rng,
            progression_service=progression_service,
            progression_state=progression_state,
        )

    def to_dto(self, player) -> PlayerTrainingDTO:
        return mappers.player_to_training_dto(player)

    def apply_dto(self, player, dto: PlayerTrainingDTO) -> None:
        mappers.apply_training_dto_to_player(player, dto)
