"""steward: a rule-based steward for the fort's essentials, with the model as the overseer for everything else.

harness.py  the loop: observe, run the playbook, consult the model on a schedule or on events, advance time
playbook.py the deterministic rules (drink, food, farms, rooms, beds, dining, manager, moods, defence)
digest.py   the observation turned into a short, legible status report for the model
prompt.py   the system prompt (DF knowledge for this API) and the tool filter for the model
"""
