Steps
- [x] Add a scoped cache context/helper in strength_cache.py (context manager that clears on exit and can inject an isolated cache instance).
- [x] Update sim entry points (regional_sim.run_autumn_regionals, tournament_sim, prefecture_sim, background sims, sim_utils.quick_resolve_match) to accept/use the scoped cache; default to shared when not provided.
+ [x] Move remaining direct roster/strength queries to sim_data: hothead/captain/relationship flows, ui displays, loops now route through sim_data where practical; kept direct deletes where intentional (graduate_third_years).
+ [ ] Keep a tiny shim in data_access.py but make sim_data the only import surface; deprecate direct imports and adjust callers.
+ [x] Add/extend a fast test ensuring scoped cache isolation (no cross-run bleed) alongside the existing test_regional_strength_cache_limits_calculations.

Further Considerations
- Scope choice: context manager per sim run vs. injectable cache instance in function signatures—chosen context manager with optional explicit cache injection.
- Backward compatibility: keep singleton default to avoid breaking current call sites while new scoped path is adopted.