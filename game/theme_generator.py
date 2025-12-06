import random

PREFIXES = {
    "Power": ["Iron", "Burning", "Grand", "Savage", "Crimson", "Heavy", "Titan", "Buster"],
    "Speed": ["Lightning", "Sonic", "Flash", "Rapid", "Wind", "Aero", "Mach", "Turbo"],
    "Technical": ["Noble", "Silent", "Phantom", "Clever", "Glass", "Precise", "Cool", "Smart"],
    "Leadership": ["Emperor", "King", "Captain", "Royal", "Golden", "Legendary", "Glorious"],
    "Generic": ["Fighting", "Wild", "Brave", "Final", "Super", "Hyper", "Ultra", "Giga"],
}

SUFFIXES = [
    "Soul",
    "Fang",
    "Impact",
    "Drive",
    "Storm",
    "Beat",
    "Heart",
    "Arrow",
    "Trigger",
    "Zone",
    "Anthem",
    "Roar",
    "Ignition",
    "Paradox",
    "Symphony",
    "Horizon",
]


def generate_player_theme(player):
    """Generate a theme name based on a player's standout traits."""

    archetype = "Generic"
    if getattr(player, "power", 0) > 70:
        archetype = "Power"
    elif getattr(player, "speed", 0) > 70:
        archetype = "Speed"
    elif getattr(player, "contact", 0) > 75:
        archetype = "Technical"
    elif getattr(player, "is_captain", False) or getattr(player, "year", 1) == 3:
        archetype = "Leadership"

    prefix = random.choice(PREFIXES.get(archetype, PREFIXES["Generic"]))
    suffix = random.choice(SUFFIXES)
    return f"{prefix} {suffix}"


def assign_theme_if_eligible(player):
    """Assign a walk-up song to upperclassmen standouts if they don't have one."""

    is_senior = getattr(player, "year", 1) >= 2
    is_good = (getattr(player, "overall", 0) or 0) >= 65
    has_theme = getattr(player, "theme_song", None)
    if is_senior and is_good and not has_theme:
        player.theme_song = generate_player_theme(player)
        return True
    return False


__all__ = ["generate_player_theme", "assign_theme_if_eligible"]
