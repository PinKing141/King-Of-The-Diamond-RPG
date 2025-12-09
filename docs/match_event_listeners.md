# Match Event Listeners

The match engine now accepts a tuple of listener factory callables via `context.match_event_listeners`.

- Each factory is called with the active `EventBus` and optional `IOInterface` (`listener(bus, io=io)`), and should attach its own subscriptions.
- The hook is wired anywhere matches are launched: season loop, weekly scheduler, world sims (prefecture/qualifiers/regionals/tournaments), and the console entrypoint seeds it with `attach_commentary_listener`.
- If no `io` surface is available, listeners should avoid colourized output and rely on plain text (see `ui.match_commentary` fallbacks).

Examples:
- Console UI default:
```python
context.match_event_listeners = (
    lambda bus, io=view.io: attach_commentary_listener(bus, io=io),
)
```

- Stacking listeners (commentary + telemetry):
```python
from ui.match_commentary import attach_commentary_listener
from match_engine.telemetry import attach_telemetry_listener

context.match_event_listeners = (
    lambda bus, io=view.io: attach_commentary_listener(bus, io=io),
    lambda bus, io=view.io: attach_telemetry_listener(bus, io=io),
)
```
Each callable receives the live `EventBus` and the active IO surface; order matters if listeners depend on prior subscriptions.

This keeps presentation concerns out of the engine and makes it easy to swap or stack listeners (telemetry, UI bridges, testing spies).
