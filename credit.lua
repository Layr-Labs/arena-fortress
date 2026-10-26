-- credit.lua start [ambient] | dump : agent-credited production (research/credited-production.md).
--   start [ambient]  clear state and hook eventful JOB_STARTED + ITEM_CREATED (every tick). `ambient` is a
--                    comma list of order-creating automation already on at run start (smoke.py fills it in);
--                    if it is non-empty, orders created while time runs are not credited to the arm.
--   dump             print JSON totals (produced / credited / raw / placed, by category) and diagnostics.
-- An item counts as PRODUCED when it is created during the run by a job held by a workshop or furnace, and is not
-- a raw material. It is CREDITED when that job came from a manager order the arm created during the run, or ran at
-- a workshop/furnace built during the run (only arm actions place buildings). Each item is counted once, at its
-- value when created (dfhack.items.getValue). Placing a built item as furniture creates no item, so it adds
-- nothing. State lives in the Lua state like recorder.lua (persists across dfhack-run calls, not a DF restart);
-- handlers are generation-guarded so a restart of the recorder never double counts.
local json = require('json')
local eventful = require('plugins.eventful')
local cmd, arg = ...

local KEY = 'yukon_credit'
local function now() return df.global.cur_year * 403200 + df.global.cur_year_tick end

local T = df.item_type
local function set(names) local s = {} for _, n in ipairs(names) do if T[n] then s[T[n]] = true end end return s end
-- gathered, felled, mined, harvested or butchered: not production (they reach the score once processed)
local RAW_TYPES = set{'WOOD', 'BOULDER', 'ROUGH', 'PLANT', 'PLANT_GROWTH', 'SEEDS', 'MEAT', 'FISH_RAW', 'CORPSE',
                      'CORPSEPIECE', 'REMAINS', 'VERMIN', 'PET', 'EGG'}
local RAW_JOBS = {}
for _, n in ipairs{'ButcherAnimal', 'MilkCreature', 'ShearCreature', 'FellTree', 'GatherPlants', 'HarvestPlot',
                   'Fish', 'CatchLiveFish', 'Hunt', 'CollectSand', 'CollectClay', 'ExtractFromRawFish',
                   'ExtractFromLandAnimal', 'ExtractFromPlants'} do
  if df.job_type[n] then RAW_JOBS[df.job_type[n]] = true end
end
local SKIP_JOBS = {}   -- held by a building but never make anything (a split stack must not be "produced" by them)
for _, n in ipairs{'ConstructBuilding', 'DestroyBuilding'} do SKIP_JOBS[df.job_type[n]] = true end
local CAT = {}
local function cat(c, names) for _, n in ipairs(names) do if T[n] then CAT[T[n]] = c end end end
cat('furniture', {'BED', 'TABLE', 'CHAIR', 'DOOR', 'CABINET', 'BOX', 'ARMORSTAND', 'WEAPONRACK', 'STATUE', 'COFFIN',
                  'HATCH_COVER', 'GRATE', 'FLOODGATE', 'WINDOW', 'QUERN', 'MILLSTONE', 'SLAB', 'TRACTION_BENCH',
                  'BOOKCASE', 'PEDESTAL', 'DISPLAY_CASE', 'CAGE', 'BARREL', 'BIN', 'BUCKET', 'ANIMALTRAP', 'CHAIN'})
cat('crafts', {'FIGURINE', 'AMULET', 'SCEPTER', 'CROWN', 'RING', 'EARRING', 'BRACELET', 'GEM', 'SMALLGEM', 'TOTEM',
               'INSTRUMENT', 'TOY', 'GOBLET', 'BOOK'})
cat('food', {'FOOD', 'FISH', 'CHEESE'})
cat('drink', {'DRINK'})
cat('weapons_armor', {'WEAPON', 'AMMO', 'ARMOR', 'SHOES', 'SHIELD', 'HELM', 'GLOVES', 'PANTS', 'TRAPCOMP', 'SIEGEAMMO'})
local CATS = {'furniture', 'crafts', 'food', 'drink', 'weapons_armor', 'artifact', 'other'}

local function st() return rawget(_G, '__credit') end

local function holder(job)
  for _, r in ipairs(job.general_refs) do
    if df.general_ref_building_holderst:is_instance(r) then return r.building_id end
  end
end
local function worker(job)
  for _, r in ipairs(job.general_refs) do
    if df.general_ref_unit_workerst:is_instance(r) then return r.unit_id end
  end
end

