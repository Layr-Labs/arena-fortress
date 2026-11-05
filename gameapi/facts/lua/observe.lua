-- observe.lua [SECTION] [BOXES_JSON]: the facts-only fortress observation (obs schema 8). Prints one JSON object.
-- Based on #85's observe2.lua (origin/obs-leaks, obs schema 5) minus interpretation, plus the facts game API v0 adds
-- (docs/GAME-API.md §5). SECTION: 'all' (default) or 'sites' (only what the site resolver needs: map, site
-- candidates, farm plots, zones, box facts). BOXES_JSON: [{"id": "R3", "x":, "y":, "z":, "w":, "h":}, ...]: boxes
-- (remembered rooms) to report tile facts for (box_facts).
-- Removed relative to #85: administrators.manager_needs_office (a measured threshold), moods[].workshop_needed (a
-- wiki table), threats.note (presentation), the map's site lists under advice-bearing names (they come back as raw
-- `site_candidates`; ids, order and status are assigned by sites.py).
local here = debug.getinfo(1, 'S').source:sub(2):match('(.*/)') or './'
local C = dofile(here .. 'common.lua')
local json = require('json')
local args = {...}
local SECTION = args[1] or 'all'
local BOXES = C.json_arg(args[2]) or {}
local o = {schema = 8}
local function try(name, fn)   -- a field whose function returns nil is left out
  local ok, v = pcall(fn)
  if ok then o[name] = v else o[name] = 'ERR: ' .. tostring(v) end
end
local ALL = SECTION == 'all'
local ent = df.historical_entity.find(df.global.plotinfo.group_id)
local citizens = C.citizens
local seen, visible_unit, report_seen, built = C.seen, C.visible_unit, C.report_seen, C.built
local NOW = C.now()

