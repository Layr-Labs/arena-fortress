-- recorder.lua start|dump : in-game daily sampler, independent of how often the harness decides.
--   start  clear state and record one sample now + every 1200 game ticks (generation-guarded, like advance.lua)
--   dump   print JSON {samples=[...], events={TYPE={n, first_tick, first_text}}}
-- Per sample: drink, food, citizens, hostiles (visible, alive), stressed (citizens at stress category <= 1),
-- min_stress (0 = most stressed .. 6), in_mood (citizens in a strange mood or worse), idle citizens, and
-- produced_value / credited_value when credit.lua is running (start it first).
-- events: every announcement report since start, counted by df.announcement_type, so failure modes
-- (migrants, sieges, moods, tantrums, deaths, cave-ins, ...) can be timed without parsing text.
-- Lab-task fields (BENCHMARK-v1 §2.1; scoring side, never shown to the agent):
--   ev     per-sample announcement counts by type since the previous sample (the day's event histogram)
--   moods  [{unit_id, mood}] for citizens with a mood (strange mood, or Melancholy/Raving/Berserk/... insanity)
--   beds_items / beds_placed  bed items (placed ones included) / bed buildings a dwarf has installed
--   S0 / S  final_state.lua at `start` (before the scenario setup) and at `dump` (the end of the run)
-- Outcome fields (docs/SUCCESS.md; outcome.lua readers, scoring side only):
--   wb     wellbeing: stress min/med/p90/max, long-term stress med/p90/max, counts at >= 25k/50k/100k, stress
--          category histogram, breakdown states (Tantrum/Depressed/Oblivious/Enraged), insane moods, focus, unmet needs
--   home   beds_placed, bedrooms (owned by a citizen), dining tables/chairs/seats, offices, meeting areas, locations
--   prog   fortress_rank, progress_*, king_arrived, created/exported/imported wealth, positions held by citizens,
--          plotinfo.tasks deaths/insanities/artifacts/invaders_repelled, invasions (n, active, siege)
--   pop    citizens tracked by id since `start`: arrived (migrants), born, died, insane, left (cumulative)
--   cit_log (dump only) per-id {first_tick, kind = start|migrant|born, gone_tick, gone = died|insane|left, hf}
--   hist_deaths (dump only) world-history deaths at the site since start of citizens in the ledger (outcome.lua)
-- State lives in the Lua state, which persists across dfhack-run calls but not across a DF restart.
local json = require('json')
local cmd = ({...})[1]

local function now() return df.global.cur_year * 403200 + df.global.cur_year_tick end

local function final_state()
  local src = debug.getinfo(1, 'S').source:gsub('^@', '')
  local dir = src:match('^(.*)/[^/]*$') or '.'
  rawset(_G, '__final_state_module', true)   -- final_state.lua then returns its state() function instead of printing
  local ok, f = pcall(dofile, dir .. '/final_state.lua')
  rawset(_G, '__final_state_module', nil)
  if not ok or type(f) ~= 'function' then return {error = tostring(f)} end
  local ok2, s = pcall(f)
  return ok2 and s or {error = tostring(s)}
end

local function outcome()
  local st = rawget(_G, '__rec_state')
  if st and st.outcome then return st.outcome end
  local src = debug.getinfo(1, 'S').source:gsub('^@', '')
  local dir = src:match('^(.*)/[^/]*$') or '.'
  local ok, m = pcall(dofile, dir .. '/outcome.lua')
  if not ok or type(m) ~= 'table' then return nil end
  if st then st.outcome = m end
  return m
end

-- citizen ledger: who was here at start, who arrived (migrants) or was born, and who died, went insane or left.
-- A citizen missing from this sample is classified by its unit: dead, insane mood, else left (e.g. a departed
-- noble or a unit that stopped being a citizen). One that comes back is un-gone.
local function track(st, units, M, t)
  local log, here = st.cit_log, {}
  for _, u in ipairs(units) do
    here[u.id] = true
    local e = log[u.id]
    if not e then
      local born = u.birth_year * 403200 + u.birth_time
      local kind = st.started and ((born >= st.t0) and 'born' or 'migrant') or 'start'
      log[u.id] = {first_tick = t, kind = kind, hf = u.hist_figure_id}
    elseif e.gone then
      e.gone, e.gone_tick = nil, nil
    end
  end
  local pop = {arrived = 0, born = 0, died = 0, insane = 0, left = 0}
  for id, e in pairs(log) do
    if e.gone == 'insane' then   -- an insane citizen who dies later (killed while berserk) is a death
      local u = df.unit.find(id)
      if not u or dfhack.units.isDead(u) then e.gone, e.gone_tick = 'died', t end
    end
    if not here[id] and not e.gone then
      local u = df.unit.find(id)
      if not u or dfhack.units.isDead(u) then e.gone = 'died'
      elseif M and M.INSANE[df.mood_type[u.mood] or ''] then e.gone = 'insane'
      else e.gone = 'left' end
      e.gone_tick = t
    end
    if e.kind == 'migrant' then pop.arrived = pop.arrived + 1 elseif e.kind == 'born' then pop.born = pop.born + 1 end
    if e.gone then pop[e.gone] = pop[e.gone] + 1 end
  end
  st.started = true
  return pop
end

local function scan_reports()
  local st = rawget(_G, '__rec_state')
  local rep = df.global.world.status.reports
  for i = 0, #rep - 1 do
    local r = rep[i]
    if r.id > st.last_report then
      st.last_report = r.id
      local t = df.announcement_type[r.type] or tostring(r.type)
      local e = st.events[t]
      if not e then
        e = {n = 0, first_tick = r.year * 403200 + r.time, first_text = dfhack.df2utf(r.text):gsub('%[[^%]]*%]', ''):sub(1, 160)}
        st.events[t] = e
      end
      e.n = e.n + 1
      st.ev[t] = (st.ev[t] or 0) + 1
    end
  end
end

-- score_version 6: food = edible items only. ANY_GOOD_FOOD also holds seeds (including seeds planted in farm plots) and
-- empty cloth bags, about 20 of 66 "food" on MY1 fort 2001 (runs/s0-compute-2026-10-23), so recorded food never reached
-- 0 while dwarves starved. Raw fish (FISH_RAW) needs a fishery before anyone can eat it.
local EDIBLE = {}
for _, t in ipairs({'FOOD', 'MEAT', 'FISH', 'CHEESE', 'EGG', 'PLANT', 'PLANT_GROWTH'}) do EDIBLE[df.item_type[t]] = true end
local function edible(it) return EDIBLE[it:getType()] and not it.flags.rotten end

local function sample()
  local st = rawget(_G, '__rec_state')
  local other = df.global.world.items.other
  local d, f = 0, 0
  for _, it in ipairs(other.DRINK) do d = d + it.stack_size end
  for _, it in ipairs(other.ANY_GOOD_FOOD) do if edible(it) then f = f + it.stack_size end end
  scan_reports()   -- announcements up to now belong to the previous sample's day
  local ev = st.ev
  st.ev = {}
  local c, stressed, min_stress, mood, idle, hostile = 0, 0, 6, 0, 0, 0
  local moods = {}
  for _, u in ipairs(df.global.world.units.active) do
    if dfhack.units.isCitizen(u) then
      c = c + 1
      local sc = dfhack.units.getStressCategory(u)
      if sc <= 1 then stressed = stressed + 1 end
      if sc < min_stress then min_stress = sc end
      if u.mood ~= -1 then
        mood = mood + 1
        moods[#moods + 1] = {unit_id = u.id, mood = df.mood_type[u.mood] or tostring(u.mood)}
      end
      if not u.job.current_job then idle = idle + 1 end
    elseif dfhack.units.isDanger(u) and not dfhack.units.isHidden(u) and not dfhack.units.isDead(u) then
      hostile = hostile + 1
    end
  end
  local beds_placed = 0
  for _, b in ipairs(df.global.world.buildings.other.BED) do
    if b:getBuildStage() >= b:getMaxBuildStage() then beds_placed = beds_placed + 1 end
  end
  local smp = {abs_tick = now(), drink = d, food = f, citizens = c, stressed = stressed,
               min_stress = min_stress, in_mood = mood, idle = idle, hostiles = hostile,
               beds_items = #other.BED, beds_placed = beds_placed}
  if next(ev) then smp.ev = ev end
  if #moods > 0 then smp.moods = moods end
  local M = outcome()
  if M then
    local units = M.citizens()
    local ok, r = pcall(function()
      return {wb = M.wellbeing(units), home = M.housing(units), prog = M.progress(units)}
    end)
    if ok then
      smp.wb, smp.home, smp.prog = r.wb, r.home, r.prog
    else
      smp.outcome_error = tostring(r):sub(1, 200)
    end
    smp.pop = track(st, units, M, smp.abs_tick)
  end
  local credit = rawget(_G, '__credit')   -- credit.lua, if started: running produced/credited value
  if credit then
    local t = credit.totals()
    smp.produced_value, smp.credited_value = t.produced, t.credited
  end
  st.samples[#st.samples + 1] = smp
end

if cmd == 'start' then
  local gen = (rawget(_G, '__rec_gen') or 0) + 1
  rawset(_G, '__rec_gen', gen)
  local rep = df.global.world.status.reports
  rawset(_G, '__rec_state', {samples = {}, events = {}, ev = {}, last_report = #rep > 0 and rep[#rep - 1].id or -1,
                              S0 = final_state(), cit_log = {}, t0 = now()})
  local function tick()
    if rawget(_G, '__rec_gen') ~= gen then return end
    sample()
    dfhack.timeout(1200, 'ticks', tick)
  end
  tick()
  print(json.encode({ok = true, gen = gen}))
elseif cmd == 'dump' then
  local st = rawget(_G, '__rec_state')
  if st then scan_reports() end
  local log = {}
  local hfs = {}
  if st then for id, e in pairs(st.cit_log or {}) do
    log[#log + 1] = {id = id, first_tick = e.first_tick, kind = e.kind, gone = e.gone, gone_tick = e.gone_tick, hf = e.hf}
    if e.hf and e.hf ~= -1 then hfs[e.hf] = true end
  end end
  table.sort(log, function(a, b) return a.id < b.id end)
  local M = st and outcome()
  local hd = nil
  if M then local ok, r = pcall(M.history_deaths, st.t0, hfs); hd = ok and r or {error = tostring(r)} end
  print(json.encode(st and {samples = st.samples, events = st.events, S0 = st.S0, S = final_state(), cit_log = log,
                                    hist_deaths = hd}
                    or {samples = {}, events = {}}))
else
  qerror('usage: recorder.lua start|dump')
end
