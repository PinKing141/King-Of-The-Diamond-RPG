from __future__ import annotations

import random
from typing import Dict, List, Optional, Tuple

DEFAULT_STYLE = "ARCHITECT"

# Map school philosophies to captain speech styles
STYLE_BY_PHILOSOPHY: Dict[str, str] = {
    "Machine Gunners": "SLASHER",
    "Slugger Army": "COMMANDER",
    "Precision Machines": "ARCHITECT",
    "Scientific": "ANALYST",
    "Catcher General": "GUARDIAN",
    "Defensive Wall": "GUARDIAN",
    "Iron Infield": "GUARDIAN",
    "No-Fly Zone": "GUARDIAN",
    "Small Ball Cult": "FOX",
    "Speed Demons": "FOX",
    "Glass Cannons": "GLADIATOR",
    "Clean-Up Crew": "GLADIATOR",
    "Supreme Dynasty": "COMMANDER",
    "National Brand": "COMMANDER",
    "Elite Battery": "COMMANDER",
    "Pitching Kingdom": "COMMANDER",
}

BUFFS: Dict[str, Dict[str, int]] = {
    "COMMANDER": {"morale": 2, "momentum": 1},
    "ANALYST": {"focus": 2, "composure": 1},
    "SLASHER": {"aggression": 2, "focus": 1},
    "FOX": {"cunning": 2, "awareness": 1},
    "GLADIATOR": {"morale": 1, "intensity": 2},
    "ARCHITECT": {"focus": 2, "cohesion": 1},
    "GUARDIAN": {"trust": 2, "morale": 1},
}


