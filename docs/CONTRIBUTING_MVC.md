# Contributing to MVC Separation

This is a quick-start guide for contributors working on Model-View-Controller separation in King of the Diamond RPG.

## Quick Rules

### ❌ DON'T Do This

```python
# In business logic (game/, match_engine/, battery_system/, core/)
from ui.ui_display import Colour

def some_game_logic(player):
    print(f"{Colour.GREEN}Victory!{Colour.RESET}")  # ❌ Direct UI in logic
```

### ✅ DO This Instead

```python
# In business logic
def some_game_logic(player, io=None):
    if io:
        io.log("Victory!", level="accent")  # ✅ Use IOInterface with semantic level
    # Or just return data and let the view handle it
    return {"status": "victory", "message": "Victory!"}
```

## Common Patterns

### Pattern 1: Use IOInterface for User Interaction

```python
from core.io_interface import IOInterface

def interactive_function(state, io: IOInterface = None):
    if io:
        io.log("Choose your action:", level="info")
        io.log("1. Train", level="info")
        io.log("2. Rest", level="info")
        choice = io.prompt(">> ")
    else:
        # Fallback for backward compatibility
        print("Choose your action:")
        choice = input(">> ")
    return choice
```

### Pattern 2: Return Structured Data

```python
def calculate_training_result(player, action):
    # Do calculations...
    
    # Return structured data, let view decide how to display
    return {
        "status": "ok",
        "message": "Training complete",
        "stat_changes": {"power": +2, "speed": +1},
        "milestones": milestone_list,  # Let view render these
        "new_fatigue": 45,
    }
```

### Pattern 3: Use Semantic Levels

Instead of color codes, use semantic levels that the view can interpret:

```python
# ❌ Bad
print(f"{Colour.RED}Error!{Colour.RESET}")

# ✅ Good
io.log("Error!", level="error")
```

Available levels:
- `"info"` - Normal information
- `"warning"` - Warnings
- `"error"` - Errors
- `"accent"` - Highlighted/important info
- `"story"` - Story/narrative text
- `"bold"` - Emphasized text
- `"muted"` - De-emphasized text

## Where Each Layer Lives

### Model Layer (Business Logic)
**Location**: `game/`, `match_engine/`, `battery_system/`, `core/`, `world_sim/`

**Responsibility**: Game rules, calculations, data access

**Can import from**: Database models, other business logic, core utilities

**Cannot import from**: `ui/`, `world/ui/`

### View Layer (Presentation)
**Location**: `ui/`, `world/ui/`

**Responsibility**: Display, formatting, colors, user input

**Can import from**: Anywhere (views coordinate everything)

### Controller Layer (Coordination)
**Location**: `game/loop/`, controllers in `match_engine/`

**Responsibility**: Orchestrate flow between model and view

**Can import from**: Both model and view layers

## Migration Checklist

When refactoring a module to separate MVC:

- [ ] Remove `from ui.ui_display import Colour` (and similar)
- [ ] Replace `print()` with `io.log()` using semantic levels
- [ ] Replace `input()` with `io.prompt()`
- [ ] Return structured data instead of rendering directly
- [ ] Add `io: IOInterface = None` parameter if user interaction needed
- [ ] Check that state.io exists if using state pattern
- [ ] Test that functionality still works
- [ ] Update documentation if API changed

## Examples in Codebase

**Good MVC Examples**:
- `game/training_logic.py` - Returns structured data
- `game/fielding_system.py` - Uses IOInterface with semantic levels
- `battery_system/battery_negotiation.py` - Uses state.io pattern
- `core/io_interface.py` - Clean abstraction protocol

**Needs Improvement** (Documented for future work):
- `game/loop/weekly_scheduler.py` - Uses IOInterface but embeds color codes
- `match_engine/commentary.py` - View component in model layer
- `world_sim/*.py` - Direct print with colors

## Testing MVC Separation

A well-separated module should be testable without UI:

```python
# This should work without any UI imports
def test_training_logic():
    context = create_test_context()
    result = apply_scheduled_action(context, "train_power")
    
    assert result["status"] == "ok"
    assert "power" in result["stat_changes"]
    # No need to test console output!
```

## Questions?

See full details in `docs/MVC_ARCHITECTURE.md`
