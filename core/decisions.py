from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class DecisionRequest:
    """A UI-agnostic request emitted by game logic.

    kind: semantic hint for the view layer (e.g., "log", "prompt", "render", "clear", "wait").
    message: primary text payload for the request.
    level: optional severity for log-style requests (info/warning/error).
    options: optional constrained options for prompts; hint only.
    default: fallback value the engine will assume if no response is provided.
    input_mode: optional hint for how to capture input (e.g., "line", "menu", "raw").
    cursor: optional starting cursor index for menu input.
    payload: arbitrary structured data for richer renders (state snapshots, stats, etc.).
    """

    kind: str
    message: str = ""
    level: str = "info"
    options: Optional[List[str]] = None
    default: str = ""
    input_mode: str = "line"
    cursor: int = 0
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DecisionResult:
    """Response envelope from a decision-producing routine.

    summary: optional high-level description of what happened.
    requests: ordered list of DecisionRequests for the view to consume.
    done: marks whether the underlying flow is complete.
    data: optional structured payload (e.g., created player id, state snapshot).
    """

    summary: Optional[str]
    requests: List[DecisionRequest]
    done: bool = False
    data: Optional[Dict[str, Any]] = None
