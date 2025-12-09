# MVC Architecture Guidelines

## Overview

This document outlines the Model-View-Controller (MVC) architecture pattern used in King of the Diamond RPG to separate concerns and enable future UI changes (GUI, web, etc.) without requiring rewrites of game logic.

## Architecture Layers

### Model Layer (Business Logic & Data)

The Model layer contains:
- **Game Logic**: Core gameplay mechanics, calculations, and rules
- **Data Models**: Database entities and domain objects
- **Repositories**: Data access patterns

**Location**: `game/`, `match_engine/`, `battery_system/`, `core/`, `world_sim/`

**Rules**:
- ❌ MUST NOT import from `ui/` modules
- ❌ MUST NOT use `ui.ui_display.Colour` or other UI-specific classes
- ❌ MUST NOT call `print()` with color codes directly
- ✅ MUST use `IOInterface` protocol for all user interactions
- ✅ MUST return structured data (dicts, dataclasses) that views can render
- ✅ CAN use semantic logging levels through `IOInterface.log(message, level="info|warning|error|accent")`

### View Layer (UI/Presentation)

The View layer contains:
- **UI Components**: Console rendering, color schemes, formatting
- **Renderers**: Transform data into visual representations
- **Display Utilities**: Screen management, themes, animations

**Location**: `ui/`, `world/ui/`

**Rules**:
- ✅ CAN import and use color codes, formatting, display functions
- ✅ SHOULD implement protocol interfaces (e.g., `SeasonView`, `IOInterface`)
- ❌ SHOULD NOT contain business logic or game rules
- ✅ SHOULD receive data from controllers/models and render it

### Controller Layer (Coordination)

The Controller layer contains:
- **Managers**: `SeasonManager`, `MatchController` - orchestrate game flow
- **Services**: Coordinate between models and views
- **Schedulers**: Manage timing and sequences

**Location**: `game/loop/`, `match_engine/controller.py`

**Rules**:
- ✅ SHOULD coordinate between Model and View layers
- ✅ SHOULD use View protocols for UI interactions
- ✅ CAN import from both Model and View layers
- ❌ SHOULD minimize direct business logic (delegate to Model)

## Key Interfaces

### IOInterface Protocol

Located in `core/io_interface.py`, this protocol defines the abstraction for all user I/O:

```python
class IOInterface(Protocol):
    def log(self, message: str, *, level: str = "info") -> None: ...
    def prompt(self, prompt: str, *, options: Optional[List[str]] = None) -> str: ...
    def clear(self) -> None: ...
    def wait(self, seconds: float) -> None: ...
```

**Supported levels**: `"info"`, `"warning"`, `"error"`, `"accent"`, `"story"`, `"bold"`, `"muted"`

### SeasonView Protocol

Located in `game/interfaces.py`, defines the contract for seasonal game flow UI:

```python
class SeasonView(Protocol):
    def show_banner(self) -> None: ...
    def show_week_header(self, *, year: int, week: int, week_max: int, month: int) -> None: ...
    def display_info(self, message: str) -> None: ...
    def display_warning(self, message: str) -> None: ...
    def display_error(self, message: str) -> None: ...
    # ... and more
```

## Migration Examples

### Before (Violates MVC)

```python
# game/training_logic.py - BEFORE
from ui.ui_display import Colour

def _announce_milestones(milestones):
    for entry in milestones:
        print(f"{Colour.gold}[MILESTONE]{Colour.RESET} {entry.description}")
```

### After (Follows MVC)

```python
# game/training_logic.py - AFTER
# No UI imports needed!

def apply_scheduled_action(...) -> dict:
    # ... business logic ...
    return {
        "status": "ok",
        "milestones": milestone_unlocks,  # Let the View handle display
        # ...
    }
```

The View layer then handles rendering:

```python
# game/loop/weekly_scheduler_core.py (View coordination)
milestones = details.get("milestones") or []
for entry in milestones:
    label = getattr(entry, "milestone_label", "Milestone")
    self.highlights.append(f"Milestone: {label}")  # View formats it
```

## Benefits of This Separation

1. **UI Flexibility**: Can swap console for GUI, web, or mobile UI without changing game logic
2. **Testing**: Business logic can be tested without UI dependencies
3. **Maintainability**: Changes in one layer don't cascade to others
4. **Reusability**: Game logic can be used in different contexts (headless sim, multiplayer, etc.)
5. **Clarity**: Clear boundaries make code easier to understand

## Current State

### ✅ Already Separated
- Core game context and state management
- Repository pattern for data access
- IOInterface abstraction
- Many controller functions already use protocols

### 🚧 Partially Separated
- `game/loop/weekly_scheduler.py` - Uses IOInterface but still embeds color codes
- `match_engine/commentary.py` - Mixed rendering and logic
- `game/mechanics/pitch_minigame.py` - Interactive minigame needs IOInterface

### 🔄 Recently Improved
- `game/training_logic.py` - Removed direct UI imports
- `game/fielding_system.py` - Uses IOInterface with semantic levels
- `ui/player_profile_renderer.py` - Moved from `game/personnel/` to `ui/`

## Guidelines for New Code

1. **Before importing from `ui/`**: Ask "Is this code part of the view layer?"
2. **For user interactions**: Use `IOInterface` with semantic levels
3. **For data display**: Return structured data, let the view format it
4. **For colors/formatting**: Use semantic levels, not raw color codes
5. **For console output**: Use `io.log()` not `print()`

## Future Work

- Complete refactoring of `game/loop/weekly_scheduler.py` to use semantic levels
- Add `IOInterface` to `pitch_minigame.py`
- Create dedicated renderer classes for complex displays
- Consider adding a GUI view implementation using the same protocols