IDENTITY_SPEECHES: List[Dict[str, List[str]]] = [
    {
        "title": "Who Are We? / Pride of the Kingdom",
        "lines": [
            "Captain: Who are the strongest?!",
            "Team: {SCHOOL}!!",
            "Captain: Who has worked the hardest?!",
            "Team: {SCHOOL}!!",
            "Captain: Who refuses to back down?!",
            "Team: {SCHOOL}!!",
            "Captain: Are we ready to win?!",
            "Team: YEEAAAHHHH!!",
            "Captain: With the pride of our kingdom at stake...",
            "Captain: ...we march toward the national crown!",
            "Team: GLORY TO {SCHOOL}!!",
            "Team (roaring): YEEEAAAAHHHH!!",
        ],
    },
    {
        "title": "Claim Your Name",
        "lines": [
            "Captain: What name do they fear?!",
            "Team: {SCHOOL}!!",
            "Captain: What name do WE protect?!",
            "Team: {SCHOOL}!!",
            "Captain: What name will echo across Japan today?!",
            "Team: {SCHOOL}!!",
            "Captain: Then SHOW THEM WHY!",
            "Team: YEAHHHHHH!!",
            "Captain: OUR FIELD! OUR BLOOD! OUR GAME!",
            "Team: {SCHOOL}! {SCHOOL}! {SCHOOL}!!!",
        ],
    },
    {
        "title": "Identity Hammer",
        "lines": [
            "Captain: Who stands united?!",
            "Team: WE DO!",
            "Captain: Who fights together?!",
            "Team: WE DO!",
            "Captain: Who carries the banner of {SCHOOL}?!",
            "Team: WE DO!!",
            "Captain: Then shout it so loud the other team shakes!",
            "Team: {SCHOOL}!! {SCHOOL}!! {SCHOOL}!!",
            "Captain: TODAY WE TAKE EVERYTHING!",
            "Team explodes: YEEEEAAAHHH!!",
        ],
    },
    {
        "title": "Philosophy Identity Call",
        "lines": [
            "Captain: What is our way?!",
            "Team: {PHILOSOPHY}!!",
            "Captain: What do we trust?!",
            "Team: OUR TRAINING!!",
            "Captain: What do we fear?!",
            "Team: NOTHING!!",
            "Captain: Who are we?!",
            "Team: {SCHOOL}!!!",
            "Captain: Then let them witness our baseball!",
            "Team: LET'S GO!!",
        ],
    },
    {
        "title": "Earn the Name",
        "lines": [
            "Captain: Every school has a name. But OURS...",
            "Team murmurs: Yeah...",
            "Captain: ...our name is a WEAPON.",
            "Team: YEAH!",
            "Captain: Who forged that weapon?!",
            "Team: WE DID!",
            "Captain: Who swings it today?!",
            "Team: WE DO!",
            "Captain: WHO ARE WE?!",
            "Team: {SCHOOL}!!!",
            "Captain: THEN GO TAKE THIS GAME!!",
            "Team: YEEEAAAHHH!!",
        ],
    },
    {
        "title": "Identity Trial",
        "lines": [
            "Captain: Do you believe in each other?!",
            "Team: YES!!",
            "Captain: Do you believe in our training?!",
            "Team: YES!!",
            "Captain: Do you believe in {SCHOOL}?!",
            "Team: YES!!",
            "Captain: THEN SHOUT IT!",
            "Team: {SCHOOL}!!",
            "Captain: LOUDER!",
            "Team: {SCHOOL}!!!",
            "Captain: LOUDER!!",
            "Team: {SCHOOL}!!!!!",
            "Captain: SHOW THEM WHO WE ARE!!",
            "Team: YAAAAHHH!!",
        ],
    },
    {
        "title": "Diamond Identity Call",
        "lines": [
            "Captain: Who owns this diamond?!",
            "Team: WE DO!!",
            "Captain: Who bleeds for this uniform?!",
            "Team: WE DO!!",
            "Captain: Who takes this win?!",
            "Team: WE DOOO!!",
            "Captain: THEN SAY OUR NAME!!",
            "Team: {SCHOOL}!! {SCHOOL}!! {SCHOOL}!!",
            "Captain: FOR THE CROWN!",
            "Team: FOR THE CROWN!!",
        ],
    },
    {
        "title": "Rise of the Identity",
        "lines": [
            "Captain: They doubt us.",
            "Team murmurs: Tch...",
            "Captain: They question us.",
            "Team: Hmph...",
            "Captain: SO WHO ARE WE?!",
            "Team: {SCHOOL}!!",
            "Captain: WHO ARE WE?!",
            "Team: {SCHOOL}!!!",
            "Captain: WHO ARE WE?!",
            "Team: {SCHOOL}!!!!!",
            "Captain: THEN RISE AND TAKE THIS GAME!",
            "Team: YAAAAHHH!!",
        ],
    },
    {
        "title": "Unbreakable Identity Call",
        "lines": [
            "Captain: Who trains the longest?!",
            "Team: {SCHOOL}!!",
            "Captain: Who runs the fastest?!",
            "Team: {SCHOOL}!!",
            "Captain: Who survives the toughest weeks?!",
            "Team: {SCHOOL}!!",
            "Captain: Who NEVER breaks?!",
            "Team: WE DON'T!!",
            "Captain: Then stand tall - SAY THE NAME!",
            "Team: {SCHOOL}!!!",
            "Captain: STAND PROUD!",
            "Team: {SCHOOL}!!!",
        ],
    },
    {
        "title": "Identity Anthem",
        "lines": [
            "Captain: What beats inside your chest?!",
            "Team: HEART!!",
            "Captain: What flows through this team?!",
            "Team: FIRE!!",
            "Captain: What name unites us?!",
            "Team: {SCHOOL}!!",
            "Captain: WHO ARE WE?!",
            "Team: {SCHOOL}!!",
            "Captain: WHO ARE WE?!",
            "Team: {SCHOOL}!!!",
            "Captain: What do we play for?!",
            "Team: PRIDE!!",
            "Captain: What do we fight for?!",
            "Team: HONOR!!",
            "Captain: WHAT DO WE TAKE TODAY?!",
            "Team: THE WIN!!!!",
            "Captain: THEN ROAR AS ONE!!",
            "Team: YEEEEAAAAHHH!!",
        ],
    },
    {
        "title": "Name of the Strongest",
        "lines": [
            "Captain: Who stands strongest?!",
            "Team: {SCHOOL}!!",
            "Captain: Who refuses to bow?!",
            "Team: {SCHOOL}!!",
            "Captain's Message: We've sharpened ourselves for this moment. Now show them the edge we've earned.",
            "Team: YAAAHHH!!",
        ],
    },
    {
        "title": "Pride of the Region",
        "lines": [
            "Captain: Who carries {REGION_TITLE} pride?!",
            "Team: WE DO!!",
            "Captain: Who protects this honor?!",
            "Team: {SCHOOL}!!",
            "Captain's Message: Hold your ground. Make them feel the weight of our pride.",
            "Team: YEAHHH!!",
        ],
    },
    {
        "title": "Who Are We",
        "lines": [
            "Captain: Who are we?!",
            "Team: {SCHOOL}!!",
            "Captain: Who do we fight for?!",
            "Team: {SCHOOL}!!",
            "Captain's Message: This field doesn't forgive hesitation. Move first and take control.",
            "Team: YAAHH!!",
        ],
    },
    {
        "title": "Unbreakable Line",
        "lines": [
            "Captain: What team never breaks?!",
            "Team: US!!",
            "Captain: What team never runs?!",
            "Team: {SCHOOL}!!",
            "Captain's Message: Doesn't matter who stands in front of us. We push straight through.",
            "Team: YEAHHH!!",
        ],
    },
    {
        "title": "Forge Ahead",
        "lines": [
            "Captain: Who forges the path?!",
            "Team: WE DO!!",
            "Captain: Who owns this moment?!",
            "Team: {SCHOOL}!!",
            "Captain's Message: Don't wait for an opening - create one. And once it appears, tear it open.",
            "Team: YAAHH!!",
        ],
    },
    {
        "title": "Identity Burn",
        "lines": [
            "Captain: Who brings the fire?!",
            "Team: WE DO!!",
            "Captain: Who burns brighter today?!",
            "Team: {SCHOOL}!!",
            "Captain's Message: Light it up. Make them feel the heat every play.",
            "Team: YEEEAAH!!",
        ],
    },
    {
        "title": "Claim the Crown",
        "lines": [
            "Captain: Who hunts the crown?!",
            "Team: WE DO!!",
            "Captain: Who takes the crown?!",
            "Team: {SCHOOL}!!",
            "Captain's Message: One inning at a time - stack them until they break. We're taking this.",
            "Team: YAAHHH!!",
        ],
    },
    {
        "title": "Stand as One",
        "lines": [
            "Captain: Who stands together?!",
            "Team: WE DO!!",
            "Captain: Who fights together?!",
            "Team: {SCHOOL}!!",
            "Captain's Message: If one moves, all move. Don't leave a single gap.",
            "Team: YEAHH!!",
        ],
    },
    {
        "title": "Rise Up",
        "lines": [
            "Captain: Who rises when it matters?!",
            "Team: WE DO!!",
            "Captain: Who rises TODAY?!",
            "Team: {SCHOOL}!!",
            "Captain's Message: This is our stage. Rise higher than ever.",
            "Team: YAAAAHH!!",
        ],
    },
    {
        "title": "The Loyal Name",
        "lines": [
            "Captain: What name do we protect?!",
            "Team: {SCHOOL}!!",
            "Captain: What name do we honor?!",
            "Team: {SCHOOL}!!",
            "Captain's Message: Carry our name with your play. Make them remember who stepped on this field.",
            "Team: YEAHH!!",
        ],
    },
    {
        "title": "Push Forward",
        "lines": [
            "Captain: Who charges first?!",
            "Team: WE DO!!",
            "Captain: Who keeps charging?!",
            "Team: {SCHOOL}!!",
            "Captain's Message: Step in and take space. Don't give a single inch back.",
            "Team: YAAHH!!",
        ],
    },
    {
        "title": "Voice of Victory",
        "lines": [
            "Captain: Whose voice fills this field?!",
            "Team: OURS!!",
            "Captain: Whose name rings loudest?!",
            "Team: {SCHOOL}!!",
            "Captain's Message: Silence them with results. Let our plays do the talking.",
            "Team: YEEEAAH!!",
        ],
    },
    {
        "title": "Unshakeable",
        "lines": [
            "Captain: Who never shakes under pressure?!",
            "Team: WE DON'T!!",
            "Captain: Who holds steady today?!",
            "Team: {SCHOOL}!!",
            "Captain's Message: Pressure's nothing. Stay sharp and don't blink.",
            "Team: YAAHH!!",
        ],
    },
    {
        "title": "Strike First",
        "lines": [
            "Captain: Who takes the first blow?!",
            "Team: WE DO!!",
            "Captain: Who strikes FIRST?!",
            "Team: {SCHOOL}!!",
            "Captain's Message: We start the fight. Hit them before they even breathe.",
            "Team: YAAAH!!",
        ],
    },
    {
        "title": "Identity of Champions",
        "lines": [
            "Captain: Who are the champions in spirit?!",
            "Team: WE ARE!!",
            "Captain: Who proves it today?!",
            "Team: {SCHOOL}!!",
            "Captain's Message: Show them why we're feared. Don't leave room for doubt.",
            "Team: YEEEAAHH!!",
        ],
    },
]


