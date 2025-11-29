import random
import sys
import os
import time
from sqlalchemy.orm import sessionmaker

# Add root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.setup_db import School, Player, engine, GameState
from world.school_philosophy import get_philosophy
from ui.ui_display import Colour, clear_screen

# Import generation helpers
from database.populate_japan import generate_stats, get_random_english_name, generate_pitch_arsenal

Session = sessionmaker(bind=engine)


# =====================================================================
#                      CAREER OUTCOME / EPILOGUE (EXTENDED)
# =====================================================================
def determine_career_outcome(player, school_prestige):
    """
    Determines the player's final career ending.
    This is the master decision tree. Original endings are preserved and
    many new position-specific endings are added (Option C).
    Returns: (Title, ShortDesc, Colour, StoryText)
    """

    # Safety: ensure numeric attributes are present
    def safe(attr, fallback=50):
        return getattr(player, attr) if hasattr(player, attr) and getattr(player, attr) is not None else fallback

    # Basic role-based stat aggregates
    if player.position == "Pitcher":
        vel = safe("velocity", 0)
        control = safe("control", 50)
        stamina = safe("stamina", 50)
        movement = safe("movement", 50)
        # velocity score normalized to 0-100 scale (120 baseline)
        vel_score = max(0, min(100, (vel - 120) * 2.5 if vel >= 120 else (vel - 80) * 1.0))
        stat_score = (vel_score * 0.55) + (control * 0.2) + (stamina * 0.15) + (movement * 0.1)
    elif player.position == "Catcher":
        # Catchers: defense + leadership + contact/power
        leadership = safe("catcher_leadership", 50)
        contact = safe("contact", 50)
        power = safe("power", 50)
        fielding = safe("fielding", 50)
        stat_score = (leadership * 0.25) + (fielding * 0.25) + (contact * 0.25) + (power * 0.25)
    elif player.position == "Infielder":
        contact = safe("contact", 50)
        power = safe("power", 50)
        fielding = safe("fielding", 50)
        speed = safe("speed", 50)
        stat_score = (fielding * 0.35) + (contact * 0.25) + (power * 0.2) + (speed * 0.2)
    elif player.position == "Outfielder":
        speed = safe("speed", 50)
        power = safe("power", 50)
        fielding = safe("fielding", 50)
        contact = safe("contact", 50)
        stat_score = (speed * 0.30) + (fielding * 0.25) + (power * 0.25) + (contact * 0.2)
    else:
        # Generic fallback
        stat_score = (safe("contact", 50) + safe("power", 50) + safe("fielding", 50) + safe("speed", 50)) / 4

    # Add school prestige influence (scouts + opportunity)
    total_score = stat_score + (school_prestige * 0.2)

    # Helpful flags
    injured = (safe("injury_days", 0) > 0 or safe("stamina", 50) < 30)
    high_prestige = (school_prestige >= 75)
    mid_prestige = (60 <= school_prestige < 75)
    low_prestige = (school_prestige < 45)

    # Keep original special endings intact (preserve exact wording where provided)
    # --- ORIGINAL: TRAGIC HERO / GLASS ACE ---
    if total_score > 80 and injured and high_prestige:
        story = (
            f"{player.last_name} was undeniable when healthy. He led {player.school.name} to glory,\n"
            "pitching through pain and carrying the hopes of the prefecture.\n"
            "But the cost was high. His shoulder was a ticking time bomb.\n"
            "He was drafted in the 2nd round, but his pro career was a series of surgeries and rehab.\n"
            "Fans still argue he had the highest ceiling of his generation, if only his body held up.\n"
            "He retired at 25, a legend of Koshien, but a 'what if' of the pros."
        )
        return ("TRAGIC HERO", "A star that burned too bright, too fast.", Colour.RED, story)

    # --- ORIGINAL: BROKEN PROSPECT ---
    if injured and low_prestige:
        story = (
            f"Injuries robbed {player.last_name} of his high school career.\n"
            "He spent more time in the trainer's room than on the field.\n"
            "Scouts saw the potential, but the medical reports were too risky.\n"
            "He went undrafted and quietly hung up his cleats.\n"
            "Sometimes he watches games and wonders how good he could have been."
        )
        return ("RETIRED (INJURY)", "Defeated by his own body.", Colour.FAIL, story)

    # --- ORIGINAL: UNFULFILLED SUMMER ---
    if low_prestige and total_score < 70:
        story = (
            f"For three years, {player.last_name} chased the dream of the Sacred Stadium.\n"
            "But the wall of the district qualifiers was too high.\n"
            "He graduated without ever stepping foot on Koshien soil.\n"
            "He played recreationally in college, but the regret of that final summer loss never fully faded.\n"
            "He is now a salaryman who avidly watches the tournament every August."
        )
        return ("RETIRED (NO KOSHIEN)", "The summer ended at the district stadium.", Colour.RESET, story)

    # --- NEW: Position-specific high-tier endings (Legends / Draft) ---
    # Legendary (global super talent)
    if total_score > 95:
        # Two-way special: if catcher/pitcher attributes high.
        if player.position == "Pitcher" and safe("velocity", 0) > 150:
            story = (
                 f"After graduating from {player.school.name}, {player.last_name} was selected in the first round of the NPB Draft.\n"
                "He dominated the Japanese league for 5 years, winning the Sawamura Award three times.\n"
                "At age 24, he signed a massive contract with an MLB team.\n"
                "He played 12 seasons in the majors, winning 3 World Series titles and an MVP award.\n"
                "Baseball historians now regard him as the greatest Japanese export in history...\n"
                f"{Colour.gold}With the sole exception of Shohei Ohtani, of course.{Colour.RESET}"
            )
            return ("GENERATIONAL ACE", "A once-in-a-century pitcher.", Colour.gold, story)

        if player.position == "Catcher" and safe("catcher_leadership", 50) > 80 and safe("power", 50) > 75:
            story = (
                f"{player.last_name} rewrote what a catcher could be. A leader, a power threat,\n"
                "and an ironback behind the plate. Drafted in the first round,\n"
                "he became a fan favorite and a team captain in pro ball."
            )
            return ("CATCHING ICON", "A new standard for the position.", Colour.gold, story)

        # Generic legend
        story = (
            f"{player.last_name} transcended expectations, earning a first-round pick.\n"
            "A glowing pro career followed — All-Star nods, championships, and a legacy.\n"
            "The name will be read in history books for years."
        )
        return ("DRAFTED 1ST ROUND (LEGEND)", "A generational talent.", Colour.gold, story)

    # --- DRAFTED PRO / PRO STAR (High-tier but less than legendary) ---
    if total_score > 80:
        if player.position == "Pitcher":
            if safe("velocity", 0) >= 145 and control >= 60:
                story = (
                    f"{player.last_name} was a furnace on the mound — drafted into the NPB and\n"
                    "became a strikeout ace. Long career, multiple awards, and a lasting legacy."
                )
                return ("DRAFTED (HIGH)", "Dominant pro pitcher.", Colour.CYAN, story)
            else:
                story = (
                    f"{player.last_name} was drafted and developed into a reliable starting pitcher.\n"
                    "Not flashy, but a true workhorse for his team."
                )
                return ("DRAFTED (STARTER)", "A dependable pro.", Colour.CYAN, story)

        elif player.position == "Catcher":
            story = (
                f"{player.last_name} was picked based on defense and leadership.\n"
                "He was pro-ready, guided pitching staffs, and became a coaching candidate after retirement."
            )
            return ("DRAFTED (CATCHER)", "Defensive leader in pro ranks.", Colour.CYAN, story)

        else:
            story = (
                f"{player.last_name} made the jump to professional baseball.\n"
                "A long career was ahead: not always a superstar, but a respected name."
            )
            return ("DRAFTED PRO", "The start of a long professional career.", Colour.CYAN, story)

    # --- UNIVERSITY / Corporate Pathways (mid-tier outcomes) ---
    if total_score > 65:
        # University star path
        if player.position == "Pitcher":
            story = (
                f"{player.last_name} accepted a scholarship to a top university and refined his craft.\n"
                "He developed into a mature pro later on, entering the draft as a polished weapon."
            )
            return ("UNIVERSITY ACE", "Refined in college, pro later.", Colour.GREEN, story)

        if player.position == "Catcher":
            story = (
                f"{player.last_name} used university ball to become a tactician behind the plate.\n"
                "His intelligence and leadership led to a pro opportunity after graduation."
            )
            return ("UNIVERSITY CATCHER", "Study and baseball combined.", Colour.GREEN, story)

        # Generic university/corporate split based on prestige
        if mid_prestige or high_prestige:
            story = (
                f"{player.last_name} won a scholarship to a top university.\n"
                "He matured physically and mentally there, setting up a future pro opportunity."
            )
            return ("UNIVERSITY STAR", "Taking the scholarly path to the pros.", Colour.GREEN, story)
        else:
            story = (
                f"{player.last_name} joined a Corporate League powerhouse — a respected career\n"
                "balancing company life and baseball. He became a fan favorite in industrial tournaments."
            )
            return ("CORPORATE LEAGUE", "The working man's baseball life.", Colour.BLUE, story)

    # --- SPECIAL POSITION-SPECIFIC ENDINGS (VARIETY, ANIME-FRIENDLY) ---
    # These add narrative flavour: 'Ironclad Reliever', 'Two-Way Sensation', 'Gold Glove Infielder', etc.

    # PITCHER-SPECIFIC BRANCHES
    if player.position == "Pitcher":
        vel = safe("velocity", 0)
        control = safe("control", 50)
        movement = safe("movement", 50)
        clutch = safe("clutch", 50)
        growth = player.growth_tag if hasattr(player, "growth_tag") else "Normal"

        # Two-way candidate (pitcher who also hit power highly)
        if vel > 140 and safe("power", 0) > 65 and safe("contact", 0) > 55:
            story = (
                f"{player.last_name} surprised everyone as a two-way talent.\n"
                "He split time between the mound and the lineup, producing highlight reels\n"
                "and becoming a rare two-way pro success story."
            )
            return ("TWO-WAY PHENOM", "A rare two-way pro.", Colour.gold, story)

        # Reliever/Closer path
        if vel > 145 and control < 55:
            story = (
                f"{player.last_name} found his calling as a late-inning power arm.\n"
                "He became a feared closer, a smaller frame but electric heat in the 9th inning."
            )
            return ("ELITE CLOSER", "The ninth-inning terror.", Colour.CYAN, story)

        # Crafty control pitcher (low velo, high control)
        if vel < 135 and control >= 75:
            story = (
                f"{player.last_name} owed his success to guile and command.\n"
                "Averse to destroying hitters with speed, he outsmarted them instead.\n"
                "A long pro career as a crafty starter followed."
            )
            return ("CRAFTY ACE", "Pitching intelligence wins games.", Colour.CYAN, story)

        # Late-bloomer story (Limitless or Sleeping Giant)
        if growth in ("Limitless", "Sleeping Giant") and total_score > 60:
            story = (
                f"{player.last_name}'s development arc was cinematic — from unknown freshman\n"
                "to a powerful pro prospect by his final year. Scouts fell in love at the right time."
            )
            return ("LATE BLOOMER", "Growth unlocked late; scouts noticed.", Colour.CYAN, story)

        # Injured but heroic: plays through and becomes folk legend
        if injured and total_score > 55:
            story = (
                f"{player.last_name} became a folk hero — he pitched through pain for the school,\n"
                "earning admiration if not a long pro career. Local legend status secured."
            )
            return ("FOLK HERO ACE", "Beloved by fans despite physical limits.", Colour.RESET, story)

        # Otherwise fallback to realistic pro / uni / corporate decisions handled above.
        # If none matched, give a default realistic ending:
        if total_score > 50:
            story = (
                f"{player.last_name} went on to play baseball at a competitive adult level.\n"
                "Not a superstar, but he found a life in the game — coaching, playing, and giving back."
            )
            return ("BASEBALL FOR LIFE", "Continues in the sport professionally or semipro.", Colour.BLUE, story)

    # CATCHER-SPECIFIC BRANCHES
    if player.position == "Catcher":
        leadership = safe("catcher_leadership", 50)
        framing = safe("command", 50)  # use command as proxy for pitch-calling quality
        power = safe("power", 50)
        contact = safe("contact", 50)

        # Manager/coach path
        if leadership >= 80 and safe("mental", 50) >= 70:
            story = (
                f"{player.last_name}'s mind for the game was unrivaled. After a modest pro run,\n"
                "he transitioned into coaching and then managing, shaping future generations."
            )
            return ("FUTURE MANAGER", "A catcher who becomes the dugout's brain.", Colour.GREEN, story)

        # Defensive general / Gold Glove catcher
        if leadership >= 65 and framing >= 70:
            story = (
                f"{player.last_name} commanded the diamond as a defensive rock.\n"
                "Pro teams prized his framing and game-calling; he enjoyed a long career behind the plate."
            )
            return ("GOLD GLOVE CATCHER", "A defensive cornerstone.", Colour.CYAN, story)

        # Power-hitting catcher story
        if power > 75 and contact >= 60:
            story = (
                f"{player.last_name} became a feared bat as well as a steadier back there.\n"
                "He hit big home runs and handled pitching staffs with authority."
            )
            return ("POWER CATCHER", "A rare offensive threat at the position.", Colour.CYAN, story)

        # Small-school superstar — becomes respected college coach/trainer
        if low_prestige and safe("overall", 0) > 60:
            story = (
                f"{player.last_name} never made the big lights as a pro, but his knowledge\n"
                "and passion made him an exceptional college coach and pitch-calling guru."
            )
            return ("COACH/MENTOR", "Teaching the next generation.", Colour.RESET, story)

        # Default catcher path
        if total_score > 55:
            story = (
                f"{player.last_name} enjoyed a fulfilling baseball life — some pro seasons,\n"
                "some coaching, lots of respect. Catchers like him keep the sport healthy."
            )
            return ("CATCHING CAREER", "A balanced catcher life.", Colour.BLUE, story)

    # INFIELDER-SPECIFIC BRANCHES
    if player.position == "Infielder":
        arm = safe("throwing", 50)
        fielding = safe("fielding", 50)
        contact = safe("contact", 50)
        power = safe("power", 50)

        # Gold Glove infielder
        if fielding >= 80 and arm >= 70:
            story = (
                f"{player.last_name} patrolled the infield like a vacuum.\n"
                "Professional teams loved his glove work. He won awards and remained a defensive icon."
            )
            return ("GOLD GLOVE INFIELDER", "A defensive wizard.", Colour.CYAN, story)

        # Power corner infielder
        if power >= 75 and contact >= 55:
            story = (
                f"{player.last_name} terrorized pitching from the hot corner.\n"
                "He became the cleanup hitter in many lineups and a feared slugger."
            )
            return ("CLEANUP CORNER", "Powerful corner infielder.", Colour.CYAN, story)

        # Tactical shortstop (leadership & clutch)
        if fielding >= 70 and safe("clutch", 50) >= 65:
            story = (
                f"{player.last_name} anchored the defense and led the team with clutch plays.\n"
                "A fan favorite who later entered coaching or pro play depending on offers."
            )
            return ("CLUTCH SHORTSTOP", "Leadership in the infield.", Colour.GREEN, story)

        # Academic path or corporate if not prodigy
        if total_score > 50:
            if mid_prestige or high_prestige:
                story = (
                    f"{player.last_name} used university ball to improve and later play professionally.\n"
                    "A steady career followed."
                )
                return ("UNIVERSITY INFIELDER", "Polished in college.", Colour.GREEN, story)
            else:
                story = (
                    f"{player.last_name} joined the corporate leagues and became a dependable star\n"
                    "in the industrial tournaments, respected by teammates and fans."
                )
                return ("CORPORATE INFIELDER", "A pillar of company baseball.", Colour.BLUE, story)

    # OUTFIELDER-SPECIFIC BRANCHES
    if player.position == "Outfielder":
        speed = safe("speed", 50)
        arm = safe("throwing", 50)
        power = safe("power", 50)
        contact = safe("contact", 50)

        # Stellar defensive OF
        if speed >= 80 and arm >= 70 and fielding >= 70:
            story = (
                f"{player.last_name} covered acres of grass with effortless athleticism.\n"
                "He made highlight reels and enjoyed an illustrious pro career as an elite defender."
            )
            return ("ELITE OUTFIELDER", "A defensive and speed juggernaut.", Colour.CYAN, story)

        # Power outfielder / slugger
        if power >= 80 and contact >= 60:
            story = (
                f"{player.last_name} launched balls into the stands with frightening regularity.\n"
                "He became a franchise slugger in pro ball with a legendary swing."
            )
            return ("FRANCHISE SLUGGER", "A feared offensive force.", Colour.CYAN, story)

        # Speed star (stolen base legend)
        if speed >= 85 and contact >= 60:
            story = (
                f"{player.last_name} became a blur on the bases and a spark atop lineups.\n"
                "His track-like speed led to college offers or pro attention as a table-setter."
            )
            return ("SPEED PHENOM", "A base-stealing dynamo.", Colour.CYAN, story)

        # Otherwise
        if total_score > 50:
            story = (
                f"{player.last_name} carved out a professional or semi-pro life as an outfielder.\n"
                "Not always the headline act, but a necessary presence on winning teams."
            )
            return ("OUTFIELD CAREER", "Solid professional or semi-pro life.", Colour.BLUE, story)

    # --- TWO-WAY / SPECIAL SITUATIONS (non-position-specific) ---
    # Two-way finalized as hitting+pitching capability but didn't match earlier two-way
    if safe("power", 0) >= 70 and safe("velocity", 0) >= 140 and total_score > 60:
        story = (
            f"{player.last_name} managed a rare two-way role in college and early pro years.\n"
            "Although specialization followed, fans remember the days he did both at a high level."
        )
        return ("TWO-WAY LEGACY", "A memorable two-way talent.", Colour.CYAN, story)

    # --- LOW-SCORE FALLBACKS (ensure player never gets unreachable states) ---
    if total_score > 45:
        # Give an aspirational ending: corporate/coach/college depending on prestige
        if high_prestige or mid_prestige:
            story = (
                f"{player.last_name} walked into university ball and worked extremely hard.\n"
                "It wasn't always a straight path, but he found a role and sometimes pro chances."
            )
            return ("UNIVERSITY PATH", "Opportunity through university ball.", Colour.GREEN, story)
        else:
            story = (
                f"{player.last_name} continued baseball at a lower tier — corporate leagues or coaching.\n"
                "He remained close to the game and found meaning there."
            )
            return ("WORK & BASEBALL", "A balanced life with baseball on the side.", Colour.BLUE, story)

    # --- PRESERVE ORIGINAL DEFAULT: RETIRED (NORMAL LIFE) ---
    story = (
        "With the final out of summer, {player.last_name} left his glove on the field.\n"
        "He went on to university, studied economics, and became a salaryman.\n"
        "Sometimes, when drinking with colleagues, he talks about that one hot summer\n"
        "when he chased a dream at Koshien."
    )
    return ("RETIRED", "A fond memory of youth.", Colour.RESET, story)


