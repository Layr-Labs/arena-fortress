-- outcome.lua: outcome readers for docs/SUCCESS.md, shared by recorder.lua (one sample a day) and final_state.lua
-- (the end state). Scoring side only: nothing here is shown to the agent, and it never changes the game.
-- Loaded with dofile; returns a table of functions. Field paths are checked in game on DF 53.16 / DFHack 53.16-r2.
--   wellbeing(units)  stress distribution (personality.stress / longterm_stress), DFHack stress categories, breakdown
--                     states (unit.counters.soldier_mood), insanity (unit.mood), focus and unmet needs
--   housing(units)    placed beds, bedrooms owned by a citizen, dining seats, offices, meeting areas, temples/taverns
--   progress()        fortress_rank, progress_* counters, monarch arrival, created / exported / imported wealth, the
--                     positions citizens hold (dfhack.units.getNoblePositions), plotinfo.tasks counters, invasions
local M = {}

local function built(b) return b:getBuildStage() >= b:getMaxBuildStage() end

local function quant(xs, q)   -- nearest-rank quantile of an ascending list
  if #xs == 0 then return nil end
  local i = math.max(1, math.min(#xs, math.ceil(q * #xs)))
  return xs[i]
end

M.INSANE = {Melancholy = true, Raving = true, Berserk = true, Traumatized = true}   -- df.mood_type insanities
M.STRESS_LEVELS = {25000, 50000, 100000}   -- wiki Stress: 'stressed' / 'haggard' / 'harrowed' warnings (long-term)
M.FOCUS_DISTRACTED = 80                     -- current_focus <= 80% of undistracted_focus: "Distracted" or worse (wiki Personality need)
M.NEED_UNMET = -1000                        -- personality.needs[].focus_level at or below: the need is unmet

function M.citizens()
  local out = {}
  for _, u in ipairs(df.global.world.units.active) do
    if dfhack.units.isCitizen(u) then out[#out + 1] = u end
  end
  return out
end

-- wellbeing: stress quantiles (raw personality.stress: higher = more stressed; −100000..100000), long-term stress,
-- counts at or above the warning levels, DFHack's 0..6 category histogram (0 = most stressed), breakdown states
-- (soldier_mood Tantrum / Depressed / Oblivious / Enraged; MartialTrance is a combat trance, not a breakdown),
-- citizens in each insane mood, focus (current_focus / undistracted_focus) and unmet needs.
function M.wellbeing(units)
  local st, lt, cat = {}, {}, {0, 0, 0, 0, 0, 0, 0}
  local hi, lthi = {0, 0, 0}, {0, 0, 0}
  local brk, insane = {}, {}
  local focus, distracted, unmet, needs_n = {}, 0, 0, 0
  for _, u in ipairs(units) do
    local soul = u.status.current_soul
    local p = soul and soul.personality
    if p then
      st[#st + 1], lt[#lt + 1] = p.stress, p.longterm_stress
      for i, v in ipairs(M.STRESS_LEVELS) do
        if p.stress >= v then hi[i] = hi[i] + 1 end
        if p.longterm_stress >= v then lthi[i] = lthi[i] + 1 end
      end
      if p.undistracted_focus > 0 then
        local r = math.floor(100 * p.current_focus / p.undistracted_focus + 0.5)
        focus[#focus + 1] = r
        if r <= M.FOCUS_DISTRACTED then distracted = distracted + 1 end
      end
      for _, nd in ipairs(p.needs) do
        needs_n = needs_n + 1
        if nd.focus_level <= M.NEED_UNMET then unmet = unmet + 1 end
      end
    end
    local c = dfhack.units.getStressCategory(u)
    if c >= 0 and c <= 6 then cat[c + 1] = cat[c + 1] + 1 end
    local sm = df.soldier_mood_type[u.counters.soldier_mood]
    if sm and sm ~= 'None' and sm ~= 'MartialTrance' then brk[sm] = (brk[sm] or 0) + 1 end
    local m = df.mood_type[u.mood]
    if m and M.INSANE[m] then insane[m] = (insane[m] or 0) + 1 end
  end
  table.sort(st); table.sort(lt); table.sort(focus)
  local o = {stress = {min = st[1], med = quant(st, 0.5), p90 = quant(st, 0.9), max = st[#st]},
             lt_stress = {med = quant(lt, 0.5), p90 = quant(lt, 0.9), max = lt[#lt]},
             stress_ge = hi, lt_stress_ge = lthi, stress_cat = cat,
             focus = {min = focus[1], med = quant(focus, 0.5), distracted = distracted},
             needs = {n = needs_n, unmet = unmet}}
  if next(brk) then o.breakdown = brk end
  if next(insane) then o.insane = insane end
  return o
end

-- the citizen-relevant building/zone counts. Zones (civzones) list the buildings inside them in
-- contained_buildings; an owned bedroom is a Bedroom zone whose assigned_unit_id is a citizen.
function M.housing(units)
  local cit = {}
  for _, u in ipairs(units) do cit[u.id] = true end
  local o = {beds_placed = 0, bedrooms = 0, bedrooms_owned = 0, dining_zones = 0, dining_tables = 0,
             dining_chairs = 0, offices = 0, meeting_areas = 0}
  for _, b in ipairs(df.global.world.buildings.other.BED) do
    if built(b) then o.beds_placed = o.beds_placed + 1 end
  end
  local owners = {}
  for _, z in ipairs(df.global.world.buildings.other.ACTIVITY_ZONE) do
    local t = df.civzone_type[z.type]
    if t == 'Bedroom' then
      o.bedrooms = o.bedrooms + 1
      if z.assigned_unit_id ~= -1 and cit[z.assigned_unit_id] then owners[z.assigned_unit_id] = true end
    elseif t == 'DiningHall' then
      o.dining_zones = o.dining_zones + 1
      for _, b in ipairs(z.contained_buildings) do
        if built(b) then
          if df.building_tablest:is_instance(b) then o.dining_tables = o.dining_tables + 1
          elseif df.building_chairst:is_instance(b) then o.dining_chairs = o.dining_chairs + 1 end
        end
      end
    elseif t == 'Office' then o.offices = o.offices + 1
    elseif t == 'MeetingHall' then o.meeting_areas = o.meeting_areas + 1
    end
  end
  for _ in pairs(owners) do o.bedrooms_owned = o.bedrooms_owned + 1 end
  o.dining_seats = math.min(o.dining_tables, o.dining_chairs)
  -- locations (temple, tavern, library, hospital, guildhall) are abstract buildings of the player's site
  local site = df.world_site.find(df.global.plotinfo.site_id)
  local loc = {}
  if site then
    for _, ab in ipairs(site.buildings) do
      local t = df.abstract_building_type[ab:getType()] or '?'
      loc[t] = (loc[t] or 0) + 1
    end
  end
  if next(loc) then o.locations = loc end
  return o
end

-- progression and the fort's ledger: DF's own counters, no inference.
function M.progress(units)
  local pi = df.global.plotinfo
  local t, w = pi.tasks, pi.tasks.wealth
  local o = {fortress_rank = pi.fortress_rank, progress_population = pi.progress_population,
             progress_trade = pi.progress_trade, progress_production = pi.progress_production,
             king_arrived = pi.king_arrived, game_over = pi.game_over,
             wealth_created = w.weapons + w.armor + w.furniture + w.other + w.architecture + w.displayed,
             wealth_total = w.total, exported = w.exported, imported = w.imported, offered = w.offered,
             deaths_total = t.total_deaths, insanities_total = t.total_insanities, artifacts_total = t.num_artifacts,
             invaders_repelled = t.invaders_repelled, migrant_wave_idx = t.migrant_wave_idx}
  local nob = {}
  for _, u in ipairs(units or M.citizens()) do
    local np = dfhack.units.getNoblePositions(u)
    if np then for _, x in ipairs(np) do nob[#nob + 1] = x.position.code end end
  end
  table.sort(nob)
  o.positions = nob
  local inv = {n = 0, active = 0, siege = 0}
  for _, i in ipairs(pi.invasions.list) do
    inv.n = inv.n + 1
    if i.flags.active then inv.active = inv.active + 1 end
    if i.flags.siege then inv.siege = inv.siege + 1 end
  end
  o.invasions = inv
  return o
end

-- hand-off liabilities at H (docs/SUCCESS.md §7.1; research/community-saves-and-scenarios.md §5.2): crises left
-- for the next player. Report-only. Each count is cheap and read-only:
--   unburied_dead  corpses of the fort's own civ and race not inside a building (a coffin) (items.other.CORPSE)
--   ghosts         active units with flags3.ghostly (restless dead; the unit itself is dead)
--   stranded       citizens whose walkable group differs from the largest citizen group (warn-stranded's idea)
--   wounded        citizens whose health record needs healthcare (unit.health.flags.needs_healthcare; old healed
--                  wounds don't count); hospitals = Hospital zones (wounded_no_hospital when there are none)
--   moods_pending  citizens in a strange mood (Fey..Fell) whose mood job still lacks items (attached < required),
--                  with the smallest mood_timeout left (ticks; 0 = insanity)
--   hostiles       visible live hostile units; invaders = live active_invader units
function M.handoff(units)
  local pi = df.global.plotinfo
  local o = {unburied_dead = 0, ghosts = 0, stranded = 0, wounded = 0, hospitals = 0, moods_pending = 0,
             moods_missing_items = 0, hostiles = 0, invaders = 0}
  for _, it in ipairs(df.global.world.items.other.CORPSE) do
    local u = df.unit.find(it.unit_id)
    if u and u.civ_id == pi.civ_id and u.race == pi.race_id and not it.flags.in_building then
      o.unburied_dead = o.unburied_dead + 1
    end
  end
  for _, u in ipairs(df.global.world.units.active) do
    if u.flags3.ghostly then o.ghosts = o.ghosts + 1   -- a ghost is a dead unit back on the map (isDead true)
    elseif dfhack.units.isDanger(u) and not dfhack.units.isHidden(u) and not dfhack.units.isDead(u)
        and not dfhack.units.isCitizen(u) then
      o.hostiles = o.hostiles + 1
      if u.flags1.active_invader then o.invaders = o.invaders + 1 end
    end
  end
  local groups, best, bestn = {}, nil, 0
  for _, u in ipairs(units) do
    local g = dfhack.maps.getWalkableGroup(xyz2pos(dfhack.units.getPosition(u)))
    groups[u.id] = g
    if g and g ~= 0 then
      local n = 0
      for _, v in pairs(groups) do if v == g then n = n + 1 end end
      if n > bestn then best, bestn = g, n end
    end
  end
  for _, u in ipairs(units) do
    if best and groups[u.id] ~= best then o.stranded = o.stranded + 1 end
    if u.health and u.health.flags.needs_healthcare then o.wounded = o.wounded + 1 end
    local m = df.mood_type[u.mood]
    if m == 'Fey' or m == 'Secretive' or m == 'Possessed' or m == 'Macabre' or m == 'Fell' then
      o.moods_pending = o.moods_pending + 1
      local j = u.job.current_job
      if not j or #j.items < #j.job_items then o.moods_missing_items = o.moods_missing_items + 1 end
      local t = u.job.mood_timeout
      if t and (not o.mood_timeout_min or t < o.mood_timeout_min) then o.mood_timeout_min = t end
    end
  end
  for _, z in ipairs(df.global.world.buildings.other.ACTIVITY_ZONE) do
    if df.civzone_type[z.type] == 'Hospital' then o.hospitals = o.hospitals + 1 end
  end
  o.wounded_no_hospital = o.hospitals == 0 and o.wounded or 0
  o.total = o.unburied_dead + o.ghosts + o.stranded + o.wounded_no_hospital + o.moods_missing_items + o.hostiles
  return o
end

-- deaths at the fort since tick t0 from world history (history_event_hist_figure_diedst at plotinfo.site_id) whose
-- victim's historical figure is in `hfs` (a set of citizen hist_figure_ids): an audit independent of incidents
function M.history_deaths(t0, hfs)
  local site, out = df.global.plotinfo.site_id, {}
  local ev = df.global.world.history.events
  for i = #ev - 1, 0, -1 do
    local e = ev[i]
    local tick = e.year * 403200 + math.max(0, e.seconds)
    if tick < t0 then break end
    if df.history_event_hist_figure_diedst:is_instance(e) and e.site == site and hfs[e.victim_hf] then
      out[#out + 1] = {hf = e.victim_hf, tick = tick, cause = df.death_type[e.death_cause] or tostring(e.death_cause)}
    end
  end
  return out
end

return M
