-- advance.lua N [notrip] : unpause, re-pause after N game ticks. Generation-guarded so a
-- stale callback from an earlier (auto-paused) advance can never pause a later one.
--
-- Tripwires (BENCHMARK-v1 §2.4.2, HARNESS-PLAN 1.1): unless `notrip`, the game is checked every CHECK ticks and
-- pauses early when something happens that a player would want to react to. Only changes during this advance
-- count, so hostiles that were already visible (or already near) at the start don't stop every advance:
--   hostile_visible        a dangerous non-citizen became visible
--   hostile_approaching    a visible hostile closed CLOSE or more tiles on the nearest citizen since the advance began
--   hostile_near_citizens  a visible hostile came within NEAR tiles (same z +-3) of a citizen
--   citizen_died           fewer living citizens than at the start
--   invasion               an invasion became active (sieges have no announcement)
--   water_rising           revealed water/magma on the fortress levels (indoor tiles within 30 tiles of the wagon, the surface
--                          level and 8 below) grew by 50% and at least 50 units (checked every WATER_EVERY checks)
--   announcement:<TYPE>    one of STOP_TYPES was announced (moods, tantrums, deaths, arrivals, ambushes, ...)
-- The reason is stored in __adv_stop = {gen, reason, detail, abs_tick}; smoke.py reads it after the pause.
local args = {...}
local n = tonumber(args[1]) or 1200
local trip = args[2] ~= 'notrip'
local gen = (rawget(_G, '__adv_gen') or 0) + 1
rawset(_G, '__adv_gen', gen)
rawset(_G, '__adv_stop', nil)
local credit = rawget(_G, '__credit')   -- credit.lua: orders created before this point are the arm's
if credit then credit.before_advance() end

local CHECK, NEAR, CLOSE = 100, 30, 25
local WATER_EVERY, WATER_R, WATER_DOWN = 4, 30, 8
local STOP_TYPES = {}
for _, t in ipairs({'STRANGE_MOOD', 'BERSERK_CITIZEN', 'CITIZEN_TANTRUM', 'POSSESSED_TANTRUM', 'CITIZEN_DEATH',
                    'MIGRANT_ARRIVAL', 'MIGRANT_ARRIVAL_NAMED', 'D_MIGRANTS_ARRIVAL', 'D_MIGRANT_ARRIVAL',
                    'CARAVAN_ARRIVAL', 'FIRST_CARAVAN_ARRIVAL', 'DIPLOMAT_ARRIVAL', 'TRADE_DIPLOMAT_ARRIVAL',
                    'MONARCH_ARRIVAL', 'NOBLE_ARRIVAL', 'MEGABEAST_ARRIVAL', 'WEREBEAST_ARRIVAL', 'BEAST_AMBUSH',
                    'AMBUSH_DEFENDER', 'AMBUSH_RESIDENT', 'AMBUSH_THIEF', 'AMBUSH_SNATCHER', 'AMBUSH_AMBUSHER',
                    'AMBUSH_AMBUSHER_NATURE', 'AMBUSH_MISCHIEVOUS', 'AMBUSH_OTHER', 'CAVE_COLLAPSE'}) do
  local id = df.announcement_type[t]
  if id then STOP_TYPES[id] = t end
end

local function now() return df.global.cur_year * 403200 + df.global.cur_year_tick end