def _select_identity_script(title: Optional[str]) -> Dict[str, List[str]]:
    if title:
        for script in IDENTITY_SPEECHES:
            if script.get("title", "").lower() == title.lower():
                return script
    return random.choice(IDENTITY_SPEECHES)


def _format_identity_lines(
    script: Dict[str, List[str]],
    captain_name: str,
    school_name: str,
    philosophy: Optional[str],
    team_nickname: Optional[str],
    region_title: Optional[str],
) -> List[str]:
    context = {
        "SCHOOL": school_name,
        "PHILOSOPHY": philosophy or "OUR WAY",
        "TEAM_NICKNAME": team_nickname or school_name,
        "REGION_TITLE": region_title or "OUR REGION",
        "CAPTAIN": captain_name,
    }
    return [line.format(**context) for line in script.get("lines", [])]


def _choose_style(philosophy: Optional[str]) -> str:
    if not philosophy:
        return DEFAULT_STYLE
    for name, style in STYLE_BY_PHILOSOPHY.items():
        if philosophy.lower() == name.lower():
            return style
    return DEFAULT_STYLE


def _templates() -> Dict[str, Dict[str, Tuple[str, str, Optional[str]]]]:
    # Returns speech templates keyed by style; values are (call, response, optional closing)
    return {
        "COMMANDER": {
            "call": "Look at me. We're not here to survive. We're here to dictate the inning.",
            "response": "Yes sir!",
            "closing": "We impose our pace."
        },
        "ANALYST": {
            "call": "Numbers are on our side: their starter is sitting 70 stamina, bullpen is thin by the 6th.",
            "response": "We squeeze first?!",
            "closing": "We win the math, we win the game."
        },
        "SLASHER": {
            "call": "Forget their name. We cut the inning to ribbons, pitch by pitch.",
            "response": "With me!",
            "closing": "Attack the zone, own the basepaths."
        },
        "FOX": {
            "call": "Play the fox. Show bunt, steal their timing, punish their overreach.",
            "response": "Snatch it early!",
            "closing": "First blood is ours."
        },
        "GLADIATOR": {
            "call": "Breathe in. Feel the field. We take their noise and turn it into fuel.",
            "response": "We roar back!",
            "closing": "Every pitch, we hit back harder."
        },
        "ARCHITECT": {
            "call": "Pick your bricks: control the count, own the lanes, stack the outs.",
            "response": "Seal the frame!",
            "closing": "We build this win together."
        },
        "GUARDIAN": {
            "call": "I won't let them break our battery. We shield each other, ball after ball.",
            "response": "We got you, captain!",
            "closing": "Trust the glove, trust the call."
        },
    }


