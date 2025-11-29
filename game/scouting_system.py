from sqlalchemy.orm import sessionmaker
from database.setup_db import engine, School, ScoutingData
from ui.ui_display import Colour

Session = sessionmaker(bind=engine)

def get_scouting_info(school_id):
    """
    Retrieves or creates scouting record for a target school.
    """
    session = Session()
    info = session.query(ScoutingData).get(school_id)
    
    if not info:
        # Create default unknown record
        info = ScoutingData(school_id=school_id, knowledge_level=0, rivalry_score=0)
        session.add(info)
        session.commit()
        
    # Detach from session to use outside
    session.refresh(info)
    session.close()
    return info

def perform_scout_action(user_school, target_school, cost_yen=50000):
    """
    Attempts to scout a team. Returns success message or error.
    """
    session = Session()
    
    # Re-fetch objects in this session
    user = session.query(School).get(user_school.id)
    target = session.query(School).get(target_school.id)
    scout_data = session.query(ScoutingData).get(target.id)
    
    if not scout_data:
        scout_data = ScoutingData(school_id=target.id, knowledge_level=0, rivalry_score=0)
        session.add(scout_data)
    
    # Check Budget
    if user.budget < cost_yen:
        session.close()
        return False, f"Not enough funds! Need ¥{cost_yen:,}, have ¥{user.budget:,}."
        
    # Check Max Level
    if scout_data.knowledge_level >= 3:
        session.close()
        return False, "We already have full intel on this team."
        
    # Execute
    user.budget -= cost_yen
    scout_data.knowledge_level += 1
    
    lvl_desc = ["Unknown", "Basic", "Detailed", "Full"][scout_data.knowledge_level]
    
    session.commit()
    session.close()
    
    return True, f"Scouting complete! Knowledge increased to {lvl_desc}. Cost: ¥{cost_yen:,}"