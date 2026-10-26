-- fort_summary.lua: a compact, read-only summary of the loaded fort, printed as one JSON line.
-- Used by embark/make_task_fort.sh to check a built task fort against its recipe's `expect` ranges, and to compare
-- a seed-built fort with the legacy snapshot it replaces (population, stocks, workshops, farms, stress, nobles,
-- plugins, pending events). Reads hidden tiles only for `dug_below_surface`, so run it at build time, never in a run.
local json = require('json')
local o = {}
local function try(name, fn) local ok, v = pcall(fn) o[name] = ok and v or ('ERR: ' .. tostring(v)) end
local items = df.global.world.items.other
local function sum(v) local n = 0 for _, it in ipairs(v) do n = n + it.stack_size end return n end
local function free(it) return not (it.flags.in_building or it.flags.forbid or it.flags.in_job or it.flags.construction) end
local function citizens() local r = {} for _, u in ipairs(df.global.world.units.active) do if dfhack.units.isCitizen(u) then r[#r + 1] = u end end return r end

try('date', function()
  local t = df.global.cur_year_tick
  return {year = df.global.cur_year, tick = t, day = t // 1200 + 1, abs_tick = df.global.cur_year * 403200 + t,
          season = ({'spring', 'summer', 'autumn', 'winter'})[t // 100800 + 1]}
end)
try('pop', function()
  local n, adults, kids, hist, stress, cats, moods = 0, 0, 0, 0, 0, {0, 0, 0, 0, 0, 0, 0}, 0
  for _, u in ipairs(citizens()) do
    n = n + 1
    if dfhack.units.isAdult(u) then adults = adults + 1 else kids = kids + 1 end
    if u.hist_figure_id ~= -1 then hist = hist + 1 end
    local c = dfhack.units.getStressCategory(u); cats[c + 1] = cats[c + 1] + 1
    if u.status.current_soul then stress = stress + u.status.current_soul.personality.stress end
    if u.mood ~= -1 then moods = moods + 1 end
  end
  return {citizens = n, adults = adults, children = kids, with_histfig = hist, moods = moods,
          stress_mean = n > 0 and math.floor(stress / n) or 0, stress_cat = cats,
          stressed = cats[1] + cats[2]}   -- recorder.lua's definition: category <= 1
end)
try('stocks', function()
  local brewable, plants = 0, 0
  for _, it in ipairs(items.PLANT) do
    local m = dfhack.matinfo.decode(it)
    if m and m.plant and not it.flags.rotten and not it.flags.forbid then
      plants = plants + it.stack_size
      for _, p in ipairs(m.material.reaction_product.id) do if p.value == 'DRINK_MAT' then brewable = brewable + it.stack_size break end end
    end
  end
  local function nfree(v) local n = 0 for _, it in ipairs(v) do if free(it) then n = n + 1 end end return n end
  local empty = 0
  for _, b in ipairs(items.BARREL) do if #dfhack.items.getContainedItems(b) == 0 and not b.flags.in_job then empty = empty + 1 end end
  return {drink = sum(items.DRINK), food = sum(items.ANY_GOOD_FOOD), meals = sum(items.FOOD), plants = plants,
          plants_brewable = brewable, seeds = sum(items.SEEDS), logs = #items.WOOD, logs_free = nfree(items.WOOD),
          boulders = #items.BOULDER, barrels = #items.BARREL, barrels_empty = empty, bins = #items.BIN,
          beds = #items.BED, beds_free = nfree(items.BED), tables = #items.TABLE, tables_free = nfree(items.TABLE),
          chairs = #items.CHAIR, chairs_free = nfree(items.CHAIR), doors = #items.DOOR, hatch_covers = #items.HATCH_COVER}
end)
try('buildings', function()
  local ws, farms, ug_farms, planted, piles, zones, beds_placed, other = {}, 0, 0, 0, 0, {}, 0, 0
  local sz = nil
  for _, b in ipairs(df.global.world.buildings.all) do
    if df.building_wagonst:is_instance(b) then sz = b.z end
  end
  for _, b in ipairs(df.global.world.buildings.all) do
    local t = b:getType()
    if t == df.building_type.Workshop or t == df.building_type.Furnace then
      local k = (t == df.building_type.Workshop and df.workshop_type or df.furnace_type)[b:getSubtype()]
      local done = b:getBuildStage() >= b:getMaxBuildStage()
      ws[k] = (ws[k] or 0) + (done and 1 or 0)
    elseif t == df.building_type.FarmPlot then
      farms = farms + 1
      if sz and b.z < sz then ug_farms = ug_farms + 1 end
      for _, c in ipairs(b.plant_id) do if c ~= -1 then planted = planted + 1 break end end
    elseif t == df.building_type.Stockpile then piles = piles + 1
    elseif t == df.building_type.Civzone then local k = df.civzone_type[b.type] or tostring(b.type); zones[k] = (zones[k] or 0) + 1
    elseif t == df.building_type.Bed then beds_placed = beds_placed + 1
    elseif t ~= df.building_type.Wagon then other = other + 1 end
  end
  return {workshops = ws, farm_plots = farms, farm_plots_underground = ug_farms, farm_plots_planted = planted,
          stockpiles = piles, zones = zones, beds_placed = beds_placed, other_buildings = other}
end)
try('layout', function()   -- what was built where: deterministic given the map (embark/build_fort.py picks sites from it)
  local r = {}
  for _, b in ipairs(df.global.world.buildings.all) do
    local t = b:getType()
    if t == df.building_type.Workshop or t == df.building_type.Furnace or t == df.building_type.FarmPlot then
      local k = t == df.building_type.FarmPlot and 'FarmPlot' or (t == df.building_type.Workshop and df.workshop_type or df.furnace_type)[b:getSubtype()]
      r[#r + 1] = ('%s@%d,%d,%d'):format(k, b.x1, b.y1, b.z)
    end
  end
  table.sort(r)
  return r
end)
try('orders', function()
  local n, left = 0, 0
  for _, wo in ipairs(df.global.world.manager_orders.all) do n = n + 1; left = left + wo.amount_left end
  return {n = n, amount_left = left}
end)
try('nobles', function()
  local ent = df.historical_entity.find(df.global.plotinfo.group_id)
  local r = {}
  for _, a in ipairs(ent.positions.assignments) do
    for _, p in ipairs(ent.positions.own) do
      if p.id == a.position_id and a.histfig2 ~= -1 then r[#r + 1] = p.code end
    end
  end
  table.sort(r)
  return r
end)
try('military', function()
  local sq, bur = 0, 0
  for _, s in ipairs(df.global.world.squads.all) do if s.entity_id == df.global.plotinfo.group_id then sq = sq + 1 end end
  bur = #df.global.plotinfo.burrows.list
  return {squads = sq, burrows = bur}
end)
try('plugins', function()   -- DFHack's `enable` listing: plugin state is saved with the fort
  local out, r = dfhack.run_command_silent('enable'), {}
  for _, p in ipairs({'autochop', 'autofarm', 'seedwatch', 'autobutcher', 'autolabor', 'autoclothing', 'nestboxes',
                       'autoslab', 'tailor', 'dwarfvet', 'suspendmanager'}) do
    if out:match('%f[%w%-]' .. p:gsub('%-', '%%-') .. ':%s+on') then r[#r + 1] = p end
  end
  return r
end)
try('events', function()
  local mig = 0
  for _, e in ipairs(df.global.timed_events) do if e.type == df.timed_event_type.Migrants then mig = mig + 1 end end
  local civ = df.historical_entity.find(df.global.plotinfo.civ_id)
  local st = civ and civ.activity_stats
  local rep = st and st.wealth.total or -1
  return {timed = #df.global.timed_events, migrants_pending = mig, reported_wealth = rep,
          report_population = st and st.population or -1, report_wave_idx = st and st.migrant_wave_idx or -1,
          wealth_total = df.global.plotinfo.tasks.wealth.total}
end)
try('map', function()
  local w
  for _, b in ipairs(df.global.world.buildings.all) do if df.building_wagonst:is_instance(b) then w = b end end
  -- dug (non-wall, non-hidden) tiles in a 61x61 box around the wagon, 1-3 levels below it: how much of the fort is
  -- underground (a stair + farm room is ~25 tiles); `outside` tiles (valley floors, river banks) don't count
  local dug = 0
  if w then
    for z = w.z - 3, w.z - 1 do
      for x = w.centerx - 30, w.centerx + 30 do
        for y = w.centery - 30, w.centery + 30 do
          local tt = dfhack.maps.getTileType(x, y, z)
          local fl = dfhack.maps.getTileFlags(x, y, z)
          if tt and fl and not fl.hidden and not fl.outside then
            local s = df.tiletype.attrs[tt].shape
            if s ~= df.tiletype_shape.WALL and s ~= df.tiletype_shape.EMPTY and s ~= df.tiletype_shape.NONE then dug = dug + 1 end
          end
        end
      end
    end
  end
  return {wagon = w and {w.centerx, w.centery, w.z} or nil, dug_below_surface = dug}
end)
print(json.encode(o, {pretty = false}))
