"""Building blocks for procedural commentary lines.

Keep physics- and action-focused phrasing here so the engine can mix and match
without hard-coding thousands of strings in logic files.
"""

from __future__ import annotations

# --- COMPONENT POOLS ---
# Verbs for velocity-driven heaters.
VELOCITY_VERBS = [
    "fires",
    "rockets",
    "unleashes",
    "pumps",
    "delivers",
    "hurls",
    "drive-bombs",
    "zips",
    "rifles",
    "deals",
]

# Adjectives that describe raw pace.
VELOCITY_ADJECTIVES = [
    "blistering",
    "scorching",
    "lightning-fast",
    "searing",
    "explosive",
    "supersonic",
    "high-octane",
    "heavy",
    "rising",
]

# Breaker verbs for bendy offerings.
BREAKING_VERBS = [
    "snaps off",
    "drops",
    "bends",
    "spins",
    "carves",
    "floats",
    "dances",
    "vanishes",
]

# Contact sounds for batted balls.
CONTACT_SOUNDS = [
    "crack",
    "thwack",
    "boom",
    "crunch",
    "ping",
]

# Contact outcomes keyed off exit velo/launch angle tiers.
CONTACT_OUTCOMES = [
    "{batter} barrels it at {exit_velo}!",
    "{batter} finds the sweet spot at {exit_velo}, LA {launch_angle}°.",
    "{batter} spoils it, sending a {contact_sound} into foul ground.",
    "{batter} muscles a soft contact at {exit_velo}.",
]

# Location fragments.
LOCATION_TAGS = [
    "upstairs",
    "on the black",
    "at the knees",
    "just off the edge",
    "in the shadow zone",
    "back-doored",
    "front-doored",
]

# Reaction descriptors when hitters whiff.
WHIFF_REACTIONS = [
    "air-guitars through it",
    "is late by a mile",
    "waves helplessly",
    "folds up",
    "gets carved in half",
    "never sees it",
    "chases daylight",
    "is frozen",
]

# Blocked pitch notes for dirt balls.
BLOCK_TEMPLATES = [
    "{catcher} smothers it in the dirt — no advance.",
    "Textbook block by {catcher}; deadens the {pitch_name}.",
    "Chest protector eats it up; runners stay put.",
    "{catcher} slides and walls it — keeps {runner_hint} glued.",
]

# Fielding range openers.
FIELDING_RANGE = [
    "{fielder} ranges far to the {direction}...",
    "Long run for {fielder} into the gap...",
    "{fielder} reads it off the bat and takes off {direction}...",
]

# Fielding catch endings.
FIELDING_CATCH = [
    "and lays out for the snag!",
    "and tracks it down for the out.",
    "leaping grab!",
    "slides and makes it look easy.",
]

# --- TEMPLATE POOLS ---
# Strikeouts fueled by premium velocity.
STRIKEOUT_HIGH_HEAT = [
    "{pitcher} {velo_verb} a {velocity} heater {location} and {batter} swings through it.",
    "Radar pops {velocity}; {pitcher} dares him up in the zone and wins.",
    "A {velo_adj} fastball at {velocity} blows past {batter} for the K.",
    "{pitcher} just challenges him with {velocity} up and gets the empty hack.",
    "{velocity} from {pitcher} — {batter} is late and walks back shaking his head.",
    "Pure gas: {pitcher} climbs the ladder at {velocity}; {batter} never catches up.",
]

# Strikeouts via bend and deception.
STRIKEOUT_BREAKING = [
    "{pitcher} {break_verb} a nasty {pitch_name} that falls off the table for strike three.",
    "{batter} is fishing as the {pitch_name} vanishes below the zone.",
    "Knees buckle on a disappearing {pitch_name}; {pitcher} paints it at {location}.",
    "Pulls the string — the {pitch_name} drifts then dives for the punchout.",
    "That {pitch_name} starts middle and ends nowhere near the barrel. Sit down, {batter}.",
]

# Strikeouts from finesse / command.
STRIKEOUT_FINESSE = [
    "{pitcher} dots a {pitch_name} {location}; {batter} is frozen looking.",
    "Pitch tunneling masterclass — {pitch_name} sneaks by for strike three.",
    "Edge attack: {pitcher} clips the corner with a {pitch_name}.",
    "{pitcher} sequences perfectly and steals the edge with a {pitch_name} for the K.",
]

# Generic fallback so we never emit nothing.
STRIKEOUT_GENERIC = [
    "{pitcher} wins the duel with a {pitch_name}.",
    "Strike three! {pitcher} out-executes {batter}.",
]

__all__ = [
    "VELOCITY_VERBS",
    "VELOCITY_ADJECTIVES",
    "BREAKING_VERBS",
    "CONTACT_SOUNDS",
    "CONTACT_OUTCOMES",
    "LOCATION_TAGS",
    "WHIFF_REACTIONS",
    "BLOCK_TEMPLATES",
    "FIELDING_RANGE",
    "FIELDING_CATCH",
    "STRIKEOUT_HIGH_HEAT",
    "STRIKEOUT_BREAKING",
    "STRIKEOUT_FINESSE",
    "STRIKEOUT_GENERIC",
]