local function scan()
  local citizens, hostiles = {}, {}
  for _, u in ipairs(df.global.world.units.active) do
    if not dfhack.units.isDead(u) then
      if dfhack.units.isCitizen(u) then
        citizens[#citizens + 1] = u
      -- v2.2: visible = on a revealed tile and not sneaking (observe2.lua visible_unit); isHidden alone stopped
      -- advances on creatures in unexplored caverns and printed where they were
      elseif dfhack.units.isDanger(u) and dfhack.units.isVisible(u) and not dfhack.units.isHidden(u) then
        hostiles[#hostiles + 1] = u
      end
    end
  end
  local near, dist = {}, {}   -- dist: tiles to the nearest citizen (horizontal; z counts as distance too)
  for _, h in ipairs(hostiles) do
    local best = math.huge
    for _, c in ipairs(citizens) do
      local d = math.max(math.abs(h.pos.x - c.pos.x), math.abs(h.pos.y - c.pos.y), math.abs(h.pos.z - c.pos.z))
      if d < best then best = d end
      if math.abs(h.pos.z - c.pos.z) <= 3 and math.max(math.abs(h.pos.x - c.pos.x), math.abs(h.pos.y - c.pos.y)) <= NEAR then
        near[h.id] = true
      end
    end
    dist[h.id] = best
  end
  local seen = {}
  for _, h in ipairs(hostiles) do seen[h.id] = h end
  local inv = {}
  for _, i in ipairs(df.global.plotinfo.invasions.list) do if i.flags.active then inv[i.id] = true end end
  return #citizens, seen, near, inv, dist
end

local function water_total()
  local w
  for _, b in ipairs(df.global.world.buildings.all) do if df.building_wagonst:is_instance(b) then w = b break end end
  if not w then return 0 end
  local total = 0
  for z = w.z - WATER_DOWN, w.z do   -- indoor tiles only (below): rivers and ponds, even on lower ground, are outside
    for x = w.centerx - WATER_R, w.centerx + WATER_R do
      for y = w.centery - WATER_R, w.centery + WATER_R do
        local d = dfhack.maps.getTileFlags(x, y, z)
        if d and d.flow_size > 0 and not d.hidden and not d.outside then total = total + d.flow_size end   -- indoors only
      end
    end
  end
  return total
end

local function last_report_id()
  local rep = df.global.world.status.reports
  return #rep > 0 and rep[#rep - 1].id or -1
end

df.global.pause_state = false
dfhack.timeout(n, 'ticks', function()
  if rawget(_G, '__adv_gen') == gen then df.global.pause_state = true end
end)

if trip then
  local c0, seen0, near0, inv0, dist0 = scan()
  local rep0, t0 = last_report_id(), now()
  local water0, nchecks = water_total(), 0
  local function stop(reason, detail)
    df.global.pause_state = true
    rawset(_G, '__adv_stop', {gen = gen, reason = reason, detail = detail, abs_tick = now(), after_ticks = now() - t0})
  end
  local function check()
    if rawget(_G, '__adv_gen') ~= gen or now() - t0 >= n then return end
    if df.global.pause_state then   -- paused by DF or a popup: look again shortly, don't stop
      dfhack.timeout(CHECK, 'ticks', check); return
    end
    local rep = df.global.world.status.reports
    for i = #rep - 1, 0, -1 do
      local r = rep[i]
      if r.id <= rep0 then break end
      if STOP_TYPES[r.type] then
        return stop('announcement:' .. STOP_TYPES[r.type], dfhack.df2utf(r.text):gsub('%[[^%]]*%]', ''):sub(1, 160))
      end
    end
    local c, seen, near, inv, dist = scan()
    if c < c0 then return stop('citizen_died', ('%d citizens, was %d'):format(c, c0)) end
    for id, u in pairs(seen) do
      if not seen0[id] then
        return stop('hostile_visible', ('%s at %d,%d,%d'):format(dfhack.units.getReadableName(u), u.pos.x, u.pos.y, u.pos.z))
      end
    end
    for id, d in pairs(dist) do
      if dist0[id] and dist0[id] < math.huge and d <= dist0[id] - CLOSE then
        local u = seen[id]
        return stop('hostile_approaching', ('%s at %d,%d,%d, %d tiles from the nearest citizen (was %d)'):format(
          dfhack.units.getReadableName(u), u.pos.x, u.pos.y, u.pos.z, d, dist0[id]))
      end
    end
    for id in pairs(near) do
      if not near0[id] then
        local u = seen[id]
        return stop('hostile_near_citizens', ('%s at %d,%d,%d, within %d tiles of a citizen'):format(
          dfhack.units.getReadableName(u), u.pos.x, u.pos.y, u.pos.z, NEAR))
      end
    end
    for id in pairs(inv) do
      if not inv0[id] then return stop('invasion', 'invasion ' .. id .. ' became active') end
    end
    nchecks = nchecks + 1
    if nchecks % WATER_EVERY == 0 then
      local wt = water_total()
      if wt - water0 >= 50 and wt >= water0 * 1.5 then
        return stop('water_rising', ('water on the fortress levels %d, was %d'):format(wt, water0))
      end
    end
    dfhack.timeout(CHECK, 'ticks', check)
  end
  dfhack.timeout(CHECK, 'ticks', check)
end
print('gen ' .. gen)
