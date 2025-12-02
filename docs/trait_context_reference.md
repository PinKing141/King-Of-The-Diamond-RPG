# Trait and Context Reference

This note summarizes the expanded trait catalog plus the game-context signals that now back situational skills. Use it as the single source of truth when wiring offseason logic, AI decisions, or narrative callouts.

## Trait Categories

| Category   | Purpose | Example keys |
|------------|---------|--------------|
| batting    | Hit tool and baserunning traits that often touch `contact`, `power`, `speed`, or matchup conditions. | `clutch_hitter`, `tough_out`, `platoon_hitter` |
| fielding   | Defensive range, transfers, or throwing traits used by position assignments. | `gold_glove`, `double_play_specialist` |
| pitching   | Mound-specific packages including command, pitch identity, and bullpen roles. | `control_freak`, `strikeout_king`, `bullpen_fireman` |
| mental     | Leadership, volatility dampeners, and aura-style team buffs. | `heart_of_the_team`, `spark_plug`, `selfless` |
| special    | Cross-discipline boosts, durability, or environment driven effects. | `speed_demon`, `mr_utility`, `fearless` |
| negative   | Drawbacks and narrative flaws that impose debuffs or roll penalties. | `glass_cannon`, `slow_start`, `presses` |
| role       | Situation-only boosts tied to lineup slot or pitching assignment. | `pinch_hitter`, `leadoff_catalyst`, `shutdown_closer` |

* Every trait entry lives in `game/trait_catalog.py` with the same metadata shape: `requirements`, `modifiers`, `roll_modifiers`, `ai_tendency`, `synergy_tags`, and `alignment`.
* `synergy_tags` feed the balancing layer so stacking redundant traits naturally introduces diminishing returns.
* Traits can opt out of progression checks by setting `allow_progression=False` (see legacy negative skills for examples).

## Synergy Telemetry

Call `game.skill_system.trait_synergy_summary(player)` to surface trait composition in UI or story beats. The helper returns:

```
{
    "profile": {"speed": 4.0, "aggression": 1.5, ...},
    "buff_scale": 0.92,
    "debuff_scale": 0.78,
    "edge_bonus": 0.14,
}
```

* `profile` sums each `synergy_tags` weight across owned traits.
* `buff_scale` and `debuff_scale` are the live multipliers already applied to passive/situational modifiers.
* `edge_bonus` is a lightweight narrative lever to describe overall edge or instability.
* UI surfaces (for example `ui/scouting_report.print_team_roster`) should read these values instead of recalculating their own heuristics.

## At-Bat Context Keys

`match_engine/context_manager.get_at_bat_context` now publishes a richer dictionary for situational checks. Keys are grouped below; everything is available to traits, AI scripts, and commentary hooks.

### Game Flow
- `inning`, `top_half`, `outs`, `balls`, `strikes`, `score_diff`, `offense_score`, `defense_score`
- `is_late`, `is_close`, `is_clutch`, `pressure_state`, `game_importance`, `is_postseason`, `is_season_opener`
- `score_tied`, `is_trailing`, `defense_trailing`, `momentum`

### Base State
- `runners_on` (bool array for each base) and `runners_detail` (player ids)
- `is_risp`, `risp_count`, `bases_loaded`, `inherited_runners`
- `is_two_strike`, `is_full_count`, `is_cleanup_spot`, `is_leadoff_spot`

### Player Metadata
- `batter_hand`, `pitcher_hand`, `lineup_slot`
- `player_position`, `player_role`, `pitcher_role`
- `is_relief_pitcher`, `is_spot_start`, `is_ace_start`
- `is_pinch_hitting`, `routine_active`

### Form and Momentum
- `hot_streak_length`, `is_hot_streak`, `is_slumping`
- `crowd_factor`, `is_hostile_env`, `has_scouting_edge`

### Team Routing
- `offense_team_id`, `defense_team_id`, `batter_team_id`, `pitcher_team_id`, `is_home_game`

When adding new context consumers, prefer reading these keys to duplicating logic. If you require an additional signal, extend `get_at_bat_context` once so that traits, commentary, and AI all benefit simultaneously.

## Implementation Notes

1. Context dictionaries intentionally keep primitive types (bool/int/float/str) so they serialize cleanly for logging or save states.
2. If a module mutates traits (grant or revoke), call `skill_system.grant_skill_by_key`/`remove_skill_by_key` so caches (`_synergy_*`) stay valid. The `tools/simulation_runner.py skill-admin` CLI exposes these helpers for manual roster edits.
3. Run `tools/simulation_runner.py skill-sync` after upgrading legacy saves; it calls `skill_system.sync_player_skills` to prune unknown keys and deduplicate rows.
4. Always guard UI reveals by knowledge level or scouting tier; the scouting report now shows synergy highlights only when intel is at "Full".
