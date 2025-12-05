# Ability Point / Talent Tree UI Plan

## Entry Point
- Extend the existing player profile overlay (`game/player_profile_renderer.py`) with a new "Pitch Lab" option so players can open the talent tree without leaving the weekly flow.
- Add a shortcut from the weekly planner summary (after schedule execution) to remind users when they earn ability points and offer to open the Pitch Lab immediately.

## Data Requirements
- `player.ability_points` (already tracked) for spend currency.
- Current repertoire / unlocked talent nodes: load via new helper `list_owned_talent_nodes(session, player_id)` that inspects `pitch_repertoire` (tier 1) plus a future persistent table for talent unlocks.
- Unlock candidates: reuse `game.talent_tree.can_unlock_talent` combined with stat data and derived metrics.

## UI Flow
1. Pitch Lab landing page shows:
   - Current Ability Point total.
   - Summary of equipped pitches (tier, quality).
   - Highlighted Coach Order progress if relevant.
2. Menu options per tier:
   - Tier 1: baseline fastballs (always available).
   - Tier 2: show parent requirements and stat thresholds (color-coded pass/fail).
   - Tier 3: mark as "Signature"; include flavour text from `pitch_types`.
3. Selecting a node opens a confirmation modal that lists:
   - Stat requirements (with current values).
   - Derived metric requirements (grip strength, etc.) and their computed scores.
   - Ability Point cost and remaining total after purchase.
   - Warning if unlocking adds a duplicate pitch (prevent duplicate entries).
4. On confirm:
   - Deduct Ability Points.
   - Persist unlocked node (new `player_talents` table or reuse `PitchRepertoire` with metadata flag).
   - Grant pitch (if not already in repertoire) via `_persist_pitch_arsenal` helper, auto-seeding quality/break.
   - Append a short narrative log entry to show immediate impact.

## Tech Tasks
- Create storage for unlocked nodes (likely `PlayerTalent` table linking `player_id`, `node_key`, `acquired_week`).
- Add `talent_tree_service.py` with helpers:
  - `get_player_talent_state(session, player)`
  - `spend_ability_points(player, amount)` (with validation)
  - `unlock_talent_node(session, player, node_key)`.
- Expand `ui/ui_display.py` with a reusable menu renderer that can show requirements in columns (Requirement, Needed, Current, Status).
- Provide automated tests covering:
  - Unlock gating by parents and stats.
  - Ability Point deduction and DB persistence.
  - Duplicate prevention.

## Stretch Goals
- Visual talent tree (ASCII graph) showing unlocked vs locked nodes.
- Passive bonuses tied to certain branches (e.g., unlocking both Tier 1 fastballs grants +2 Control).
- Coach feedback lines when signature pitches unlock.