local function log(s, e)
  local l = s.log
  l[#l + 1] = e
  if #l > 200 then table.remove(l, 1) end
end

-- A job's products appear on its workshop's tiles, where its worker stands, in the tick it finishes. So the
-- producer of an item that appears on a workshop/furnace is one of the jobs recently STARTED (given a worker)
-- there: the one whose worker is the item's maker (crafted items record it), else the one whose worker stands on
-- the item's tile, else the latest. Several dwarves can hold jobs at one workshop while they fetch materials, so
-- "the latest" alone misattributed 2 of 27 items in a 30-day scripted run. (eventful's JOB_COMPLETED is not used:
-- in a 2026-10-07 test it reported 3 of 7 finished carpenter jobs; JOB_STARTED and ITEM_CREATED compare state.)
local function workshop(bid)
  local b = bid and df.building.find(bid)
  if b and (df.building_workshopst:is_instance(b) or df.building_furnacest:is_instance(b)) then return b end
end

local function on_start(s, job)
  local bid = holder(job)
  if not bid or SKIP_JOBS[job.job_type] or not workshop(bid) then return end
  local wid = worker(job)
  local u = wid and df.unit.find(wid)
  s.jobs_started = s.jobs_started + 1
  local l = s.started[bid] or {}
  s.started[bid] = l
  l[#l + 1] = {t = now(), o = job.order_id, j = job.job_type, hf = u and u.hist_figure_id or -2, u = wid, id = job.id}
  if #l > 8 then table.remove(l, 1) end
  log(s, {ev = 'start', t = now(), j = df.job_type[job.job_type], b = bid, o = job.order_id, id = job.id})
end

local function on_item(s, id)
  if id < s.item0 then return end
  local it = df.item.find(id)
  if not it then return end
  local ty = it:getType()
  local v = dfhack.items.getValue(it)
  s.items_new = s.items_new + 1
  local x, y, z = dfhack.items.getPosition(it)
  local b = x and dfhack.buildings.findAtTile(xyz2pos(x, y, z))
  local cands = b and workshop(b.id) and s.started[b.id]
  local maker = it.getMaker and it:getMaker() or -1
  local match, how
  if cands and #cands > 0 then
    for i = #cands, 1, -1 do
      if maker ~= -1 and cands[i].hf == maker then match, how = cands[i], 'maker' break end
    end
    if not match then
      for i = #cands, 1, -1 do
        local u = cands[i].u and df.unit.find(cands[i].u)
        if u and u.pos.x == x and u.pos.y == y and u.pos.z == z then match, how = cands[i], 'worker_tile' break end
      end
    end
    if not match then match, how = cands[#cands], 'latest' end
    s.match_how[how] = (s.match_how[how] or 0) + 1
    if maker ~= -1 and maker ~= match.hf then s.maker_mismatch = s.maker_mismatch + 1 end
  end
  if not RAW_TYPES[ty] then
    log(s, {ev = 'item', t = now(), id = id, ty = df.item_type[ty], v = v, b = b and b.id, maker = maker,
            job = match and match.id, how = how})
  end
  if RAW_TYPES[ty] or (match and RAW_JOBS[match.j]) then
    s.raw_value = s.raw_value + v; s.raw_n = s.raw_n + 1
    return
  end
  if not match then
    s.unmatched_n = s.unmatched_n + 1; s.unmatched_value = s.unmatched_value + v
    return
  end
  local c = it.flags.artifact and 'artifact' or CAT[ty] or 'other'
  s.items[id] = {v = v, c = c, o = match.o, b = b.id, j = df.job_type[match.j], ty = df.item_type[ty],
                 stack = it.stack_size, t = now()}   -- stack: consumables are capped in units (BENCHMARK-v1 §3.4);
                                                    -- t: creation tick, for in-window clauses (LT01, v2)
end

-- an order is the arm's if it was created during the run outside a time advance (arm actions happen while paused),
-- or during an advance (by automation) when no order-creating automation was already on at run start
local function order_credited(s, o)
  if o < 0 or o < s.ord0 then return false end
  local auto = s.auto_orders[o] or (s.advancing and o >= s.last_ord)
  return not auto or s.ambient == ''
end

local function totals(s)
  local p, c = {}, {}
  for _, k in ipairs(CATS) do p[k] = 0; c[k] = 0 end
  local P, C, placed, placed_c, n, nc = 0, 0, 0, 0, 0, 0
  for id, r in pairs(s.items) do
    p[r.c] = p[r.c] + r.v; P = P + r.v; n = n + 1
    local cr = order_credited(s, r.o) or r.b >= s.bld0
    if cr then c[r.c] = c[r.c] + r.v; C = C + r.v; nc = nc + 1 end
    local it = df.item.find(id)
    if it and it.flags.in_building then
      placed = placed + r.v
      if cr then placed_c = placed_c + r.v end
    end
  end
  return {produced = P, credited = C, produced_n = n, credited_n = nc, produced_by_category = p,
          credited_by_category = c, placed_value = placed, placed_credited_value = placed_c,
          raw_value = s.raw_value, raw_n = s.raw_n}
end

local function guard(fn)
  return function(...)
    local s = st()
    if not s or s.gen ~= rawget(_G, '__credit_gen') then return end
    local c0 = os.clock()
    local ok, err = pcall(fn, s, ...)
    s.hook_cpu = s.hook_cpu + (os.clock() - c0)
    if not ok then s.errors = s.errors + 1; s.last_error = tostring(err):sub(1, 200) end
  end
end

if cmd == 'start' then
  local gen = (rawget(_G, '__credit_gen') or 0) + 1
  rawset(_G, '__credit_gen', gen)
  local mo = df.global.world.manager_orders
  local s = {gen = gen, start_tick = now(), item0 = df.global.item_next_id, bld0 = df.global.building_next_id,
             ord0 = mo.manager_order_next_id, last_ord = mo.manager_order_next_id, auto_orders = {},
             advancing = false, ambient = arg or '', started = {}, match_how = {}, items = {}, jobs_started = 0, maker_mismatch = 0, items_new = 0,
             raw_value = 0, raw_n = 0, unmatched_n = 0, unmatched_value = 0, hook_cpu = 0, errors = 0,
             advances = 0, log = {}}
  -- advance.lua calls before_advance just before it unpauses; score.lua calls after_advance once time has stopped
  s.before_advance = function()
    s.last_ord = mo.manager_order_next_id   -- everything up to here was created by the arm, while paused
    s.advancing = true; s.advances = s.advances + 1
  end
  s.after_advance = function()
    if not s.advancing or not df.global.pause_state then return end
    for o = s.last_ord, mo.manager_order_next_id - 1 do s.auto_orders[o] = true end
    s.last_ord = mo.manager_order_next_id
    s.advancing = false
  end
  s.totals = function() return totals(s) end
  rawset(_G, '__credit', s)
  -- jobs already being worked at run start (a snapshot): their products are produced, not credited by order/building
  local l = df.global.world.jobs.list.next
  while l do
    if l.item and dfhack.job.getWorker(l.item) then guard(on_start)(l.item) end
    l = l.next
  end
  eventful.enableEvent(eventful.eventType.JOB_STARTED, 1)
  eventful.enableEvent(eventful.eventType.ITEM_CREATED, 1)
  eventful.onJobStarted[KEY] = guard(on_start)
  eventful.onItemCreated[KEY] = guard(on_item)
  print(json.encode({ok = true, gen = gen, item0 = s.item0, bld0 = s.bld0, ord0 = s.ord0, ambient = s.ambient}))
elseif cmd == 'dump' then
  local s = st()
  if not s then print(json.encode({ok = false, error = 'not started'})) return end
  local o = totals(s)
  local arm, auto = 0, 0
  for id = s.ord0, df.global.world.manager_orders.manager_order_next_id - 1 do
    if s.auto_orders[id] then auto = auto + 1 else arm = arm + 1 end
  end
  o.ok = true
  o.meta = {orders_arm = arm, orders_auto = auto, ambient = s.ambient, ord0 = s.ord0, bld0 = s.bld0, item0 = s.item0,
            buildings_built = df.global.building_next_id - s.bld0, jobs_started = s.jobs_started, maker_mismatch = s.maker_mismatch, match_how = s.match_how,
            items_new = s.items_new, unmatched_n = s.unmatched_n, unmatched_value = s.unmatched_value,
            hook_cpu_s = s.hook_cpu, errors = s.errors, last_error = s.last_error, advances = s.advances}
  if arg == 'items' then
    local l = {}
    for id, r in pairs(s.items) do
      l[#l + 1] = {id = id, v = r.v, c = r.c, ty = r.ty, job = r.j, order = r.o, bld = r.b, stack = r.stack, tick = r.t,
                   credited = order_credited(s, r.o) or r.b >= s.bld0}
    end
    table.sort(l, function(a, b) return a.id < b.id end)
    o.items = l
    o.log = s.log
  end
  print(json.encode(o))
else
  qerror('usage: credit.lua start [ambient] | dump [items]')
end
