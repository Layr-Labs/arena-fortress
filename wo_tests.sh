#!/bin/bash
# wo_tests.sh: one-variable-at-a-time work-order root cause. Each test starts from a fresh reset.
. "$(dirname "$0")/instance.sh" || exit 1
ensure_instance || exit 1
cd "$DF" || exit 1
R(){ timeout 30 ./dfhack-run "$@" 2>&1 | sed 's/\x1b\[[0-9;]*[A-Za-z]//g'; }
adv(){ R lua -f "$DFP/advance.lua" $1 >/dev/null; for i in $(seq 1 120); do sleep 1; R lua "print(df.global.pause_state)" | grep -q true && break; done; }
fresh(){ "$DFP/reset_fort.sh" 2>/dev/null | tail -1; }
report(){ echo "-- after $1 ticks:"; R lua -f "$DFP/wo_lib.lua" orders; R lua -f "$DFP/wo_lib.lua" counts; }

echo "===== A: ConstructBed order, NO manager, NO workshop"
fresh; R workorder '{"job":"ConstructBed","amount_total":2}'; adv 3600; report 3600

echo "===== B: + carpenter's workshop, NO manager"
fresh; R lua -f "$DFP/wo_lib.lua" workshop Carpenters 111 93 106; R build-now; R workorder '{"job":"ConstructBed","amount_total":2}'; adv 3600; report 3600

echo "===== C: + manager, NO workshop"
fresh; R lua -f "$DFP/wo_lib.lua" assign_manager; R workorder '{"job":"ConstructBed","amount_total":2}'; adv 3600; report 3600

echo "===== D: + manager + carpenter's workshop"
fresh; R lua -f "$DFP/wo_lib.lua" assign_manager; R lua -f "$DFP/wo_lib.lua" workshop Carpenters 111 93 106; R build-now; R workorder '{"job":"ConstructBed","amount_total":2}'; adv 3600; report 3600; adv 6000; report 9600

echo "===== E: drink: BrewDrink is not a manager job; try the reaction name"
R workorder '{"job":"CustomReaction","reaction":"BREW_DRINK_FROM_PLANT","amount_total":2}'
R lua "for i,r in ipairs(df.global.world.raws.reactions.reactions) do if r.code:find('BREW') then print(r.code) end end"