# =====================================================================
#                            EPILOGUE SEQUENCE
# =====================================================================
def play_ending_sequence(title, desc, color, story):
    clear_screen()
    print("\n\n")
    time.sleep(1)
    print(f"    {color}--- EPILOGUE ---{Colour.RESET}")
    time.sleep(2)
    print(f"\n    {title}")
    time.sleep(1.5)
    print(f"    {desc}")
    time.sleep(2)
    print("\n" + "="*60 + "\n")
    for line in story.split('\n'):
        print(f"    {line}")
        time.sleep(2.5)
    print("\n" + "="*60 + "\n")
    time.sleep(3)
    input("    [Press Enter to close the book on this legend...]")


# =====================================================================
#                          END OF SEASON ENGINE
# =====================================================================
def run_end_of_season_logic(user_player_id=None):
    """
    Executes the transition from one school year to the next.
    THIS FUNCTION PRESERVES YOUR ORIGINAL FLOW AND ADDS:
      - Offseason growth including height potential growth
      - Position-sensitive offseason stat gains
      - Recruitment of new freshmen
      - Calendar reset
    No existing features removed unless explicitly noted.
    """
    session = Session()

    # -------------------------------------------------------------
    # 0. GRADUATION CHECK FOR USER
    # -------------------------------------------------------------
    user_graduated = False
    if user_player_id:
        user = session.query(Player).get(user_player_id)
        if user and user.year == 3:
            user_graduated = True
            # Ensure school linkage for story text
            school = session.query(School).get(user.school_id)
            user.school = school
            title, desc, color, story = determine_career_outcome(user, school.prestige)
            play_ending_sequence(title, desc, color, story)

    if user_graduated:
        session.close()
        return True

    print(f"\n{Colour.HEADER}=== END OF SEASON PROCESSING ==={Colour.RESET}")

    # -------------------------------------------------------------
    # 1. REMOVE SENIORS (3rd years)
    # -------------------------------------------------------------
    print(" > 3rd Years are graduating...")
    deleted_count = session.query(Player).filter(Player.year == 3).delete()

    # -------------------------------------------------------------
    # 2. PROMOTIONS
    # -------------------------------------------------------------
    print(" > Promoting underclassmen...")
    players = session.query(Player).all()

    for p in players:
        p.year += 1
        p.fatigue = 0
        p.injury_days = 0
        # off-season base overall bump
        if hasattr(p, "overall") and p.overall is not None:
            p.overall = min(99, p.overall + 2)
    session.commit()
    print(f"   (Goodbye to {deleted_count} seniors.)")

    # -------------------------------------------------------------
    # 3. OFFSEASON GROWTH SYSTEM (HEIGHT + STATS)
    # -------------------------------------------------------------
    print(" > Offseason physical growth occurring...")

    for p in players:
        # NOTE: years have been incremented already (1->2, 2->3). We want to allow growth
        # for incoming 2nd and 3rd years (originally 1st and 2nd)
        # HEIGHT GROWTH: only those now in year 2 or 3 (i.e. previous 1st/2nd)
        try:
            # If database doesn't have height fields, skip safely
            if hasattr(p, "height_cm") and hasattr(p, "height_potential"):
                # Only allow growth for non-graduates (we already removed 3rd-year grads)
                if p.year in (2, 3):
                    remaining = max(0, getattr(p, "height_potential", getattr(p, "height_cm", 0)) - getattr(p, "height_cm", 0))
                    if remaining > 0:
                        # growth_tag affects amount and chance
                        growth_tag = getattr(p, "growth_tag", "Normal")
                        if growth_tag == "Limitless":
                            growth = random.randint(2, 7)
                        elif growth_tag == "Sleeping Giant":
                            growth = random.randint(0, 10)
                        elif growth_tag == "Grinder":
                            growth = random.randint(1, 3)
                        else:
                            growth = random.randint(1, 5)
                        growth = min(growth, remaining)
                        p.height_cm = getattr(p, "height_cm", 0) + growth
        except Exception:
            # Be robust: skip height growth if unexpected DB shape
            pass

        # BASE ATTRIBUTE GROWTH (position-independent list)
        base_attributes = [
            "velocity", "control", "command", "movement",
            "speed", "contact", "power", "fielding", "throwing",
            "stamina"
        ]

        for attr in base_attributes:
            if not hasattr(p, attr):
                continue
            current = getattr(p, attr) or 0

            # Growth by potential
            pot = getattr(p, "potential_grade", "C")
            if pot == "S":
                gain = random.randint(2, 6)
            elif pot == "A":
                gain = random.randint(2, 5)
            elif pot == "B":
                gain = random.randint(1, 4)
            elif pot == "C":
                gain = random.randint(1, 3)
            else:
                gain = random.randint(0, 2)

            # Growth tag multiplier/variance
            gtag = getattr(p, "growth_tag", "Normal")
            if gtag == "Limitless":
                gain = int(gain * 1.4)
            elif gtag == "Sleeping Giant":
                gain = int(gain * random.uniform(0.7, 2.0))
            elif gtag == "Grinder":
                gain = int(gain * 0.8)

            # Position-focused tweaks:
            if getattr(p, "position", "") == "Pitcher" and attr == "velocity":
                # pitchers get small added chance for velocity bump (separate later)
                pass
            if getattr(p, "position", "") == "Catcher" and attr == "command":
                # catchers can improve command (pitch-calling proxy) more
                gain = int(gain * 1.1)

            # Apply gain and cap at 99
            try:
                setattr(p, attr, min(99, current + gain))
            except Exception:
                # ignore write errors
                pass

        # SPECIAL PITCHER-ONLY VELOCITY GROWTH
        if getattr(p, "position", "") == "Pitcher":
            try:
                velo_cap = 170
                velo_gain = random.randint(0, 3)
                if getattr(p, "growth_tag", "") == "Limitless":
                    velo_gain += 1
                if getattr(p, "potential_grade", "") == "S":
                    velo_gain += 1
                p.velocity = min(velo_cap, (p.velocity or 0) + velo_gain)
            except Exception:
                pass

    session.commit()

    # -------------------------------------------------------------
    # 4. RECRUITMENT (FRESHMEN)
    # -------------------------------------------------------------
    print(" > Scouting new freshmen for 4000 schools (Simulated)...")

    schools = session.query(School).all()
    new_player_count = 0

    for school in schools:
        current_roster = len(school.players)
        target_roster = 18
        needed = max(5, target_roster - current_roster)

        phil_name, phil_data = get_philosophy(school.philosophy)
        focus = phil_data.get('focus', 'Balanced')

        for _ in range(needed):
            roll = random.random()
            if roll < 0.4:
                pos = "Pitcher"; spec = "P"
            elif roll < 0.5:
                pos = "Catcher"; spec = "C"
            elif roll < 0.75:
                pos = "Infielder"; spec = "Utility"
            else:
                pos = "Outfielder"; spec = "Utility"

            stats = generate_stats(pos, spec, focus)
            l_name, f_name = get_random_english_name('M')

            valid_cols = [c.key for c in Player.__table__.columns]
            clean_stats = {k: v for k, v in stats.items() if k in valid_cols}

            p = Player(
                name=f"{l_name} {f_name}",
                first_name=f_name, last_name=l_name,
                position=pos,
                year=1,
                school_id=school.id,
                jersey_number=random.randint(20, 99),
                role="BENCH",
                fatigue=0, injury_days=0,
                growth_tag=stats.get('growth_tag', 'Normal'),
                potential_grade=stats.get('potential_grade', 'C'),
                **clean_stats
            )

            if pos == "Pitcher":
                # generate pitch repertoire using a small helper pseudo-object
                class PseudoPlayer:
                    def __init__(self, s):
                        self.control = s.get('control', 50)
                        self.movement = s.get('movement', 50)
                try:
                    arsenal = generate_pitch_arsenal(PseudoPlayer(stats), focus, "Overhand")
                    # arsenal expected to be a list of PitchRepertoire-like objects or similar
                    p.pitch_repertoire = arsenal
                except Exception:
                    # If repertoire generation fails, ignore gracefully
                    pass

            session.add(p)
            new_player_count += 1

    session.commit()
    print(f"   (Welcome to {new_player_count} new freshmen.)")

    # -------------------------------------------------------------
    # 5. RESET CALENDAR
    # -------------------------------------------------------------
    state = session.query(GameState).first()
    state.current_year = (state.current_year or 2024) + 1
    state.current_month = 4
    state.current_week = 1
    session.commit()

    print(f"\n{Colour.gold}=== SEASON {state.current_year} START ==={Colour.RESET}")
    session.close()

    return False