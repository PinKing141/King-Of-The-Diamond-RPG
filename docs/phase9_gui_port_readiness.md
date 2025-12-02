# Phase 9: GUI Port Readiness (Future)

🖼️ **Objective:** Final preparation for Godot/Web interface parity.

- [ ] **API Bridge** — add `api_bridge.py` at the project root as the single entry point Godot/Web clients call into. It should expose well-named functions for hero generation, scheduling, save/load, and return-only serializable data.
- [ ] **JSON Responses** — audit core gameplay helpers (creation, scheduling, sim runners) so their primary entrypoints return clean JSON (dict/list/primitive only) that the GUI layer can consume without additional marshaling.
- [ ] **Error Handling** — define a structured error payload (e.g., `{ "ok": false, "error": { "code": "...", "details": "..." } }`) and ensure all bridge-accessible functions wrap exceptions into that contract for predictable UI messaging.

> Track these items before starting the Godot or Web client so the runtime surface is predictable and testable.
