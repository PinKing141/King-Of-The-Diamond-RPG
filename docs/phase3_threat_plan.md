# Phase 3 "Threat" Update Plan

## Goals
- Introduce a reusable baserunning engine that can evaluate steals, leads, jumps, slide steps, and pick-off attempts.
- Give pitchers additional pre-pitch decisions (slide step vs. standard, pick-off tries) that trade velocity/control for runner management.
- Expand batter decision logic to include squeeze plays and situational bunts driven by game state tension.

## Baserunning Engine (`world_sim/baserunning.py`)
### Inputs
- `runner` attributes: `speed`, `awareness`, `loyalty` (for risk), skills.
- Pitcher attributes: `delivery_time`, `control`, `velocity`, `stamina`, `pickoff_rating`.
- Catcher attributes: `pop_time`, `arm_strength`, `accuracy`.
- `lead_state`: dynamic structure with `lead_off_distance`, `jump_quality`, `pressure`.
- Environmental context: inning, score differential, crowd pressure modifiers already used elsewhere.

### Derived Variables
- `Runner_Speed_Time`: converts runner speed into time-to-second/third by table or linear conversion.
- `Pop_Time`: base pop time from catcher + catcher fatigue penalty.
- `Delivery_Time`: base pitcher delivery plus modifiers for slide steps (+) or fatigue.
- `Lead_Off_Advantage`: `lead_off_distance * 0.02 + jump_quality * 0.03` (tunable).

### API Surface
- `prepare_runner_state(state, base_index) -> RunnerThreatState`: caches lead distance/jump windows after each pitch.
- `evaluate_slide_step(pitch_context, *, use_slide_step: bool) -> SlideStepResult`: returns `delivery_time`, `velocity_penalty`, `control_penalty` for negotiation loop to use.
- `resolve_steal_attempt(runner_state, pitcher_timing, catcher_timing) -> StealOutcome`: implements `Pop_Time + Delivery_Time > Runner_Speed_Time - Lead_Off_Advantage` formula plus RNG fuzz.
- `simulate_pickoff(pitch_state, runner_state) -> PickoffOutcome`: consumes stamina, compares pitcher pickoff skill vs runner lead to return `picked`, `stamina_delta`, `lead_reset`.

### Events
- Publish `THREAT_LEAD`, `THREAT_PICKOFF`, `THREAT_STEAL` via `EventBus` so commentary/UI can broadcast tension.

## Integration Points
1. **Pitch Negotiation Loop**
   - When pitcher selects slide step, call `evaluate_slide_step`, update velocity/control before pitch logic, log stamina hit if repeated.
   - Provide new menu option (AI + player) to attempt pickoff before delivering pitch; if successful ends PA, else affects lead.

2. **Runner Memory**
   - Store `lead_off_distance` and `jump_quality` per runner on base in `state.base_threat_cache[(runner_id, base)]`.
   - Update after each pitch/throw over; degrade lead on pickoffs/step-offs, improve on fastballs out of zone.

3. **Existing `match_engine.base_running`**
   - Replace simple `resolve_steal_attempt` calls with wrapper around new module to preserve backwards compatibility while adding advanced parameters when available.

## Squeeze/Bunt Logic
- Extend `match_engine/batter_logic.py` (or `batter_system`) to check game situation: inning >= 7, score diff within 1-2 runs, runner on 3rd or 2nd/less than 2 outs.
- Introduce `BuntIntent` data describing direction guess based on pitch location quadrant (high FB harder to deaden, low breaking easier -> apply contact penalty/bonus).
- Add event `OFFENSE_CALLS_SQUEEZE` for UI.

## Testing Strategy
- Unit tests for steal resolution edge cases (huge lead, elite catcher) using deterministic inputs.
- Tests for slide step output verifying velocity/control penalties applied.
- Scenario tests for squeeze logic verifying bunts only triggered in clutch states and direction modifiers applied to batted ball result probabilities.
