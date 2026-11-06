"""State digest and action memory: compact interpretation of fort state and feedback on recent failures.
"""
import json

DAY = 1200


def build_status(obs, recent_failures=None):
    """Build a compact advisory digest dict from the raw observation."""
    if not isinstance(obs, dict):
        return {}
    st = obs.get("stocks") if isinstance(obs.get("stocks"), dict) else {}
    adm = obs.get("administrators") if isinstance(obs.get("administrators"), dict) else {}
    dwarves = obs.get("dwarves") if isinstance(obs.get("dwarves"), list) else []
    cit = max(1, adm.get("citizens") or len(dwarves))
    
    drink = st.get("drink", 0) or 0
    food = st.get("food_edible", 0) or st.get("food", 0) or 0
    logs = st.get("logs_usable", 0) or 0
    barrels = st.get("barrels_empty", 0) or 0
    
    # Placed furniture
    placed = {}
    for f in (obs.get("furniture") or []):
        if isinstance(f, dict):
            k = f.get("kind")
            placed[k] = placed.get(k, 0) + 1
            
    beds = placed.get("bed", 0)
    tables = placed.get("table", 0)
    chairs = placed.get("chair", 0)
    dining_seats = min(tables, chairs)
    
    # Manager & office
    mgr_active = adm.get("manager_active_for_orders", False)
    mo = adm.get("manager_office")
    office_ready = isinstance(mo, dict) and bool(mo.get("chair"))
    
    # Moods
    mood_list = []
    for m in (obs.get("moods") or []):
        if isinstance(m, dict):
            mood_list.append({
                "unit_id": m.get("unit_id"),
                "mood": m.get("mood"),
                "skill": m.get("skill"),
                "claimed": bool(m.get("claimed_building_id")),
                "waiting": m.get("waiting", False),
                "items_needed": m.get("items_needed"),
            })

    status = {
        "citizens": cit,
        "supply": {
            "drink": drink,
            "drink_days_est": round(drink / max(0.1, cit * 0.06), 1),
            "food_edible": food,
            "food_days_est": round(food / max(0.1, cit * 0.024), 1),
            "logs_usable": logs,
            "barrels_empty": barrels,
        },
        "housing": {
            "beds_placed": beds,
            "beds_needed": cit,
            "dining_seats": dining_seats,
            "dining_seats_needed": math_ceil_half(cit),
        },
        "management": {
            "manager_active": mgr_active,
            "office_ready": office_ready,
        },
    }
    if mood_list:
        status["moods"] = mood_list
    if recent_failures:
        status["recent_failed_actions"] = recent_failures[-8:]
    return status


def math_ceil_half(n):
    return (n + 1) // 2