try('date', function()
  local t = df.global.cur_year_tick
  return {year = df.global.cur_year, day_of_year = t // 1200 + 1,
          season = ({'spring', 'summer', 'autumn', 'winter'})[t // 100800 + 1], abs_tick = NOW}
end)

if ALL then
try('dwarves', function()
  local r = {}
  for _, u in ipairs(citizens()) do
    local nob = dfhack.units.getNoblePositions(u)
    local titles = {}
    if nob then for _, p in ipairs(nob) do titles[#titles + 1] = p.position.code end end
    r[#r + 1] = {id = u.id, name = C.name(u),
      profession = dfhack.units.getProfessionName(u),
      job = u.job.current_job and df.job_type[u.job.current_job.job_type] or 'idle',
      positions = titles,
      organizer_skill = dfhack.units.getNominalSkill(u, df.job_skill.ORGANIZATION, true),
      stress = dfhack.units.getStressCategory(u),   -- 0 most stressed .. 6; recorder.lua counts <= 1 as stressed
      -- schema 6: what create_squad's eligibility and shelter checks need (audit §c-7)
      adult = dfhack.units.isAdult(u), squad_id = u.military.squad_id ~= -1 and u.military.squad_id or nil,
      x = u.pos.x, y = u.pos.y, z = u.pos.z}
  end
  return r
end)

try('stressed_citizens', function()   -- same definition as recorder.lua's daily `stressed` sample
  local n = 0
  for _, u in ipairs(citizens()) do if dfhack.units.getStressCategory(u) <= 1 then n = n + 1 end end
  return n
end)

-- The manager's office: an Office zone assigned to the manager, and whether a built chair is in it. Schema 6 drops
-- #85's manager_needs_office (a threshold measured in game, not something DF reports) and gives the facts it was
-- made from instead: the citizen count and the position's required_office value (DF's noble raws).
local function office_of(u)
  for _, z in ipairs(df.global.world.buildings.other.ACTIVITY_ZONE) do
    if z.type == df.civzone_type.Office and z.assigned_unit_id == u.id then
      local chair = false
      for _, b in ipairs(z.contained_buildings) do if df.building_chairst:is_instance(b) and built(b) then chair = true end end
      return z, chair
    end
  end
end

try('administrators', function()
  local r = {citizens = #citizens()}
  for _, asg in ipairs(ent.positions.assignments) do
    for _, ps in ipairs(ent.positions.own) do
      if ps.id == asg.position_id and (ps.code == 'MANAGER' or ps.code == 'BOOKKEEPER' or ps.code == 'EXPEDITION_LEADER' or ps.code == 'CHIEF_MEDICAL_DWARF' or ps.code == 'BROKER') then
        local hf = asg.histfig ~= -1 and df.historical_figure.find(asg.histfig)
        local u = hf and df.unit.find(hf.unit_id)
        r[ps.code] = hf and (u and C.name(u) or 'hf ' .. hf.id) or 'VACANT'
        if u then r[ps.code .. '_id'] = u.id end
      end
    end
  end
  r.manager_active_for_orders = #ent.assignments_by_type.MANAGE_PRODUCTION > 0
  for _, asg in ipairs(ent.positions.assignments) do
    for _, ps in ipairs(ent.positions.own) do
      local hf = ps.id == asg.position_id and ps.code == 'MANAGER' and asg.histfig ~= -1 and df.historical_figure.find(asg.histfig)
      local u = hf and df.unit.find(hf.unit_id)
      if ps.id == asg.position_id and ps.code == 'MANAGER' then r.manager_required_office = ps.required_office end
      if u then
        local z, chair = office_of(u)
        r.manager_office = z and {zone_id = z.id, chair = chair} or 'none'
      end
    end
  end
  return r
end)
end

-- world.items.other.<KIND>, revealed items only (cached per kind for this observation)
local items = setmetatable({}, {__index = function(t, k)
  local r = {}
  for _, it in ipairs(df.global.world.items.other[k]) do if seen(it) then r[#r + 1] = it end end
  t[k] = r
  return r
end})

if ALL then
-- the score's edible food (recorder.lua, score_version 6)
local EDIBLE = {}
for _, t in ipairs({'FOOD', 'MEAT', 'FISH', 'CHEESE', 'EGG', 'PLANT', 'PLANT_GROWTH'}) do EDIBLE[df.item_type[t]] = true end

try('stocks', function()
  local other = items
  local function sum(v) local n = 0 for _, it in ipairs(v) do n = n + it.stack_size end return n end
  local usable_logs, wagon_logs = 0, 0
  for _, it in ipairs(other.WOOD) do
    if it.flags.in_building or it.flags.forbid or it.flags.in_job then wagon_logs = wagon_logs + 1 else usable_logs = usable_logs + 1 end
  end
  local function empties(v) local n = 0 for _, b in ipairs(v) do if #dfhack.items.getContainedItems(b) == 0 and not b.flags.in_job then n = n + 1 end end return n end
  local brewable, plants_usable, plants_rotten, by_kind = 0, 0, 0, {}
  for _, it in ipairs(other.PLANT) do
    local m = dfhack.matinfo.decode(it)
    if it.flags.rotten then
      plants_rotten = plants_rotten + it.stack_size
    elseif m and m.plant and not it.flags.forbid then
      plants_usable = plants_usable + it.stack_size
      local brew = false
      for _, p in ipairs(m.material.reaction_product.id) do if p.value == 'DRINK_MAT' then brew = true break end end
      if brew then brewable = brewable + it.stack_size end
      local k = by_kind[m.plant.name] or {n = 0, brewable = brew, cookable = m.material.flags.EDIBLE_COOKED}
      k.n = k.n + it.stack_size
      by_kind[m.plant.name] = k
    end
  end
  local seeds_by_kind = {}
  for _, it in ipairs(other.SEEDS) do
    local m = dfhack.matinfo.decode(it)
    if m and m.plant and not it.flags.forbid then
      local p = m.plant
      local k = seeds_by_kind[p.name]
      if not k then
        local seasons = {}
        for _, sn in ipairs({'SPRING', 'SUMMER', 'AUTUMN', 'WINTER'}) do if p.flags[sn] then seasons[#seasons + 1] = sn:lower() end end
        k = {n = 0, underground = p.underground_depth_min > 0, seasons = seasons}
        seeds_by_kind[p.name] = k
      end
      k.n = k.n + it.stack_size
    end
  end
  local furniture_free = {}
  for kind, t in pairs({bed = 'BED', table = 'TABLE', chair = 'CHAIR', door = 'DOOR', container = 'BOX'}) do
    local n = 0
    for _, it in ipairs(other[t]) do
      if not (it.flags.in_building or it.flags.forbid or it.flags.in_job or it.flags.construction) then n = n + 1 end
    end
    furniture_free[kind] = n
  end
  local boulders_usable = 0
  for _, it in ipairs(other.BOULDER) do if not (it.flags.in_building or it.flags.forbid or it.flags.in_job) then boulders_usable = boulders_usable + 1 end end
  -- schema 6: totals for what the frozen recipes make (audit §c-10); charcoal = BAR items of the COAL material
  local charcoal = 0
  for _, it in ipairs(other.BAR) do if it.mat_type == df.builtin_mats.COAL then charcoal = charcoal + it.stack_size end end
  -- schema 8: food_edible is the score's food (recorder.lua, score_version 6): edible item types, unrotten; no seeds,
  -- empty bags or raw fish. food_any_good keeps DF's ANY_GOOD_FOOD list total (what food_edible was in schemas 5-7).
  local food_edible = 0
  for _, it in ipairs(other.ANY_GOOD_FOOD) do
    if EDIBLE[it:getType()] and not it.flags.rotten then food_edible = food_edible + it.stack_size end
  end
  return {drink = sum(other.DRINK), food_edible = food_edible, food_any_good = sum(other.ANY_GOOD_FOOD),
          prepared_meals = sum(other.FOOD),
          plants_total = plants_usable, plants_brewable = brewable, plants_rotten = plants_rotten, seeds = sum(other.SEEDS),
          plants_by_kind = by_kind, seeds_by_kind = seeds_by_kind,
          logs_usable = usable_logs, logs_unusable = wagon_logs, boulders = #other.BOULDER, boulders_usable = boulders_usable,
          barrels_total = #other.BARREL, barrels_empty = empties(other.BARREL),
          beds = #other.BED, tables = #other.TABLE, chairs = #other.CHAIR, bins = #other.BIN, charcoal = charcoal,
          furniture_free = furniture_free}
end)

try('wealth', function() local w = df.global.plotinfo.tasks.wealth
  local logs = 0
  for _, it in ipairs(items.WOOD) do logs = logs + dfhack.items.getValue(it) end
  local created = w.weapons + w.armor + w.furniture + w.other + w.architecture + w.displayed
  return {created = created, total = w.total, furniture = w.furniture, architecture = w.architecture, other = w.other,
          crafted = w.weapons + w.armor + w.furniture + w.architecture + w.displayed, raw_logs_value = logs} end)

try('workshops', function()
  local r = {}
  for _, b in ipairs(df.global.world.buildings.all) do
    local furnace = df.building_furnacest:is_instance(b)
    if furnace or df.building_workshopst:is_instance(b) then
      local jobs, details = {}, {}
      for _, j in ipairs(b.jobs) do
        jobs[#jobs + 1] = df.job_type[j.job_type] .. (j.flags.by_manager and '(order)' or '')   -- observe2's shape
        -- schema 6: per-job facts (audit §c-14)
        local w = dfhack.job.getWorker(j)
        details[#details + 1] = {job = df.job_type[j.job_type], reaction = j.reaction_name ~= '' and j.reaction_name or nil,
                                 order_id = j.order_id ~= -1 and j.order_id or nil, by_manager = j.flags.by_manager or nil,
                                 worker_id = w and w.id or nil, suspended = j.flags.suspend or nil, do_now = j.flags.do_now or nil}
      end
      local _, st = C.building_kind(b)
      r[#r + 1] = {id = b.id, type = st, x = b.centerx, y = b.centery, z = b.z, built = built(b), jobs = jobs, job_details = details}
    end
  end
  return r
end)
end

-- zones: every activity zone (schema 6: no silent cap of 12; at most ZONE_CAP listed, zones_total always the true count)
local ZONE_CAP = 200
local function zone_list()
  local r, total = {}, 0
  for _, z in ipairs(df.global.world.buildings.other.ACTIVITY_ZONE) do
    total = total + 1
    if #r < ZONE_CAP then
      local furn, planned, ids = {}, {}, {}
      for _, b in ipairs(z.contained_buildings) do
        local t = df.building_type[b:getType()]:lower()
        if built(b) then furn[t] = (furn[t] or 0) + 1 else planned[t] = (planned[t] or 0) + 1 end
        ids[#ids + 1] = b.id
      end
      r[#r + 1] = {id = z.id, type = df.civzone_type[z.type], x = z.x1, y = z.y1, z = z.z,
                   w = z.x2 - z.x1 + 1, h = z.y2 - z.y1 + 1,
                   owner = z.assigned_unit_id ~= -1 and z.assigned_unit_id or nil,
                   furniture = furn, furniture_planned = next(planned) and planned or nil,
                   building_ids = #ids > 0 and ids or nil}
    end
  end
  return r, total
end
do
  local ok, zl, total = pcall(zone_list)
  if ok then o.zones = zl; o.zones_total = total else o.zones = 'ERR: ' .. tostring(zl) end
end

-- schema 6 (audit §c-5): every placed furniture building, built or not, with the zones it is in (DF's building
-- relations); furniture_unzoned counts those in none, by kind
if ALL then
local FURN = {}
for _, n in ipairs({'Bed', 'Table', 'Chair', 'Box', 'Cabinet', 'Armorstand', 'Weaponrack', 'Statue', 'Coffin', 'Slab',
                    'TractionBench', 'Bookcase', 'DisplayFurniture', 'Chain', 'Cage', 'Door', 'Hatch'}) do
  if df.building_type[n] then FURN[df.building_type[n]] = n:lower() end
end
try('furniture', function()
  local r, unzoned, total = {}, {}, 0
  for _, b in ipairs(df.global.world.buildings.all) do
    local k = FURN[b:getType()]
    if k and C.revealed(b.centerx, b.centery, b.z) then
      total = total + 1
      local zs = C.zone_ids(b)
      if #zs == 0 then unzoned[k] = (unzoned[k] or 0) + 1 end
      if #r < 300 then r[#r + 1] = {id = b.id, kind = k, x = b.centerx, y = b.centery, z = b.z, built = built(b), zone_ids = zs} end
    end
  end
  o.furniture_total = total
  o.furniture_unzoned = unzoned   -- contract §3.1: counts by kind of placed furniture (built or not) in no zone
  return r
end)
end

try('farm_plots', function()
  local r = {}
  local SEAS = {'spring', 'summer', 'autumn', 'winter'}
  for _, b in ipairs(df.global.world.buildings.other.FARM_PLOT) do
    local planted = 0
    for _, ci in ipairs(b.contained_items) do if df.item_plantst:is_instance(ci.item) or df.item_seedsst:is_instance(ci.item) then planted = planted + 1 end end
    local crops = {}
    for s = 0, 3 do local p = b.plant_id[s] crops[SEAS[s + 1]] = p ~= -1 and df.global.world.raws.plants.all[p].id or 'none' end
    r[#r + 1] = {id = b.id, x = b.x1, y = b.y1, z = b.z, w = b.x2 - b.x1 + 1, h = b.y2 - b.y1 + 1,
                 built = built(b), seeds_or_crops_in_plot = planted,
                 crop_this_season = crops[SEAS[df.global.cur_season + 1]], crops = crops,
                 subterranean = (function() local fl = dfhack.maps.getTileFlags(b.x1, b.y1, b.z) return fl and fl.subterranean or false end)()}
  end
  return r
end)

if ALL then
-- orders. Schema 6 fixes `when` (audit §c-1): every condition with its item type (null = any item type), subtype,
-- material, flags, reaction class/product and tool use, not only item_type (which made flag-only conditions read "NONE")
local function cond_facts(c)
  local item = {item_type = C.item_type_name(c.item_type), item_subtype = C.subtype_id(c.item_type, c.item_subtype),
                material = C.mat_string(c.mat_type, c.mat_index), flags = C.item_flags(c),
                reaction_class = c.reaction_class ~= '' and c.reaction_class or nil,
                reaction_product = c.has_material_reaction_product ~= '' and c.has_material_reaction_product or nil,
                tool_use = c.has_tool_use >= 0 and df.tool_uses[c.has_tool_use] or nil,
                test = df.logic_condition_type[c.compare_type], value = c.compare_val}
  if #item.flags == 0 then item.flags = nil end
  return item
end
try('orders', function()
  local r = {}
  local spawned = {}
  local l = df.global.world.jobs.list.next
  while l do if l.item.order_id ~= -1 then spawned[l.item.order_id] = (spawned[l.item.order_id] or 0) + 1 end l = l.next end
  for _, ord in ipairs(df.global.world.manager_orders.all) do
    local e = {id = ord.id, job = df.job_type[ord.job_type], reaction = ord.reaction_name ~= '' and ord.reaction_name or nil,
               meal_kind = ord.job_type == df.job_type.PrepareMeal and ord.mat_type or nil,
               material_category = (function() local b = C.bits(ord.material_category) return #b > 0 and b or nil end)(),
               left = ord.amount_left, total = ord.amount_total, validated = ord.status.validated,
               active = ord.status.active, jobs_in_progress = spawned[ord.id] or 0}
    if ord.frequency ~= df.workquota_frequency_type.OneTime then
      e["repeat"] = df.workquota_frequency_type[ord.frequency]:lower()
    end
    local w = {}
    for _, c in ipairs(ord.item_conditions) do w[#w + 1] = cond_facts(c) end
    if #w > 0 then e.when = w end
    r[#r + 1] = e
  end
  return r
end)

try('recent_cancellations', function()   -- DF's own cancellation reasons, last 3 days (#85)
  local rep, r = df.global.world.status.reports, {}
  for i = #rep - 1, math.max(0, #rep - 200), -1 do
    if NOW - C.report_tick(rep[i]) > 3 * 1200 then break end
    local t = dfhack.df2utf(rep[i].text)
    if (t:find(' cancels ') or t:find('unable to')) and report_seen(rep[i]) then r[#r + 1] = (t:gsub('%[[^%]]*%]', '')) end
    if #r >= 8 then break end
  end
  return r
end)

try('recent_events', function()   -- last 7 days (#85); the full stream is events()
  local rep, r = df.global.world.status.reports, {}
  for i = #rep - 1, math.max(0, #rep - 60), -1 do
    if NOW - C.report_tick(rep[i]) > 7 * 1200 then break end
    local t = dfhack.df2utf(rep[i].text):gsub('%[[^%]]*%]', '')
    if not t:find(' cancels ') and #t < 300 and report_seen(rep[i]) then r[#r + 1] = t end
    if #r >= 6 then break end
  end
  return r
end)
end

local wagon = C.wagon()
local function wagon_pos()
  if wagon then return wagon.centerx, wagon.centery, wagon.z end
  return 97, 96, 106
end

local function alert_burrows()
  local l = df.global.plotinfo.alerts.list
  local r = {}
  if #l > 1 then for _, id in ipairs(l[1].burrows) do r[id] = true end end
  return r
end

if ALL then
try('threats', function()
  local wx, wy, wz = wagon_pos()
  local hostile, list, by_race, nearest = 0, {}, {}, nil
  local shelter = {}
  for id in pairs(alert_burrows()) do local b = df.burrow.find(id) if b then shelter[#shelter + 1] = b end end
  for _, u in ipairs(df.global.world.units.active) do
    if dfhack.units.isDanger(u) and visible_unit(u) and not dfhack.units.isDead(u) then
      hostile = hostile + 1
      local race = df.creature_raw.find(u.race).creature_id
      local inv = dfhack.units.isInvader(u) or u.flags1.active_invader or u.flags1.invader_origin
      -- dist_to_wagon: tiles (max of |dx|,|dy|, plus 3 per z-level) from the wagon
      local d = math.max(math.abs(u.pos.x - wx), math.abs(u.pos.y - wy)) + 3 * math.abs(u.pos.z - wz)
      nearest = math.min(nearest or d, d)
      local e = by_race[race] or {n = 0, invader = false}
      e.n = e.n + 1; e.invader = e.invader or inv; by_race[race] = e
      local inside = false
      for _, b in ipairs(shelter) do if dfhack.burrows.isAssignedTile(b, u.pos) then inside = true end end
      local wpn
      for _, it in ipairs(u.inventory) do if it.mode == df.inv_item_role_type.Weapon then wpn = dfhack.items.getDescription(it.item, 0, true) end end
      if #list < 20 then list[#list + 1] = {id = u.id, race = race, invader = inv, x = u.pos.x, y = u.pos.y, z = u.pos.z,
                                             dist_to_wagon = d, weapon = wpn, in_shelter = inside or nil} end
    end
  end
  local dead, inv_dead = 0, 0
  for _, u in ipairs(df.global.world.units.all) do
    if dfhack.units.isDead(u) then
      if dfhack.units.isOwnGroup(u) and not dfhack.units.isAnimal(u) then dead = dead + 1
      elseif (u.flags1.invader_origin or u.flags1.active_invader) then
        local x, y, z = dfhack.units.getPosition(u)
        local fl = x and dfhack.maps.getTileFlags(x, y, z)
        if fl and not fl.hidden then inv_dead = inv_dead + 1 end
      end
    end
  end
  return {visible_hostiles = hostile, dead_citizens_total = dead, invaders_dead = inv_dead, by_race = by_race,
          nearest_hostile_dist_to_wagon = nearest, hostiles = list}
end)

-- strange moods (schema 7): only what a vanilla DF 53 player sees (gameapi/manual/MOOD-VISIBILITY.md; DFHack tags
-- `showmood` as armok, i.e. hidden information). Always: unit, mood type, skill, DF's mood job type (StrangeMood*),
-- the claimed workshop, whether the dwarf is `waiting` (idle in its claimed workshop, not fetching/bringing/working:
-- checked in game, job.flags), and `collected_items` (the items tasked in the workshop). `items_needed` only while
-- waiting, as the workshop's clues word it: {demand, quantity (null for the primary material, element 0), collected};
-- Fey moods also name the material of bars/glass and the cloth kind. No raw flags, exact materials or availability.
local function demand_of(ji)
  local it = ji.item_type >= 0 and df.item_type[ji.item_type] or nil
  local fl = {}
  for _, n in ipairs(C.item_flags(ji)) do fl[n] = true end
  local glass = false
  if ji.mat_type >= 0 then
    local mi = dfhack.matinfo.decode(ji.mat_type, ji.mat_index)
    glass = mi and mi.material and mi.material.flags.IS_GLASS or false
  end
  local D = {BOULDER = 'rock', BLOCKS = 'blocks', WOOD = 'logs', BAR = 'bars', SMALLGEM = 'cut gems',
             ROUGH = glass and 'raw glass' or 'rough gems', CLOTH = 'cloth', THREAD = 'thread', SKIN_TANNED = 'leather',
             CORPSE = 'body parts', CORPSEPIECE = 'body parts', GLOB = 'globs'}
  local d = it and (D[it] or it:lower())
  if not d then
    if fl.bone then d = 'bones' elseif fl.shell then d = 'shells' elseif fl.horn then d = 'horns'
    elseif fl.ivory_tooth or fl.tooth then d = 'teeth' elseif fl.pearl then d = 'pearls' elseif fl.silk then d = 'silk'
    elseif fl.leather then d = 'leather' elseif fl.cloth then d = 'cloth' elseif fl.yarn then d = 'yarn' else d = 'items' end
  end
  local cloth = fl.silk and 'silk' or fl.plant and 'plant' or fl.yarn and 'yarn' or nil
  return d, cloth
end
try('moods', function()
  local r = {}
  for _, u in ipairs(citizens()) do
    local m = df.mood_type[u.mood]
    if u.mood ~= -1 and m and m ~= 'Baby' and m ~= 'None' then
      local e = {unit_id = u.id, mood = m, skill = df.job_skill[u.job.mood_skill], waiting = false}
      local j = u.job.current_job
      local jname = j and df.job_type[j.job_type]
      if jname and jname:find('^StrangeMood') then
        e.job = jname
        e.collected_items = #j.items
        local b = dfhack.job.getHolder(j)
        if b then
          e.claimed_building_id = b.id
          local t, st = C.building_kind(b)
          e.claimed_workshop = st or t
          local p = u.pos
          e.waiting = p.z == b.z and p.x >= b.x1 and p.x <= b.x2 and p.y >= b.y1 and p.y <= b.y2
                      and not (j.flags.fetching or j.flags.bringing or j.flags.working)
        end
        if e.waiting then
          local need = {}
          for i, ji in ipairs(j.job_items.elements or j.job_items) do
            local have = 0
            for _, ref in ipairs(j.items) do if ref.job_item_idx == i then have = have + 1 end end
            local d, cloth = demand_of(ji)
            local x = {demand = d, quantity = i > 0 and ji.quantity or nil, collected = have}
            if m == 'Fey' then
              if d == 'bars' or d == 'raw glass' then x.material = C.mat_string(ji.mat_type, ji.mat_index) end
              if d == 'cloth' or d == 'thread' then x.cloth = cloth end
            end
            need[#need + 1] = x
          end
          if #need > 0 then e.items_needed = need end
        end
      elseif jname then
        e.job = jname
      end
      r[#r + 1] = e
    end
  end
  if #r > 0 then return r end
end)

-- water on the fortress levels a player can see (#85): revealed, indoor tiles within 30 tiles of the wagon, from 8
-- levels below it up
try('water_on_fort_levels', function()
  local wx, wy, wz = wagon_pos()
  local tiles, deep, depth = 0, 0, 0
  for z = wz - 8, wz do
    for x = wx - 30, wx + 30 do
      for y = wy - 30, wy + 30 do
        local d = dfhack.maps.getTileFlags(x, y, z)
        if d and d.flow_size > 0 and not d.hidden and not d.outside and not d.liquid_type then
          tiles = tiles + 1; depth = depth + d.flow_size
          if d.flow_size >= 4 then deep = deep + 1 end
        end
      end
    end
  end
  if tiles > 0 then return {tiles = tiles, deep_tiles = deep, total_depth = depth} end
end)

try('military', function()
  local r = {}
  for _, sq in ipairs(df.global.world.squads.all) do
    if sq.entity_id == df.global.plotinfo.group_id then
      local members, armed = {}, 0
      for i, p in ipairs(sq.positions) do
        if p.occupant ~= -1 then
          local hf = df.historical_figure.find(p.occupant)
          local u = hf and df.unit.find(hf.unit_id)
          if u and not dfhack.units.isDead(u) then
            local wpn
            for _, it in ipairs(u.inventory) do if it.mode == df.inv_item_role_type.Weapon then wpn = dfhack.items.getDescription(it.item, 0, true) end end
            local assigned = 0
            for _, spec in ipairs(p.equipment.uniform[df.uniform_category.weapon]) do assigned = assigned + #spec.assigned end
            if wpn then armed = armed + 1 end
            members[#members + 1] = {id = u.id, name = C.name(u),
                                     leader = i == 0 or nil, weapon = wpn, weapon_assigned = assigned > 0, x = u.pos.x, y = u.pos.y, z = u.pos.z}
          end
        end
      end
      local orders = {}
      for _, od in ipairs(sq.orders) do
        if df.squad_order_kill_listst:is_instance(od) then
          local alive = 0
          for _, id in ipairs(od.units) do local t = df.unit.find(id) if t and not dfhack.units.isDead(t) then alive = alive + 1 end end
          orders[#orders + 1] = {order = 'attack', targets = #od.units, targets_alive = alive}
        elseif df.squad_order_movest:is_instance(od) then
          orders[#orders + 1] = {order = 'station', x = od.pos.x, y = od.pos.y, z = od.pos.z}
        else orders[#orders + 1] = {order = tostring(od._type)} end
      end
      local uniform = 'none'
      if sq.positions[0] and #sq.positions[0].equipment.uniform[df.uniform_category.weapon] > 0 then
        uniform = #sq.positions[0].equipment.uniform[df.uniform_category.body] > 0 and 'weapon+armor' or 'weapon_only' end
      r[#r + 1] = {id = sq.id, name = sq.alias ~= '' and sq.alias or dfhack.df2utf(dfhack.military.getSquadName(sq.id)),
                   members = members, armed = armed, uniform = uniform, orders = orders,
                   on_duty = #orders > 0}
    end
  end
  local free = 0
  for _, it in ipairs(items.WEAPON) do
    if not (it.flags.forbid or it.flags.in_inventory or it.flags.in_job or it.flags.trader) then free = free + 1 end
  end
  return {squads = r, weapons_free = free}
end)

try('burrows', function()
  local al, r = alert_burrows(), {}
  local cits = dfhack.units.getCitizens()
  for _, b in ipairs(df.global.plotinfo.burrows.list) do
    local inside = 0
    for _, u in ipairs(cits) do if dfhack.burrows.isAssignedTile(b, u.pos) then inside = inside + 1 end end
    local x1, y1, z1, x2, y2, z2, n = 1e9, 1e9, 1e9, -1, -1, -1, 0
    for _, blk in ipairs(dfhack.burrows.listBlocks(b)) do
      for bx = 0, 15 do for by = 0, 15 do
        if dfhack.burrows.isAssignedBlockTile(b, blk, bx, by) then
          local x, y, z = blk.map_pos.x + bx, blk.map_pos.y + by, blk.map_pos.z
          n = n + 1
          x1, y1, z1 = math.min(x1, x), math.min(y1, y), math.min(z1, z)
          x2, y2, z2 = math.max(x2, x), math.max(y2, y), math.max(z2, z)
        end
      end end
    end
    r[#r + 1] = {id = b.id, name = dfhack.df2utf(b.name), tiles = n, civ_alert_burrow = al[b.id] or false,
                 citizens_inside = inside, bbox = n > 0 and {x1 = x1, y1 = y1, x2 = x2, y2 = y2, z1 = z1, z2 = z2} or nil}
  end
  return {list = r, civilian_alert = df.global.plotinfo.alerts.civ_alert_idx ~= 0}
end)

try('doors', function()
  local r = {}
  for _, b in ipairs(df.global.world.buildings.all) do
    local hatch = df.building_hatchst:is_instance(b)
    if hatch or df.building_doorst:is_instance(b) then
      r[#r + 1] = {id = b.id, kind = hatch and 'hatch' or 'door', x = b.centerx, y = b.centery, z = b.z,
                   built = built(b), locked = b.door_flags.forbidden}
    end
  end
  local function free(v) local n = 0 for _, it in ipairs(v) do if not (it.flags.forbid or it.flags.in_building or it.flags.in_job or it.flags.in_inventory) then n = n + 1 end end return n end
  return {list = r, door_items_free = free(items.DOOR), hatch_cover_items_free = free(items.HATCH_COVER)}
end)

-- pending digging (schema 6, audit §c-16): the map-wide total as before, plus the count per z-level. Designations are
-- the player's own orders, so tiles still hidden count too.
do
  local ok, err = pcall(function()
    local n, by_z = 0, {}
    for _, blk in ipairs(df.global.world.map.map_blocks) do
      if blk.flags.designated then
        for x = 0, 15 do for y = 0, 15 do
          if blk.designation[x][y].dig ~= df.tile_dig_designation.No then
            n = n + 1
            local z = tostring(blk.map_pos.z)
            by_z[z] = (by_z[z] or 0) + 1
          end
        end end
      end
    end
    o.dig_designations_pending = n
    o.dig_pending_by_z = by_z
  end)
  if not ok then o.dig_designations_pending = 'ERR: ' .. tostring(err) end
end
end

-- box facts for remembered sites (rooms): open floor, designated, hidden and soil tiles in the box
try('box_facts', function()
  local r = {}
  for _, bx in ipairs(BOXES) do
    local floor, des, hidden, soil, n = 0, 0, 0, 0, 0
    for x = bx.x, bx.x + (bx.w or 1) - 1 do for y = bx.y, bx.y + (bx.h or 1) - 1 do
      n = n + 1
      local fl = dfhack.maps.getTileFlags(x, y, bx.z)
      if fl then
        if fl.dig ~= df.tile_dig_designation.No then des = des + 1 end
        if fl.hidden then hidden = hidden + 1 else
          local tt = dfhack.maps.getTileType(x, y, bx.z)
          local a = tt and df.tiletype.attrs[tt]
          if a and a.shape == df.tiletype_shape.FLOOR then
            floor = floor + 1
            if a.material == df.tiletype_material.SOIL then soil = soil + 1 end
          end
        end
      end
    end end
    r[tostring(bx.id)] = {tiles = n, floor = floor, soil_floor = soil, designated = des, hidden = hidden}
  end
  if #BOXES > 0 then return r end
end)

-- map facts and the raw site candidates (#85's searches, unchanged; schema 6 drops their ranked, advice-named lists:
-- sites.py gives each candidate its stable id and status and lists them by id)
try('map', function()
  local sz = {dfhack.maps.getSize()}
  local wx, wy, wz = wagon_pos()
  -- size: in map blocks of 16x16 tiles (x, y) and z-levels, as #85; size_tiles: the same in tiles
  return {size = sz, size_tiles = {sz[1] * 16, sz[2] * 16, sz[3]}, wagon = {x = wx, y = wy, z = wz, present = wagon ~= nil}, surface_z = wz}
end)

local SOILISH = {}
for _, n in ipairs({'SOIL', 'GRASS_LIGHT', 'GRASS_DARK', 'GRASS_DRY', 'GRASS_DEAD'}) do SOILISH[df.tiletype_material[n]] = true end

try('site_candidates', function()
  local w = wagon
  local wx, wy, wz = wagon_pos()
  local function in_wagon(x, y) return w and x >= w.x1 - 1 and x <= w.x2 + 1 and y >= w.y1 - 1 and y <= w.y2 + 1 end
  local function free(x, y, z, soil_only)
    local tt = dfhack.maps.getTileType(x, y, z)
    if not tt then return false end
    local a = df.tiletype.attrs[tt]
    if a.shape ~= df.tiletype_shape.FLOOR or a.material == df.tiletype_material.TREE then return false end
    if soil_only and not SOILISH[a.material] then return false end
    if dfhack.buildings.findAtTile(xyz2pos(x, y, z)) or in_wagon(x, y) then return false end
    local d = dfhack.maps.getTileFlags(x, y, z)
    return d and not d.hidden and d.dig == df.tile_dig_designation.No
  end
  local function box_soil(x, y, z, w_, h_)   -- all revealed tiles of the box soil/grass
    for ax = 0, w_ - 1 do for ay = 0, h_ - 1 do
      local tt = dfhack.maps.getTileType(x + ax, y + ay, z)
      if not tt or not C.revealed(x + ax, y + ay, z) or not SOILISH[df.tiletype.attrs[tt].material] then return false end
    end end
    return true
  end
  local function subterranean(x, y, z) local fl = dfhack.maps.getTileFlags(x, y, z) return fl and fl.subterranean or false end
  -- W: free 3x3 floor on the wagon's level (x,y = centre)
  local sites, wtaken = {}, {}
  for r = 3, 20 do
    for dx = -r, r, 2 do for dy = -r, r, 2 do
      if math.max(math.abs(dx), math.abs(dy)) == r then
        local x, y, ok = wx + dx, wy + dy, true
        for ax = -1, 1 do for ay = -1, 1 do
          if not free(x + ax, y + ay, wz) or wtaken[(x + ax) .. ',' .. (y + ay)] then ok = false end
        end end
        if ok and #sites < 8 then
          sites[#sites + 1] = {x = x, y = y, z = wz, w = 3, h = 3, anchor = 'centre', soil = box_soil(x - 1, y - 1, wz, 3, 3),
                               subterranean = subterranean(x, y, wz)}
          for ax = -1, 1 do for ay = -1, 1 do wtaken[(x + ax) .. ',' .. (y + ay)] = true end end
        end
      end
    end end
  end
  -- G: surface soil 3x3 (top-left)
  local farm = {}
  for r = 4, 24 do
    for dx = -r, r, 3 do for dy = -r, r, 3 do
      if math.max(math.abs(dx), math.abs(dy)) == r and #farm < 4 then
        local x, y, ok = wx + dx, wy + dy, true
        for ax = 0, 2 do for ay = 0, 2 do if not free(x + ax, y + ay, wz, true) then ok = false end end end
        if ok then farm[#farm + 1] = {x = x, y = y, z = wz, w = 3, h = 3, soil = true, subterranean = subterranean(x, y, wz)} end
      end
    end end
  end
  -- F: dug soil floor 3x3 below the surface (top-left)
  local ug, taken = {}, {}
  for z = wz - 1, math.max(0, wz - 6), -1 do
    for x = wx - 25, wx + 25 do for y = wy - 25, wy + 25 do
      if #ug < 4 then
        local ok = true
        for ax = 0, 2 do for ay = 0, 2 do
          local tt = dfhack.maps.getTileType(x + ax, y + ay, z)
          local at = tt and df.tiletype.attrs[tt]
          if not at or at.shape ~= df.tiletype_shape.FLOOR or at.material ~= df.tiletype_material.SOIL
             or taken[(x + ax) .. ',' .. (y + ay) .. ',' .. z] or dfhack.maps.getTileFlags(x + ax, y + ay, z).hidden
             or dfhack.buildings.findAtTile(xyz2pos(x + ax, y + ay, z)) then ok = false end
        end end
        if ok then
          ug[#ug + 1] = {x = x, y = y, z = z, w = 3, h = 3, soil = true, subterranean = subterranean(x, y, z)}
          for ax = 0, 2 do for ay = 0, 2 do taken[(x + ax) .. ',' .. (y + ay) .. ',' .. z] = true end end
        end
      end
    end end
  end
  -- E: down stairs on the surface level; A: the dug area per level below it (bounding box)
  local access, areas = {}, {}
  for x = wx - 30, wx + 30 do for y = wy - 30, wy + 30 do
    local tt = dfhack.maps.getTileType(x, y, wz)
    local sh = tt and df.tiletype.attrs[tt].shape
    if (sh == df.tiletype_shape.STAIR_DOWN or sh == df.tiletype_shape.STAIR_UPDOWN) and #access < 8
       and not dfhack.maps.getTileFlags(x, y, wz).hidden then
      access[#access + 1] = {x = x, y = y, z = wz, w = 1, h = 1, kind = 'down_stair', building = dfhack.buildings.findAtTile(xyz2pos(x, y, wz)) and true or false}
    end
  end end
  for z = wz - 1, math.max(0, wz - 6), -1 do
    local x1, y1, x2, y2, n = 1e9, 1e9, -1, -1, 0
    for x = wx - 30, wx + 30 do for y = wy - 30, wy + 30 do
      local tt = dfhack.maps.getTileType(x, y, z)
      local sh = tt and df.tiletype.attrs[tt].shape
      if sh == df.tiletype_shape.FLOOR or sh == df.tiletype_shape.STAIR_UP or sh == df.tiletype_shape.STAIR_DOWN or sh == df.tiletype_shape.STAIR_UPDOWN then
        local fl = dfhack.maps.getTileFlags(x, y, z)
        if not fl.hidden and not fl.outside then
          n = n + 1; x1, y1, x2, y2 = math.min(x1, x), math.min(y1, y), math.max(x2, x), math.max(y2, y)
        end
      end
    end end
    if n > 0 then areas[#areas + 1] = {z = z, x = x1, y = y1, w = x2 - x1 + 1, h = y2 - y1 + 1, open_tiles = n, subterranean = true} end
  end
  -- S: free surface floor tiles where a stair can start (clear of the wagon and of W sites)
  local stairs = {}
  for r = 3, 14 do
    for dx = -r, r, 2 do for dy = -r, r, 2 do
      if math.max(math.abs(dx), math.abs(dy)) == r and #stairs < 4 then
        local x, y = wx + dx, wy + dy
        if free(x, y, wz) and not wtaken[x .. ',' .. y] then
          local tt = dfhack.maps.getTileType(x, y, wz)
          stairs[#stairs + 1] = {x = x, y = y, z = wz, w = 1, h = 1, soil = SOILISH[df.tiletype.attrs[tt].material] or false}
        end
      end
    end end
  end
  -- R: a 3x3 box beside a dug stair below the surface; the row next to the stair is revealed solid wall (soil = that
  -- whole row is soil); the far rows may still be hidden
  local rooms, rtaken = {}, {}
  local function wall_at(x, y, z)
    local fl = dfhack.maps.getTileFlags(x, y, z)
    if not fl then return nil end
    if fl.hidden then return false, false end
    local tt = dfhack.maps.getTileType(x, y, z)
    local a = tt and df.tiletype.attrs[tt]
    if not a or a.shape ~= df.tiletype_shape.WALL or a.material == df.tiletype_material.TREE then return nil end
    if fl.dig ~= df.tile_dig_designation.No then return nil end
    return true, a.material == df.tiletype_material.SOIL
  end
  for z = wz - 1, math.max(0, wz - 8), -1 do
    for x = wx - 25, wx + 25 do for y = wy - 25, wy + 25 do
      local tt = dfhack.maps.getTileType(x, y, z)
      local sh = tt and df.tiletype.attrs[tt].shape
      if (sh == df.tiletype_shape.STAIR_UP or sh == df.tiletype_shape.STAIR_UPDOWN or sh == df.tiletype_shape.STAIR_DOWN)
         and not dfhack.maps.getTileFlags(x, y, z).hidden and #rooms < 4 then
        for _, b in ipairs({{x + 1, y - 1, 'x', x + 1}, {x - 3, y - 1, 'x', x - 1}, {x - 1, y + 1, 'y', y + 1}, {x - 1, y - 3, 'y', y - 1}}) do
          local bx, by, axis, near = b[1], b[2], b[3], b[4]
          local ok, soil = true, true
          for ax = 0, 2 do for ay = 0, 2 do
            local tx, ty = bx + ax, by + ay
            local rev, is_soil = wall_at(tx, ty, z)
            if rev == nil or rtaken[tx .. ',' .. ty .. ',' .. z] then ok = false
            elseif (axis == 'x' and tx == near) or (axis == 'y' and ty == near) then
              if not rev then ok = false elseif not is_soil then soil = false end
            end
          end end
          if ok and #rooms < 4 then
            rooms[#rooms + 1] = {x = bx, y = by, z = z, w = 3, h = 3, soil = soil, subterranean = true, stair = {x = x, y = y}}
            for ax = 0, 2 do for ay = 0, 2 do rtaken[(bx + ax) .. ',' .. (by + ay) .. ',' .. z] = true end end
          end
        end
      end
    end end
  end
  -- D: one-tile chokepoints below the surface (floor with wall on two opposite sides, open on the other two)
  local doorways = {}
  local function shape(x, y, z)
    local fl = dfhack.maps.getTileFlags(x, y, z)
    if not fl or fl.hidden then return nil end
    local t = dfhack.maps.getTileType(x, y, z) return t and df.tiletype.attrs[t].shape
  end
  local function walk(sh) return sh == df.tiletype_shape.FLOOR or sh == df.tiletype_shape.STAIR_UP
                                 or sh == df.tiletype_shape.STAIR_DOWN or sh == df.tiletype_shape.STAIR_UPDOWN end
  for z = wz - 1, math.max(0, wz - 6), -1 do
    for x = wx - 30, wx + 30 do for y = wy - 30, wy + 30 do
      if #doorways < 6 and shape(x, y, z) == df.tiletype_shape.FLOOR then
        local fl = dfhack.maps.getTileFlags(x, y, z)
        local W = df.tiletype_shape.WALL
        if not fl.hidden and fl.dig == df.tile_dig_designation.No and not dfhack.buildings.findAtTile(xyz2pos(x, y, z)) then
          local ns = shape(x, y - 1, z) == W and shape(x, y + 1, z) == W and walk(shape(x - 1, y, z)) and walk(shape(x + 1, y, z))
          local ew = shape(x - 1, y, z) == W and shape(x + 1, y, z) == W and walk(shape(x, y - 1, z)) and walk(shape(x, y + 1, z))
          if ns or ew then doorways[#doorways + 1] = {x = x, y = y, z = z, w = 1, h = 1, kind = 'doorway'} end
        end
      end
    end end
  end
  return {W = sites, G = farm, F = ug, E = access, A = areas, S = stairs, R = rooms, D = doorways}
end)

print(json.encode(o, {pretty = false}))