def _build_lines(style: str, captain_name: str, school_name: str) -> List[str]:
    templates = _templates()
    template = templates.get(style, templates[DEFAULT_STYLE])
    lines = [
        f"{captain_name} ({style}): {template['call']}",
        f"Team: {template['response']}",
    ]
    if template.get("closing"):
        lines.append(f"{captain_name}: {template['closing']}")
    lines.append(f"[{school_name}] Momentum primed by {style.lower()} call.")
    return lines


def run_team_huddle(
    captain,
    school,
    *,
    echo: bool = False,
    pause: bool = False,
    use_identity_pack: bool = False,
    identity_title: Optional[str] = None,
    team_nickname: Optional[str] = None,
    region_title: Optional[str] = None,
) -> Tuple[List[str], Dict[str, int]]:
    """Generate and optionally print a captain's pre-game huddle.

    Returns a tuple of (lines, buff). Buff is a small dict of momentum/focus style bumps.
    Set use_identity_pack to True to pull a call-and-response identity chant. Provide
    identity_title to target a specific script; otherwise one is picked at random.
    """
    captain_name = getattr(captain, "name", None) or getattr(captain, "last_name", None) or "Captain"
    school_name = getattr(school, "name", None) or "Our Side"
    philosophy = getattr(school, "philosophy", None)

    style = _choose_style(philosophy)
    buff = {**BUFFS.get(style, {}), "style": style}

    if use_identity_pack:
        script = _select_identity_script(identity_title)
        identity_lines = _format_identity_lines(
            script,
            captain_name,
            school_name,
            philosophy,
            team_nickname,
            region_title,
        )
        lines = [f"Identity Call - {script.get('title', 'Untitled')}", *identity_lines]
        lines.append(f"[{school_name}] Momentum primed by {style.lower()} call.")
    else:
        lines = _build_lines(style, captain_name, school_name)

    if echo:
        print("=== CAPTAIN HUDDLE ===")
        for line in lines:
            print(f" {line}")
            if pause:
                input("  (press Enter)")
    return lines, buff


__all__ = ["run_team_huddle"]
