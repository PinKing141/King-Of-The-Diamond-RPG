from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple


class AtBatNode(Enum):
    SETUP = auto()
    DECISION = auto()
    PITCH = auto()
    CONTACT = auto()
    RESOLUTION = auto()
    POST_PLAY = auto()
    DONE = auto()


@dataclass
class AtBatEvent:
    name: str
    payload: Dict[str, Any]


@dataclass
class AtBatState:
    node: AtBatNode
    context: Dict[str, Any]


class AtBatStateMachine:
    """Explicit, single-step at-bat state machine.

    Each call to `advance(input_payload)` moves to the next node and emits events.
    No internal while/continue loops; callers drive the pacing.
    """

    def __init__(self, *, context: Optional[Dict[str, Any]] = None) -> None:
        self.state = AtBatState(node=AtBatNode.SETUP, context=context or {})
        self._finished = False

    def advance(self, user_input: Optional[Dict[str, Any]] = None) -> Tuple[AtBatState, List[AtBatEvent]]:
        if self._finished:
            return self.state, []

        handler = {
            AtBatNode.SETUP: self._handle_setup,
            AtBatNode.DECISION: self._handle_decision,
            AtBatNode.PITCH: self._handle_pitch,
            AtBatNode.CONTACT: self._handle_contact,
            AtBatNode.RESOLUTION: self._handle_resolution,
            AtBatNode.POST_PLAY: self._handle_post_play,
        }.get(self.state.node)

        if handler is None:
            self._finished = True
            self.state = AtBatState(node=AtBatNode.DONE, context=self.state.context)
            return self.state, []

        next_node, events = handler(user_input or {})
        self.state = AtBatState(node=next_node, context=self.state.context)
        if next_node == AtBatNode.DONE:
            self._finished = True
        return self.state, events

    # --- Node Handlers ---
    def _handle_setup(self, _: Dict[str, Any]) -> Tuple[AtBatNode, List[AtBatEvent]]:
        return AtBatNode.DECISION, [AtBatEvent("ATBAT_SETUP", self.state.context.copy())]

    def _handle_decision(self, input_payload: Dict[str, Any]) -> Tuple[AtBatNode, List[AtBatEvent]]:
        self.state.context.update({"decision": input_payload})
        return AtBatNode.PITCH, [AtBatEvent("ATBAT_DECISION", input_payload)]

    def _handle_pitch(self, input_payload: Dict[str, Any]) -> Tuple[AtBatNode, List[AtBatEvent]]:
        self.state.context.update({"pitch": input_payload})
        return AtBatNode.CONTACT, [AtBatEvent("ATBAT_PITCH", input_payload)]

    def _handle_contact(self, input_payload: Dict[str, Any]) -> Tuple[AtBatNode, List[AtBatEvent]]:
        self.state.context.update({"contact": input_payload})
        return AtBatNode.RESOLUTION, [AtBatEvent("ATBAT_CONTACT", input_payload)]

    def _handle_resolution(self, input_payload: Dict[str, Any]) -> Tuple[AtBatNode, List[AtBatEvent]]:
        self.state.context.update({"resolution": input_payload})
        return AtBatNode.POST_PLAY, [AtBatEvent("ATBAT_RESOLUTION", input_payload)]

    def _handle_post_play(self, input_payload: Dict[str, Any]) -> Tuple[AtBatNode, List[AtBatEvent]]:
        self.state.context.update({"post_play": input_payload})
        return AtBatNode.DONE, [AtBatEvent("ATBAT_POST_PLAY", input_payload)]
