-- final_state.lua: fort state for lab-task predicates (BENCHMARK-v1 §2.1, symbols S0 / S). Read-only; prints JSON.
-- recorder.lua also loads this file and keeps S0 (at `recorder.lua start`, before the scenario setup) and S (at
-- `dump`, the end of the run) in the daily file, so smoke.py needs no change. Scoring side only: the agent never
-- sees it.
--   workshops / farm plots, placed furniture (built vs planned), activity zones by type with the furniture inside,
--   bed items, num_artifacts, total_insanities, wealth exported/imported, per-citizen stress and mood, squads.
--   Outcome fields (docs/SUCCESS.md, outcome.lua): wb (wellbeing), home (housing), prog (rank, wealth, positions,
--   counters, invasions), invasions (one row per plotinfo.invasions entry), per-citizen focus / unmet needs / positions.
local json = require('json')

local function outcome()
  local src = debug.getinfo(1, 'S').source:gsub('^@', '')
  local dir = src:match('^(.*)/[^/]*$') or '.'
  local ok, m = pcall(dofile, dir .. '/outcome.lua')
  return ok and type(m) == 'table' and m or nil
end

local function built(b) return b:getBuildStage() >= b:getMaxBuildStage() end

local function state()
  local o = {}
  local ws = {}
  for _, b in ipairs(df.global.world.buildings.all) do
    if df.building_workshopst:is_instance(b) or df.building_furnacest:is_instance(b) then
      local t = df.building_workshopst:is_instance(b) and df.workshop_type[b.type] or df.furnace_type[b.type]
      ws[#ws + 1] = {id = b.id, type = t, built = built(b)}
    end
  end
  o.workshops = ws
  local farms = {}
  for _, b in ipairs(df.global.world.buildings.other.FARM_PLOT) do
    local planted = 0   -- seeds or crops in the plot (observe2.lua's seeds_or_crops_in_plot), for LT02
    for _, ci in ipairs(b.contained_items) do
      if df.item_plantst:is_instance(ci.item) or df.item_seedsst:is_instance(ci.item) then planted = planted + 1 end
    end
    farms[#farms + 1] = {id = b.id, built = built(b), z = b.z, planted = planted,
                         subterranean = dfhack.maps.getTileFlags(b.centerx, b.centery, b.z).subterranean}
  end
  o.farm_plots = farms
  -- placed furniture: buildings.other.<TYPE>; `built` = a dwarf has installed it, `planned` = designated only
  local furn = {}
  for _, k in ipairs({'BED', 'TABLE', 'CHAIR', 'DOOR', 'BOX', 'CABINET', 'COFFIN', 'STATUE'}) do
    local n, p = 0, 0
    for _, b in ipairs(df.global.world.buildings.other[k] or {}) do
      if built(b) then n = n + 1 else p = p + 1 end
    end
    furn[k] = {built = n, planned = p}
  end
  o.furniture = furn
  local items = {}
  for _, k in ipairs({'BED', 'TABLE', 'CHAIR'}) do
    local n, free = 0, 0
    for _, it in ipairs(df.global.world.items.other[k]) do
      n = n + 1
      if not (it.flags.in_building or it.flags.forbid or it.flags.in_job or it.flags.construction) then free = free + 1 end
    end
    items[k] = {total = n, free = free}
  end
  o.items = items
  -- zones: type, size, and the built furniture whose tile is inside the zone's box
  local zones = {}
  for _, z in ipairs(df.global.world.buildings.other.ACTIVITY_ZONE) do
    local c = {}
    for _, k in ipairs({'BED', 'TABLE', 'CHAIR'}) do
      local n = 0
      for _, b in ipairs(df.global.world.buildings.other[k]) do
        if built(b) and b.z == z.z and b.centerx >= z.x1 and b.centerx <= z.x2 and b.centery >= z.y1
            and b.centery <= z.y2 then n = n + 1 end
      end
      c[k] = n
    end
    zones[#zones + 1] = {id = z.id, type = df.civzone_type[z.type] or tostring(z.type), x1 = z.x1, y1 = z.y1,
                         x2 = z.x2, y2 = z.y2, z = z.z, contains = c}
  end
  o.zones = zones
  local t = df.global.plotinfo.tasks
  o.num_artifacts, o.total_insanities, o.total_deaths = t.num_artifacts, t.total_insanities, t.total_deaths
  o.wealth = {total = t.wealth.total, exported = t.wealth.exported, imported = t.wealth.imported}
  local cit = {}
  for _, u in ipairs(df.global.world.units.active) do
    if dfhack.units.isCitizen(u) then
      local s = u.status.current_soul
      local unmet, pos = 0, {}
      if s then for _, nd in ipairs(s.personality.needs) do if nd.focus_level <= -1000 then unmet = unmet + 1 end end end
      for _, x in ipairs(dfhack.units.getNoblePositions(u) or {}) do pos[#pos + 1] = x.position.code end
      cit[#cit + 1] = {id = u.id, stress = s and s.personality.stress or nil,
                       longterm_stress = s and s.personality.longterm_stress or nil,
                       stress_category = dfhack.units.getStressCategory(u),
                       mood = df.mood_type[u.mood] or tostring(u.mood),
                       soldier_mood = df.soldier_mood_type[u.counters.soldier_mood],
                       focus = s and s.personality.undistracted_focus > 0
                               and math.floor(100 * s.personality.current_focus / s.personality.undistracted_focus + 0.5) or nil,
                       needs_unmet = unmet, positions = #pos > 0 and pos or nil,
                       age = math.floor(dfhack.units.getAge(u) or 0)}
    end
  end
  o.citizens = cit
  local sq = 0
  for _, s in ipairs(df.global.world.squads.all) do
    if s.entity_id == df.global.plotinfo.group_id then sq = sq + 1 end
  end
  o.squads = sq
  local M = outcome()
  if M then
    local units = M.citizens()
    local ok, err = pcall(function() o.wb, o.home, o.prog = M.wellbeing(units), M.housing(units), M.progress(units) end)
    if not ok then o.outcome_error = tostring(err):sub(1, 200) end
    ok, err = pcall(function() o.handoff = M.handoff(units) end)
    if not ok then o.outcome_error = tostring(err):sub(1, 200) end
  end
  local inv = {}
  for _, i in ipairs(df.global.plotinfo.invasions.list) do
    inv[#inv + 1] = {id = i.id, civ_id = i.civ_id, active = i.flags.active, siege = i.flags.siege,
                     undead = i.flags.undead_source, size = i.size, mission = i.mission, created_year = i.created_year}
  end
  o.invasions = inv
  o.abs_tick = df.global.cur_year * 403200 + df.global.cur_year_tick
  return o
end

if rawget(_G, '__final_state_module') then return state end   -- loaded by recorder.lua
print(json.encode(state()))
