-- fort_events.lua <cmd> [args] : population and event steps for embark/build_fort.py (task forts from a seed).
--   report <wealth>            the civ's caravan report as a caravan would leave it: reported wealth <wealth>, the fort's
--                              current population, no migrant wave since (scripted-y1's report: 3330, 19, 0). DF sizes a
--                              migrant wave by this report (scenarios/lua/migrant_surge.lua). A fresh embark has no
--                              report (activity_stats): it is created as a copy of the fort's own statistics, so every
--                              array has DF's sizes
--   wave <wealth>              report <wealth>, then queue a Migrants timed event now (they arrive within a day)
--   pending <season> <ticks>   queue a Migrants timed event at that season tick (10 game ticks each) if it is still ahead
--   clear_migrants             drop every pending Migrants event
--   stress <n> <stress> <longterm> <seed>   as scenarios/lua/stress.lua (the n citizens drawn with seed)
--   count                      print CITIZENS <n> <adults>
-- Measured on a fresh TEMPERATE_SOIL embark (seed 1000, 7 founders, spring of year 2, migrant_wave_idx 0): a wave at
-- reported wealth 10000 / 12000 / 15000 / 17000 / 19000 / 20000 / 30000 / 50000 gave 3 / 5 / 9 / 11 / 13 / 13 / 20 / 25
-- migrants, twice each where repeated (2026-10-14). A forced Migrants event without a report brings nobody, and
-- creating activity_stats from scratch (df.new without the copy) crashes DF at the next migrant check.
local a = {...}
local cmd = a[1]
local civ = df.historical_entity.find(df.global.plotinfo.civ_id)
local function citizens()
  local n, ad = 0, 0
  for _, u in ipairs(df.global.world.units.active) do
    if dfhack.units.isCitizen(u) then n = n + 1; if dfhack.units.isAdult(u) then ad = ad + 1 end end
  end
  return n, ad
end
local function report(w)
  if not civ.activity_stats then
    local s = df.entity_activity_statistics:new()
    s:assign(df.global.plotinfo.tasks)
    civ.activity_stats = s
  end
  local rw = civ.activity_stats.wealth
  rw.other, rw.total = math.max(0, rw.other + (w - rw.total)), w
end
local function fresh_report(w)   -- as if a caravan had just reported the fort home: its wealth, its population, and
  report(w)                      -- no migrant wave since (the report counts waves since it was made, migrant_wave_idx,
  local s = civ.activity_stats   -- and DF shrinks later waves by it: with 1 left over from the build's wave,
  local n = citizens()           -- migrant_surge.lua 100000 brought +7 instead of scripted-y1's +17; reset, +19)
  s.population, s.potential_soldiers, s.migrant_wave_idx = n, n, 0
end
local function queue(season, ticks)
  df.global.timed_events:insert('#', {new = true, type = df.timed_event_type.Migrants, season = season,
                                      season_ticks = ticks, entity = civ, feature_ind = -1})
end
if cmd == 'report' then
  fresh_report(tonumber(a[2]))
  print('REPORT ' .. civ.activity_stats.wealth.total)
elseif cmd == 'wave' then
  report(tonumber(a[2]))
  queue(df.global.cur_season, df.global.cur_season_tick)
  print(('WAVE wealth=%d citizens=%d'):format(civ.activity_stats.wealth.total, citizens()))
elseif cmd == 'pending' then
  local s, t = tonumber(a[2]), tonumber(a[3])
  if s > df.global.cur_season or (s == df.global.cur_season and t > df.global.cur_season_tick) then
    queue(s, t); print(('PENDING %d %d'):format(s, t))
  else
    print(('PENDING_PAST %d %d (now %d %d)'):format(s, t, df.global.cur_season, df.global.cur_season_tick))
  end
elseif cmd == 'clear_migrants' then
  local ev = df.global.timed_events
  for i = #ev - 1, 0, -1 do if ev[i].type == df.timed_event_type.Migrants then ev:erase(i) end end
  print('CLEARED')
elseif cmd == 'stress' then
  local n, s, l, seed = tonumber(a[2]), tonumber(a[3]), tonumber(a[4]), tonumber(a[5]) or 0
  local cit = {}
  for _, u in ipairs(df.global.world.units.active) do
    if dfhack.units.isCitizen(u) and dfhack.units.isAdult(u) and u.status.current_soul then cit[#cit + 1] = u end
  end
  table.sort(cit, function(x, y) return x.id < y.id end)
  local x = seed % 2147483647
  local function rnd(k) x = (x * 48271) % 2147483647; return x % k + 1 end
  for i = #cit, 2, -1 do local j = rnd(i); cit[i], cit[j] = cit[j], cit[i] end
  local ids = {}
  for i = 1, math.min(n, #cit) do
    local p = cit[i].status.current_soul.personality
    p.stress, p.longterm_stress = s, l
    ids[#ids + 1] = ('%d:%d'):format(cit[i].id, dfhack.units.getStressCategory(cit[i]))
  end
  print('STRESSED ' .. table.concat(ids, ' '))
elseif cmd == 'count' then
  print(('CITIZENS %d %d'):format(citizens()))
else
  qerror('usage: fort_events.lua report|wave|pending|clear_migrants|stress|count ...')
end
