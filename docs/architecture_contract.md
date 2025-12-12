# Architecture Contract

Guidelines for keeping the project maintainable and predictable.

- Entry points: `main.py` owns menu flow; `SeasonManager` owns season loop; `match_engine.controller.run_match/resolve_match` is the only way to run a game. Avoid new ad-hoc entry scripts.
- UI/IO: use `core.io_interface.IOInterface`/`NoOpIO` abstractions and the event bus (`core.event_bus.EventBus`). Do not import UI from domain logic; presentation subscribes to events.
- Session/DB: construct sessions via `core.services.SessionProvider` or `database.setup_db.get_session`; never create raw engines in feature code. Schema changes go through Alembic and `ensure_*_schema` helpers.
- Config/data: load gameplay data only through `core.config_loader.ConfigLoader`/`SeasonConfigLoader`; do not open JSON directly elsewhere.
- World sim: import strengths/rosters through `world_sim.services.sim_data` (and its cache helpers). `world_sim.data_access` remains a shim and should not be referenced by new code.
- Match engine: orchestrate through `match_engine.controller.MatchController`/`run_match`; `match_engine.pregame.prepare_match` constructs `MatchState`; `match_engine.match_sim.MatchSimulation` stays deterministic/pure aside from its bus IO. Avoid writing new flows that bypass these.
- RNG and caches: pass RNG via state or constructor; do not call `random` module directly in new code. Use `world_sim.strength_cache` helpers and scoped contexts to prevent bleed between sims.
- Domain boundaries: 
  - UI → services/domain via interfaces and events.
  - Domain → data via repositories/services, not UI.
  - Tests may use fixtures/factories but should honor the same public surfaces.
- Testing: keep behavioral coverage under `tests/` using existing patterns (match sim/controller, strength cache, config loader). Prefer unit-style tests over integration scripts.

When adding new features, answer: which layer owns this? what is its public surface? does it respect these import directions? If not, refactor before merging.
