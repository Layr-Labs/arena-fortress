-- score.lua: outcome snapshot for scoring (read-only). Prints one JSON object.
local json = require('json')
local o = {}
-- credit.lua bookkeeping (not a game change): the first score after an advance marks the orders created while time
-- ran as automation's; produced/credited value is read from its live totals
local credit = rawget(_G, '__credit')
if credit then
  credit.after_advance()
  local c = credit.totals()
  o.produced_value, o.credited_value = c.produced, c.credited
  o.produced_by_category, o.credited_by_category = c.produced_by_category, c.credited_by_category
  o.placed_value, o.raw_value = c.placed_value, c.raw_value
end
o.abs_tick = df.global.cur_year * 403200 + df.global.cur_year_tick
o.year = df.global.cur_year
local cit, ids = 0, {}
for _, u in ipairs(df.global.world.units.active) do
  if dfhack.units.isCitizen(u) then cit = cit + 1; ids[#ids + 1] = u.id end
end
o.citizens = cit
o.citizen_ids = ids
o.wealth_total = df.global.plotinfo.tasks.wealth.total
local w = df.global.plotinfo.tasks.wealth
o.wealth_created = w.weapons + w.armor + w.furniture + w.other + w.architecture + w.displayed
o.wealth_by_category = {weapons = w.weapons, armor = w.armor, furniture = w.furniture, other = w.other,
                        architecture = w.architecture, displayed = w.displayed}
-- felled logs land in `other`: with autochop on they dominate created wealth (243 logs = 729 of 754 by day 20).
-- wealth_crafted leaves `other` out entirely. (Subtracting a live log value from `other` is wrong: DF refreshes
-- the wealth tallies only periodically, so the difference goes negative after a burst of felling.)
o.wealth_crafted = w.weapons + w.armor + w.furniture + w.architecture + w.displayed
local logs = 0
for _, it in ipairs(df.global.world.items.other.WOOD) do logs = logs + dfhack.items.getValue(it) end
o.wealth_logs = logs  -- live value, for reference
-- score_version 6: food = edible items only. ANY_GOOD_FOOD also holds seeds (including seeds planted in farm plots) and
-- empty cloth bags, about 20 of 66 "food" on MY1 fort 2001 (runs/s0-compute-2026-10-23), so recorded food never reached
-- 0 while dwarves starved. Raw fish (FISH_RAW) needs a fishery before anyone can eat it.
local EDIBLE = {}
for _, t in ipairs({'FOOD', 'MEAT', 'FISH', 'CHEESE', 'EGG', 'PLANT', 'PLANT_GROWTH'}) do EDIBLE[df.item_type[t]] = true end
local function edible(it) return EDIBLE[it:getType()] and not it.flags.rotten end
local f, d = 0, 0
for _, it in ipairs(df.global.world.items.other.ANY_GOOD_FOOD) do if edible(it) then f = f + it.stack_size end end
for _, it in ipairs(df.global.world.items.other.DRINK) do d = d + it.stack_size end
o.food, o.drink = f, d
-- deaths: only fortress members (own group, not animals). Pets/livestock share the fort's civ_id
-- and world incidents include wildlife/visitors/invaders, so neither may be counted as citizen deaths.
local function member(u) return u and dfhack.units.isOwnGroup(u) and not dfhack.units.isAnimal(u) end
-- score_version 5: a citizen who left the fort's group before dying (a berserk dwarf that is killed, in game
-- 2026-10-13 on LT04) fails isOwnGroup at the end, so also count victims the recorder tracked as citizens
-- (recorder.lua's ledger, cit_log: the citizens alive at `start` and every later arrival, so F0 is unchanged)
local rec = rawget(_G, '__rec_state')
local ledger = rec and rec.cit_log or {}
local causes, other, dead_cit = {}, {}, 0
for _, inc in ipairs(df.global.world.incidents.all) do
  if inc.type == df.incident_type.Death then
    local c = df.death_type[inc.death_cause] or tostring(inc.death_cause)
    if member(df.unit.find(inc.victim)) or ledger[inc.victim] then
      causes[c] = (causes[c] or 0) + 1; dead_cit = dead_cit + 1
    else
      other[c] = (other[c] or 0) + 1
    end
  end
end
o.citizen_death_causes = causes
o.other_death_causes = other
o.citizen_deaths = dead_cit
-- invaders (scenario spawns and native raids/sieges): units flagged active_invader / invader_origin
local inv_dead, inv_alive = 0, 0
for _, u in ipairs(df.global.world.units.all) do
  if (u.flags1.active_invader or u.flags1.invader_origin) and not member(u) then
    if dfhack.units.isDead(u) then inv_dead = inv_dead + 1 elseif dfhack.units.isActive(u) then inv_alive = inv_alive + 1 end
  end
end
o.invaders_killed, o.invaders_alive = inv_dead, inv_alive
-- thefts (BENCHMARK-v1 LT06): DF 53.16 has no Theft incident type (incident_type is Death, Crime, Attack, ...;
-- crime_type Theft is fort justice). A thief that escapes the map with an item writes a history_event_item_stolenst
-- (site = this fort, theft_method Theft) and a CREATURE_STEALS_OBJECT announcement, verified in game 2026-10-10.
-- The history persists in the save, so count only events with tick >= the run's start (smoke.py does that).
local site, thefts = df.global.plotinfo.site_id, {}
for _, ev in ipairs(df.global.world.history.events) do
  if df.history_event_item_stolenst:is_instance(ev) and ev.site == site then
    thefts[#thefts + 1] = {id = ev.id, tick = ev.year * 403200 + ev.seconds, item = ev.item,
                           item_type = df.item_type[ev.item_type] or tostring(ev.item_type),
                           method = df.theft_method_type[ev.theft_method] or tostring(ev.theft_method)}
  end
end
o.thefts = thefts
-- thieves (kobold/goblin skulkers: flags1.marauder, not invader-flagged, so invaders_* miss them) and loot they carry
-- (inventory role Hauled) while still on the map: a theft in progress, not yet a history event
local th_dead, th_on_map, th_caged, held, active = 0, 0, 0, 0, {}
for _, a in ipairs(df.global.world.units.active) do active[a.id] = true end
for _, u in ipairs(df.global.world.units.all) do
  if u.flags1.marauder and not member(u) then
    if dfhack.units.isDead(u) then th_dead = th_dead + 1
    else
      if u.flags1.caged then th_caged = th_caged + 1 end
      if active[u.id] then
        th_on_map = th_on_map + 1
        for _, ii in ipairs(u.inventory) do if ii.mode == df.inv_item_role_type.Hauled then held = held + 1 end end
      end
    end
  end
end
o.thieves_dead, o.thieves_on_map, o.thieves_caged, o.thief_held_items = th_dead, th_on_map, th_caged, held
o.paused = df.global.pause_state
print(json.encode(o))
