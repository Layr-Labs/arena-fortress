-- observe2.lua: rich, read-only fortress observation for harness v2. Prints one JSON object.
local json = require('json')
local o = {}
local function try(name, fn)   -- a field whose function returns nil is left out (v2: moods, water_on_fort_levels)
  local ok, v = pcall(fn)
  if ok then o[name] = v else o[name] = 'ERR: ' .. tostring(v) end
end
local ent = df.historical_entity.find(df.global.plotinfo.group_id)

try('date', function()
  local t = df.global.cur_year_tick
  return {year = df.global.cur_year, day_of_year = t // 1200 + 1,
          season = ({'spring', 'summer', 'autumn', 'winter'})[t // 100800 + 1], abs_tick = df.global.cur_year * 403200 + t}
end)

local function citizens() local r = {} for _, u in ipairs(df.global.world.units.active) do if dfhack.units.isCitizen(u) then r[#r + 1] = u end end return r end

try('dwarves', function()
  local r = {}
  for _, u in ipairs(citizens()) do
    local nob = dfhack.units.getNoblePositions(u)
    local titles = {}
    if nob then for _, p in ipairs(nob) do titles[#titles + 1] = p.position.code end end
    r[#r + 1] = {id = u.id, name = dfhack.df2utf(dfhack.units.getReadableName(u)):gsub(' ".-"', ''),
      profession = dfhack.units.getProfessionName(u),
      job = u.job.current_job and df.job_type[u.job.current_job.job_type] or 'idle',
      positions = titles,
      organizer_skill = dfhack.units.getNominalSkill(u, df.job_skill.ORGANIZATION, true),
      stress = dfhack.units.getStressCategory(u)}   -- 0 most stressed .. 6; recorder.lua counts <= 1 as stressed
  end
  return r
end)

try('stressed_citizens', function()   -- same definition as recorder.lua's daily `stressed` sample
  local n = 0
  for _, u in ipairs(citizens()) do if dfhack.units.getStressCategory(u) <= 1 then n = n + 1 end end
  return n
end)

-- The manager's office (v2). From OFFICE_FROM citizens the manager validates new work orders only from an Office
-- zone assigned to them with a built chair in it; the noble screen shows the unmet room need. Checked in game
-- 2026-10-13 on scripted-2-y2 (22 citizens): orders stayed unvalidated 5 days with no office, 4 more with an assigned
-- office and no chair, and validated within 2-4 days once a chair was built in it (docs/BENCHMARK-v2.md).
local OFFICE_FROM = 20
local function built(b) return b:getBuildStage() >= b:getMaxBuildStage() end
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
  local r = {}
  for _, asg in ipairs(ent.positions.assignments) do
    for _, ps in ipairs(ent.positions.own) do
      if ps.id == asg.position_id and (ps.code == 'MANAGER' or ps.code == 'BOOKKEEPER' or ps.code == 'EXPEDITION_LEADER' or ps.code == 'CHIEF_MEDICAL_DWARF' or ps.code == 'BROKER') then
        local hf = asg.histfig ~= -1 and df.historical_figure.find(asg.histfig)
        r[ps.code] = hf and (df.unit.find(hf.unit_id) and dfhack.df2utf(dfhack.units.getReadableName(df.unit.find(hf.unit_id))):gsub(' ".-"', '') or 'hf ' .. hf.id) or 'VACANT'
      end
    end
  end
  r.manager_active_for_orders = #ent.assignments_by_type.MANAGE_PRODUCTION > 0
  for _, asg in ipairs(ent.positions.assignments) do
    for _, ps in ipairs(ent.positions.own) do
      local hf = ps.id == asg.position_id and ps.code == 'MANAGER' and asg.histfig ~= -1 and df.historical_figure.find(asg.histfig)
      local u = hf and df.unit.find(hf.unit_id)
      if u then
        local z, chair = office_of(u)
        r.manager_office = z and {zone_id = z.id, chair = chair} or 'none'
        r.manager_needs_office = ps.required_office > 0 and #citizens() >= OFFICE_FROM
      end
    end
  end
  return r
end)

-- No hidden map information (BENCHMARK-v1 §4.3): an item on an unrevealed tile (an unexplored cavern, undug rock)
-- is not visible to a player, so it is left out of every count. Items in containers or carried use their holder's tile.
local function seen(it)
  local x, y, z = dfhack.items.getPosition(it)
  if not x then return true end
  local fl = dfhack.maps.getTileFlags(x, y, z)
  return not (fl and fl.hidden)
end
-- v2.2 (obs 5): a unit a player can see: on a revealed tile (isVisible) and not sneaking or in ambush (isHidden).
-- isHidden alone let creatures in unexplored caverns into threats. Out of line of sight is fine: the map shows them.
local function visible_unit(u) return dfhack.units.isVisible(u) and not dfhack.units.isHidden(u) end
-- v2.2: a report about something on an unrevealed tile (a fight in an unexplored cavern) stays out, unless the game
-- put it in the announcement list, which the player reads whatever its position
local function report_seen(rp)
  local ok, keep = pcall(function()
    if rp.flags.announcement then return true end
    local p = rp.pos
    if not p or p.x < 0 then return true end
    local fl = dfhack.maps.getTileFlags(p.x, p.y, p.z)
    return not (fl and fl.hidden)
  end)
  return not ok or keep
end
-- world.items.other.<KIND>, revealed items only (cached per kind for this observation)
local items = setmetatable({}, {__index = function(t, k)
  local r = {}
  for _, it in ipairs(df.global.world.items.other[k]) do if seen(it) then r[#r + 1] = it end end
  t[k] = r
  return r
end})

try('stocks', function()
  local other = items
  local function sum(v) local n = 0 for _, it in ipairs(v) do n = n + it.stack_size end return n end
  local usable_logs, wagon_logs = 0, 0
  for _, it in ipairs(other.WOOD) do
    if it.flags.in_building or it.flags.forbid or it.flags.in_job then wagon_logs = wagon_logs + 1 else usable_logs = usable_logs + 1 end
  end
  local function empties(v) local n = 0 for _, b in ipairs(v) do if #dfhack.items.getContainedItems(b) == 0 and not b.flags.in_job then n = n + 1 end end return n end
  -- plants: only usable ones (rotten or forbidden plants can't be brewed or cooked; counting them hid shortages),
  -- by kind, so an agent can tell brewable from cookable stock
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
  -- seeds by kind, with what the plant needs: underground plants grow only on subterranean plots
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
  -- built furniture items that aren't placed yet (place_furniture uses these)
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
  local meals = sum(other.FOOD)
  return {drink = sum(other.DRINK), food_edible = sum(other.ANY_GOOD_FOOD), prepared_meals = meals,
          plants_total = plants_usable, plants_brewable = brewable, plants_rotten = plants_rotten, seeds = sum(other.SEEDS),
          plants_by_kind = by_kind, seeds_by_kind = seeds_by_kind,
          logs_usable = usable_logs, logs_unusable = wagon_logs, boulders = #other.BOULDER, boulders_usable = boulders_usable,
          barrels_total = #other.BARREL, barrels_empty = empties(other.BARREL),
          beds = #other.BED, furniture_free = furniture_free}
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
    local furnace = df.building_furnacest:is_instance(b)   -- WoodFurnace is a furnace, not a workshop, in DF
    if furnace or df.building_workshopst:is_instance(b) then
      local jobs = {}
      for _, j in ipairs(b.jobs) do jobs[#jobs + 1] = df.job_type[j.job_type] .. (j.flags.by_manager and '(order)' or '') end
      r[#r + 1] = {id = b.id, type = furnace and df.furnace_type[b.type] or df.workshop_type[b.type], x = b.centerx, y = b.centery, z = b.z,
                   built = b:getBuildStage() >= b:getMaxBuildStage(), jobs = jobs}
    end
  end
  return r
end)

try('zones', function()   -- activity zones (make_zone): bedrooms, dormitories, dining halls, meeting areas, offices
  local r = {}
  for _, z in ipairs(df.global.world.buildings.other.ACTIVITY_ZONE) do
    if #r < 12 then
      local furn = {}
      for _, b in ipairs(z.contained_buildings) do
        if built(b) then local t = df.building_type[b:getType()]:lower() furn[t] = (furn[t] or 0) + 1 end
      end
      r[#r + 1] = {id = z.id, type = df.civzone_type[z.type], x = z.x1, y = z.y1, z = z.z,
                   w = z.x2 - z.x1 + 1, h = z.y2 - z.y1 + 1,
                   owner = z.assigned_unit_id ~= -1 and z.assigned_unit_id or nil, furniture = next(furn) and furn or nil}
    end
  end
  return r
end)

try('farm_plots', function()
  local r = {}
  for _, b in ipairs(df.global.world.buildings.other.FARM_PLOT) do
    local planted = 0
    for _, ci in ipairs(b.contained_items) do if df.item_plantst:is_instance(ci.item) or df.item_seedsst:is_instance(ci.item) then planted = planted + 1 end end
    r[#r + 1] = {id = b.id, x = b.x1, y = b.y1, z = b.z, w = b.x2 - b.x1 + 1, h = b.y2 - b.y1 + 1,
                 built = b:getBuildStage() >= b:getMaxBuildStage(), seeds_or_crops_in_plot = planted,
                 crop_this_season = b.plant_id[df.global.cur_season] ~= -1 and df.global.world.raws.plants.all[b.plant_id[df.global.cur_season]].id or 'none'}
  end
  return r
end)

try('orders', function()
  local r = {}
  for _, ord in ipairs(df.global.world.manager_orders.all) do
    local spawned = 0
    local l = df.global.world.jobs.list.next
    while l do if l.item.order_id == ord.id then spawned = spawned + 1 end l = l.next end
    r[#r + 1] = {id = ord.id, job = df.job_type[ord.job_type], reaction = ord.reaction_name ~= '' and ord.reaction_name or nil,
                 meal_kind = ord.job_type == df.job_type.PrepareMeal and ord.mat_type or nil,
                 left = ord.amount_left, total = ord.amount_total, validated = ord.status.validated,
                 active = ord.status.active, jobs_in_progress = spawned}
    local o = r[#r]
    if ord.frequency ~= df.workquota_frequency_type.OneTime then
      o["repeat"] = df.workquota_frequency_type[ord.frequency]:lower()   -- `repeat` is a Lua keyword
      local w = {}
      for _, c in ipairs(ord.item_conditions) do
        w[#w + 1] = {item = df.item_type[c.item_type], test = df.logic_condition_type[c.compare_type], value = c.compare_val}
      end
      if #w > 0 then o.when = w end
    end
  end
  return r
end)

-- reports are kept for a long time: without an age limit, a 45-day-old cancellation was shown as "recent"
local NOW = df.global.cur_year * 403200 + df.global.cur_year_tick
local function age_ticks(rp) return NOW - (rp.year * 403200 + rp.time) end

try('recent_cancellations', function()   -- last 3 days
  local rep, r = df.global.world.status.reports, {}
  for i = #rep - 1, math.max(0, #rep - 200), -1 do
    if age_ticks(rep[i]) > 3 * 1200 then break end
    local t = dfhack.df2utf(rep[i].text)
    if (t:find(' cancels ') or t:find('unable to')) and report_seen(rep[i]) then r[#r + 1] = t:gsub('%[[^%]]*%]', '') end
    if #r >= 8 then break end
  end
  return r
end)

try('recent_events', function()   -- last 7 days
  local rep, r = df.global.world.status.reports, {}
  for i = #rep - 1, math.max(0, #rep - 60), -1 do
    if age_ticks(rep[i]) > 7 * 1200 then break end
    local t = dfhack.df2utf(rep[i].text):gsub('%[[^%]]*%]', '')
    if not t:find(' cancels ') and #t < 300 and report_seen(rep[i]) then r[#r + 1] = t end
    if #r >= 6 then break end
  end
  return r
end)

local function wagon_pos()
  for _, b in ipairs(df.global.world.buildings.all) do if df.building_wagonst:is_instance(b) then return b.centerx, b.centery, b.z end end
  return 97, 96, 106
end

local function alert_burrows()
  local l = df.global.plotinfo.alerts.list
  local r = {}
  if #l > 1 then for _, id in ipairs(l[1].burrows) do r[id] = true end end
  return r
end

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
  local dead = 0  -- fortress members only: pets/livestock share the fort's civ_id
  local inv_dead = 0
  for _, u in ipairs(df.global.world.units.all) do
    if dfhack.units.isDead(u) then
      if dfhack.units.isOwnGroup(u) and not dfhack.units.isAnimal(u) then dead = dead + 1
      elseif (u.flags1.invader_origin or u.flags1.active_invader) then
        -- v2: only deaths a player could see (the body lies on a revealed tile); unseen deaths stay unknown
        local x, y, z = dfhack.units.getPosition(u)
        local fl = x and dfhack.maps.getTileFlags(x, y, z)
        if fl and not fl.hidden then inv_dead = inv_dead + 1 end
      end
    end
  end
  return {visible_hostiles = hostile, dead_citizens_total = dead, invaders_dead = inv_dead, by_race = by_race,
          nearest_hostile_dist_to_wagon = nearest, hostiles = list,
          note = 'dist_to_wagon: tiles (max of |dx|,|dy|, plus 3 per z-level) from the wagon at the fort centre'}
end)

-- v2 (BENCHMARK-v1 §2.4.4): strange moods as the unit sheet and the mood announcements show them. The workshop a
-- mood claims follows from its skill (the DF wiki's table); items are the mood job's requirements, with how many
-- the dwarf has collected so far.
local MOOD_WORKSHOP = {WOODCRAFT = 'Craftsdwarfs', STONECRAFT = 'Craftsdwarfs', BONECARVE = 'Craftsdwarfs',
  CARPENTRY = 'Carpenters', MASONRY = 'Masons', STONECUTTING = 'Masons', ENGRAVE_STONE = 'Masons',
  BOWYER = 'Bowyers', TANNER = 'Leatherworks', LEATHERWORK = 'Leatherworks', WEAVING = 'Loom',
  CLOTHESMAKING = 'Clothiers', GLASSMAKER = 'GlassFurnace', CUTGEM = 'Jewelers', ENCRUSTGEM = 'Jewelers',
  FORGE_WEAPON = 'MetalsmithsForge', FORGE_ARMOR = 'MetalsmithsForge', FORGE_FURNITURE = 'MetalsmithsForge',
  METALCRAFT = 'MetalsmithsForge', MECHANICS = 'Mechanics'}
try('moods', function()
  local r = {}
  for _, u in ipairs(citizens()) do
    local m = df.mood_type[u.mood]
    if u.mood ~= -1 and m and m ~= 'Baby' and m ~= 'None' then
      local skill = df.job_skill[u.job.mood_skill]
      local e = {unit_id = u.id, mood = m, skill = skill, workshop_needed = skill and MOOD_WORKSHOP[skill] or skill}
      local j = u.job.current_job
      if j and j.job_type == df.job_type.StrangeMood then
        local b = dfhack.job.getHolder(j)
        e.claimed_building_id = b and b.id or nil
        local need = {}
        for i, ji in ipairs(j.job_items) do
          local mi = ji.mat_type >= 0 and dfhack.matinfo.decode(ji.mat_type, ji.mat_index)
          local have = 0
          for _, ref in ipairs(j.items) do if ref.job_item_idx == i then have = have + 1 end end
          need[#need + 1] = {item = df.item_type[ji.item_type] or 'any', material = mi and mi:toString() or nil,
                             quantity = ji.quantity, collected = have}
        end
        if #need > 0 then e.items_needed = need end
      end
      r[#r + 1] = e
    end
  end
  if #r > 0 then return r end
end)

-- v2 (BENCHMARK-v1 §LT07): water on the fortress levels a player can see. The same scan as advance.lua's
-- water_rising tripwire: revealed, indoor tiles within 30 tiles of the wagon, from 8 levels below it up.
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
            members[#members + 1] = {id = u.id, name = dfhack.df2utf(dfhack.units.getReadableName(u)):gsub(' ".-"', ''),
                                     leader = i == 0 or nil, weapon = wpn, weapon_assigned = assigned > 0, x = u.pos.x, y = u.pos.y, z = u.pos.z}
          end
        end
      end
      local orders = {}
      for _, o in ipairs(sq.orders) do
        if df.squad_order_kill_listst:is_instance(o) then
          local alive = 0
          for _, id in ipairs(o.units) do local t = df.unit.find(id) if t and not dfhack.units.isDead(t) then alive = alive + 1 end end
          orders[#orders + 1] = {order = 'attack', targets = #o.units, targets_alive = alive}
        elseif df.squad_order_movest:is_instance(o) then
          orders[#orders + 1] = {order = 'station', x = o.pos.x, y = o.pos.y, z = o.pos.z}
        else orders[#orders + 1] = {order = tostring(o._type)} end
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
                   built = b:getBuildStage() >= b:getMaxBuildStage(), locked = b.door_flags.forbidden}
    end
  end
  local function free(v) local n = 0 for _, it in ipairs(v) do if not (it.flags.forbid or it.flags.in_building or it.flags.in_job or it.flags.in_inventory) then n = n + 1 end end return n end
  return {list = r, door_items_free = free(items.DOOR), hatch_cover_items_free = free(items.HATCH_COVER)}
end)

try('dig_designations_pending', function()
  local n = 0
  for _, blk in ipairs(df.global.world.map.map_blocks) do
    if blk.flags.designated then for x = 0, 15 do for y = 0, 15 do if blk.designation[x][y].dig ~= df.tile_dig_designation.No then n = n + 1 end end end end
  end
  return n
end)

try('map', function()
  local w
  for _, b in ipairs(df.global.world.buildings.all) do if df.building_wagonst:is_instance(b) then w = b end end
  local sz = {dfhack.maps.getSize()}
  local wx, wy, wz = w and w.centerx or 97, w and w.centery or 96, w and w.z or 106
  local function in_wagon(x, y) return w and x >= w.x1 - 1 and x <= w.x2 + 1 and y >= w.y1 - 1 and y <= w.y2 + 1 end
  -- free 3x3 floor sites on the wagon's level (for workshops), nearest first
  local sites = {}
  local function free(x, y, z, soil_only)
    local tt = dfhack.maps.getTileType(x, y, z)
    if not tt then return false end
    local a = df.tiletype.attrs[tt]
    if a.shape ~= df.tiletype_shape.FLOOR or a.material == df.tiletype_material.TREE then return false end
    if soil_only and not (a.material == df.tiletype_material.SOIL or a.material == df.tiletype_material.GRASS_LIGHT or a.material == df.tiletype_material.GRASS_DARK
                          or a.material == df.tiletype_material.GRASS_DRY or a.material == df.tiletype_material.GRASS_DEAD) then return false end
    if dfhack.buildings.findAtTile(xyz2pos(x, y, z)) or in_wagon(x, y) then return false end
    local d = dfhack.maps.getTileFlags(x, y, z)
    return d and not d.hidden and d.dig == df.tile_dig_designation.No
  end
  local wtaken = {}
  for r = 3, 20 do
    for dx = -r, r, 2 do for dy = -r, r, 2 do
      if math.max(math.abs(dx), math.abs(dy)) == r then
        local x, y, ok = wx + dx, wy + dy, true
        for ax = -1, 1 do for ay = -1, 1 do
          if not free(x + ax, y + ay, wz) or wtaken[(x + ax) .. ',' .. (y + ay)] then ok = false end
        end end
        if ok and #sites < 8 then   -- never overlap: building one listed site must not invalidate another
          sites[#sites + 1] = {x = x, y = y, z = wz}
          for ax = -1, 1 do for ay = -1, 1 do wtaken[(x + ax) .. ',' .. (y + ay)] = true end end
        end
      end
    end end
  end
  local farm = {}
  for r = 4, 24 do
    for dx = -r, r, 3 do for dy = -r, r, 3 do
      if math.max(math.abs(dx), math.abs(dy)) == r and #farm < 4 then
        local x, y, ok = wx + dx, wy + dy, true
        for ax = 0, 2 do for ay = 0, 2 do if not free(x + ax, y + ay, wz, true) then ok = false end end end
        if ok then farm[#farm + 1] = {x = x, y = y, z = wz, w = 3, h = 3} end
      end
    end end
  end
  -- underground dug soil floor (where the starting seeds actually grow)
  local ug, taken = {}, {}  -- taken: tiles inside an already-listed site, so candidates never overlap
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
          ug[#ug + 1] = {x = x, y = y, z = z, w = 3, h = 3}
          for ax = 0, 2 do for ay = 0, 2 do taken[(x + ax) .. ',' .. (y + ay) .. ',' .. z] = true end end
        end
      end
    end end
  end
  -- entrances: down stairs / ramps on the surface level near the wagon (hatch-cover spots), and the dug areas below
  local access, areas = {}, {}
  for x = wx - 30, wx + 30 do for y = wy - 30, wy + 30 do
    local tt = dfhack.maps.getTileType(x, y, wz)
    local sh = tt and df.tiletype.attrs[tt].shape
    if (sh == df.tiletype_shape.STAIR_DOWN or sh == df.tiletype_shape.STAIR_UPDOWN) and #access < 8
       and not dfhack.maps.getTileFlags(x, y, wz).hidden then
      access[#access + 1] = {x = x, y = y, z = wz, kind = 'down_stair', building = dfhack.buildings.findAtTile(xyz2pos(x, y, wz)) and true or nil}
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
    if n > 0 then areas[#areas + 1] = {z = z, x = x1, y = y1, w = x2 - x1 + 1, h = y2 - y1 + 1, open_tiles = n} end
  end
  -- stair starts: free surface floor near the wagon (clear of its footprint), spaced apart. Only the surface tile is
  -- checked: what lies below is hidden until dug.
  local stairs = {}
  for r = 3, 14 do
    for dx = -r, r, 2 do for dy = -r, r, 2 do
      if math.max(math.abs(dx), math.abs(dy)) == r and #stairs < 4 then
        local x, y = wx + dx, wy + dy
        if free(x, y, wz) and not wtaken[x .. ',' .. y] then stairs[#stairs + 1] = {x = x, y = y, z = wz} end
      end
    end end
  end
  -- rooms: a 3x3 box beside a dug stair below the surface, on its level. The box's row next to the stair must be
  -- revealed solid wall (soil = all of that row is soil); the far rows may still be hidden.
  local rooms, rtaken = {}, {}
  local function wall_at(x, y, z)   -- nil: not usable; false: hidden (not looked at: no hidden-map leak); true: revealed wall
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
            local revealed, is_soil = wall_at(tx, ty, z)
            if revealed == nil or rtaken[tx .. ',' .. ty .. ',' .. z] then ok = false
            elseif (axis == 'x' and tx == near) or (axis == 'y' and ty == near) then
              if not revealed then ok = false elseif not is_soil then soil = false end
            end
          end end
          if ok and #rooms < 4 then
            rooms[#rooms + 1] = {x = bx, y = by, z = z, w = 3, h = 3, soil = soil, stair = {x = x, y = y}}
            for ax = 0, 2 do for ay = 0, 2 do rtaken[(bx + ax) .. ',' .. (by + ay) .. ',' .. z] = true end end
          end
        end
      end
    end end
  end
  -- doorways (v2): one-tile chokepoints below the surface: a revealed floor tile with wall on two opposite sides and
  -- open floor or stair on the other two (a corridor tile, a room's opening, the tile beside a stair foot). A door or
  -- a wall (build_door, build_wall) there closes the way through.
  local doorways = {}
  local function shape(x, y, z)   -- v2.2: nil for an unrevealed neighbour (its shape isn't known to a player)
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
          if ns or ew then doorways[#doorways + 1] = {x = x, y = y, z = z, kind = 'doorway'} end
        end
      end
    end end
  end
  return {stair_sites = stairs, room_sites = rooms, doorways = doorways,
          surface_entrances = access, underground_dug_areas = areas,
          underground_soil_farm_sites = ug,
          surface_soil_sites_NOT_for_starting_seeds = farm, size = sz, wagon = {x = wx, y = wy, z = wz}, surface_z = wz, free_3x3_sites_near_wagon = sites}
end)

print(json.encode(o))
