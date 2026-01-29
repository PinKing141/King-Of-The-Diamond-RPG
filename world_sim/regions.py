# The 8 Blocks of Japanese High School Baseball

# Prefecture-to-region mapping follows the Autumn/Spring tournament blocks.
REGION_MAP = {
    "Hokkaido-Tohoku": ["Hokkaido", "Hokkaido North", "Hokkaido South", "Aomori", "Iwate", "Akita", "Yamagata", "Miyagi", "Fukushima"],
    "Kanto": ["Ibaraki", "Tochigi", "Gunma", "Saitama", "Chiba", "Kanagawa", "Yamanashi"],
    "Tokyo": ["Tokyo"],  # Tokyo is often its own block due to school density
    "Hokushin-etsu": ["Niigata", "Nagano", "Toyama", "Ishikawa", "Fukui"],
    "Tokai": ["Shizuoka", "Aichi", "Gifu", "Mie"],
    "Kinki": ["Shiga", "Kyoto", "Osaka", "Hyogo", "Nara", "Wakayama"],
    "Chugoku-Shikoku": [
        "Tottori",
        "Shimane",
        "Okayama",
        "Hiroshima",
        "Yamaguchi",
        "Tokushima",
        "Kagawa",
        "Ehime",
        "Kochi",
    ],
    "Kyushu": ["Fukuoka", "Saga", "Nagasaki", "Kumamoto", "Oita", "Miyazaki", "Kagoshima", "Okinawa"],
}


def get_region_for_prefecture(pref_name: str) -> str:
    """Return the region block label for a given prefecture name."""
    pref = pref_name.strip()
    for region, prefs in REGION_MAP.items():
        if pref in prefs:
            return region
    if pref.lower() == "hokkaido":
        return "Hokkaido-Tohoku"
    return "Unknown"
