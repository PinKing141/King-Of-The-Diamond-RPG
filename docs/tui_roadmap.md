# TUI Roadmap (Textual-based)

Scope: replace the current CLI menus with a richer terminal UI using `textual`, starting at the main menu and expanding outward. Keep gameplay logic unchanged; swap only the view layer.

## Phase 1 – Main Menu (now)
- [x] Add `docs/tui_roadmap.md` to track progress.
- [x] Scaffold a `Textual` main menu that mirrors current options and returns the same choice tokens.
- [ ] Gate entry via env flag (`USE_TUI_MAIN_MENU=1`) while keeping console as default.
- [ ] Smoke-test locally once `textual` is installed (optional dependency).

## Phase 2 – Season shell
- [ ] Weekly command menu (next-week, scouting, save, smart-sim) with keybinds.
- [ ] Scouting/character sheet panels (read-only first) with scrollable panes.
- [ ] Save/load selector with slots, confirmation dialogs.

## Phase 3 – In-game overlays
- [ ] Match HUD: scoreboard, basepaths, at-bat log, pitch input prompts, and runner states.
- [ ] Commentary/log stream with filters (all / key plays / debug).
- [ ] Manual pitching/batting prompts with arrow-key navigation.

## Phase 4 – Polish & accessibility
- [ ] Theme tokens (colors, spacing) mapped from existing themes.
- [ ] Keybind help overlay; mouse support optional.
- [ ] Error handling and safe fallback to console view.

## Integration principles
- Keep all business logic in place; only swap the `SeasonView`/menu prompt surfaces.
- Optional dependency: if `textual` is missing, fall back silently to the console menus.
- Reuse existing services/DTOs; avoid duplicating state. Render from existing snapshots/context.
- Keep prompts non-blocking where possible; otherwise mimic current flows to avoid regression.

## Open questions / future items
- Should we expose the debug menu inside the TUI (keybind) or keep it CLI-only?
- Do we want live stat widgets (battery sync, momentum) during games?
- Should the TUI also cover character creation, or remain on the console flow?"
