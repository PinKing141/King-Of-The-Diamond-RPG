# The 8 Blocks of Japanese High School Baseball

# Prefecture-to-region mapping follows the Autumn/Spring tournament blocks.
REGION_MAP = {
    "Hokkaido-Tohoku": ["Hokkaido", "Aomori", "Iwate", "Akita", "Yamagata", "Miyagi", "Fukushima"],
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
    for region, prefs in REGION_MAP.items():
        if pref_name in prefs:
            return region
    return "Unknown"
