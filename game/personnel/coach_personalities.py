import random

from core.config_loader import ConfigLoader


def _load_coach_archetypes():
    data = ConfigLoader.get_section("coach_archetypes", {}) or {}
    if data:
        return data
    # Fallback to legacy defaults if config missing
    return {
        "Stoic": {"bias": "balanced", "dialogue": "brief", "buff": "composure"},
        "Gruff": {"bias": "power", "dialogue": "harsh", "buff": "toughness"},
        "Tactical": {"bias": "defense", "dialogue": "smart", "buff": "iq"},
        "Relentless": {"bias": "stamina", "dialogue": "intense", "buff": "endurance"},
        "Charismatic": {"bias": "balanced", "dialogue": "smooth", "buff": "morale"},
        "Unorthodox": {"bias": "trickery", "dialogue": "weird", "buff": "instinct"},
        "Disciplined": {"bias": "defense", "dialogue": "formal", "buff": "control"},
        "Mentorly": {"bias": "balanced", "dialogue": "warm", "buff": "growth"},
        "Energetic": {"bias": "speed", "dialogue": "loud", "buff": "speed"},
        "Cunning": {"bias": "trickery", "dialogue": "sly", "buff": "steal"},
        "Serene": {"bias": "balanced", "dialogue": "calm", "buff": "recovery"},
        "Intense": {"bias": "power", "dialogue": "scary", "buff": "clutch"},
        "Eccentric": {"bias": "trickery", "dialogue": "riddle", "buff": "adaptability"},
        "Nurturing": {"bias": "defense", "dialogue": "gentle", "buff": "trust"},
        "Strict": {"bias": "standard", "dialogue": "harsh", "buff": "discipline"},
        "Observant": {"bias": "tactical", "dialogue": "detail", "buff": "technique"},
        "Ruthless": {"bias": "aggro", "dialogue": "cold", "buff": "power"},
        "Passionate": {"bias": "aggro", "dialogue": "loud", "buff": "spirit"},
        "Whimsical": {"bias": "random", "dialogue": "weird", "buff": "luck"},
        "Logical": {"bias": "tactical", "dialogue": "robot", "buff": "analytics"},
        "Philosophical": {"bias": "balanced", "dialogue": "riddle", "buff": "mental"},
        "Old-School": {"bias": "bunt", "dialogue": "grumpy", "buff": "grit"},
        "Maverick": {"bias": "gambler", "dialogue": "cocky", "buff": "clutch"},
    }


COACH_ARCHETYPES = _load_coach_archetypes()


def get_personality_profile(persona_key: str):
    return COACH_ARCHETYPES.get(persona_key, COACH_ARCHETYPES.get("Stoic", {}))


def get_random_personality(rng: random.Random | None = None) -> str:
    picker = rng or random
    return picker.choice(list(COACH_ARCHETYPES.keys()))
