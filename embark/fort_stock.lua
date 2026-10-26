-- fort_stock.lua <cmd> [args] : set a fort's stocks to exact counts (embark/build_fort.py; task forts from a seed).
-- Items are created with DFHack's dfhack.items.createItem (made by the lowest-id citizen) and put on the ground on
-- free floor tiles 10-16 tiles from the map's centre (clear of the workshop and stair sites build_fort.py uses, which are
-- the nearest free 3x3s), in a fixed scan order; removals take the highest item ids first. Given
-- the same map and the same items before, the result is the same. Commands:
--   logs <n>                     free logs (wood of the tree nearest the map centre) up to n; never removes logs
--   drink <n> <barrels>          remove every drink, then n units of dwarven wine in <barrels> new barrels
--   barrels_empty <n>            create or remove empty barrels so exactly n are empty
--   plants <PLANT_ID> <n>        usable plant items of that plant (e.g. MUSHROOM_HELMET_PLUMP) set to n units
--   plants_all <n>               every usable plant item: remove highest ids until <= n units (0 = none)
--   seeds <PLANT_ID> <n>         seeds of that plant set to n
--   food <n>                     add prepared fish (the wagon's fish kind, else lungfish) until food_edible >= n
--   furniture <BED|TABLE|CHAIR> <n>  free (unplaced) pieces set to at least n
-- Prints one line per command: STOCK <cmd> <before> -> <after>.
local a = {...}
local cmd = a[1]
local other = df.global.world.items.other
local creator
for _, u in ipairs(df.global.world.units.active) do
  if dfhack.units.isCitizen(u) and (not creator or u.id < creator.id) then creator = u end
end
assert(creator, 'no citizen')
local wagon
for _, b in ipairs(df.global.world.buildings.all) do if df.building_wagonst:is_instance(b) then wagon = b end end
assert(wagon, 'no wagon')
-- items go around the map's centre, not the wagon (DF places the wagon +-1 tile at random; embark/fort_site.lua)
local wx, wy, wz = df.global.world.map.x_count // 2, df.global.world.map.y_count // 2, wagon.z

local spots = {}
do
  for r = 10, 16 do
    for dy = -r, r do
      for dx = -r, r do
        if math.max(math.abs(dx), math.abs(dy)) == r then
          local x, y = wx + dx, wy + dy
          local tt = dfhack.maps.getTileType(x, y, wz)
          local fl = dfhack.maps.getTileFlags(x, y, wz)
          local at = tt and df.tiletype.attrs[tt]
          if at and fl and at.shape == df.tiletype_shape.FLOOR and fl.flow_size == 0 and not fl.hidden
             and not dfhack.buildings.findAtTile(xyz2pos(x, y, wz)) then
            spots[#spots + 1] = xyz2pos(x, y, wz)
          end
        end
      end
    end
  end
  assert(#spots > 0, 'no free floor near the wagon')
end
local placed = 0
local function drop(it)   -- 12 items per tile, tiles in scan order
  local p = spots[(placed // 12) % #spots + 1]
  placed = placed + 1
  dfhack.items.moveToGround(it, p)
end
local function usable(it) return not (it.flags.in_building or it.flags.forbid or it.flags.in_job or it.flags.construction or it.flags.rotten) end
local function sum(v) local n = 0 for _, it in ipairs(v) do n = n + it.stack_size end return n end
local function make(t, mat, n)
  local r = dfhack.items.createItem(creator, t, -1, mat.type, mat.index)
  local it = r and r[1]
  assert(it, 'createItem failed: ' .. df.item_type[t])
  if n and n > 1 then it.stack_size = n end
  return it
end
local function sorted_desc(v, pred)
  local xs = {}
  for _, it in ipairs(v) do if not pred or pred(it) then xs[#xs + 1] = it end end
  table.sort(xs, function(p, q) return p.id > q.id end)
  return xs
end
local function remove_units(xs, excess)   -- remove whole items (or shrink the last one) until `excess` units are gone
  for _, it in ipairs(xs) do
    if excess <= 0 then break end
    if it.stack_size <= excess then excess = excess - it.stack_size; dfhack.items.remove(it)
    else it.stack_size = it.stack_size - excess; excess = 0 end
  end
end
local wood
do
  local best, bd
  for _, p in ipairs(df.global.world.plants.all) do
    if p.tree_info then
      local d = math.abs(p.pos.x - wx) + math.abs(p.pos.y - wy) + 3 * math.abs(p.pos.z - wz)
      local raw = df.plant_raw.find(p.material)
      if raw and raw.flags.TREE and (not bd or d < bd or (d == bd and p.material < best)) then best, bd = p.material, d end
    end
  end
  local raw = best and df.plant_raw.find(best)
  wood = raw and dfhack.matinfo.find('PLANT_MAT:' .. raw.id .. ':WOOD') or dfhack.matinfo.find('PLANT_MAT:MAPLE:WOOD')
end
local function of_plant(it, pid)
  local m = dfhack.matinfo.decode(it)
  return m and m.plant and m.plant.id == pid
end
local function empty_barrels()
  local xs = {}
  for _, b in ipairs(other.BARREL) do
    if #dfhack.items.getContainedItems(b) == 0 and not b.flags.in_job then xs[#xs + 1] = b end   -- as fort_summary.lua counts
  end
  return xs
end

if cmd == 'logs' then
  local n, before = tonumber(a[2]), 0
  for _, it in ipairs(other.WOOD) do if usable(it) then before = before + 1 end end
  for _ = before + 1, n do drop(make(df.item_type.WOOD, wood)) end
  local after = 0 for _, it in ipairs(other.WOOD) do if usable(it) then after = after + 1 end end
  print(('STOCK logs %d -> %d (%s)'):format(before, after, wood:getToken()))
elseif cmd == 'drink' then
  local n, nb, before = tonumber(a[2]), tonumber(a[3]), sum(other.DRINK)
  for _, it in ipairs(sorted_desc(other.DRINK)) do dfhack.items.remove(it) end
  local mat = dfhack.matinfo.find('PLANT_MAT:MUSHROOM_HELMET_PLUMP:DRINK')
  for i = 1, nb do
    local k = n // nb + ((i <= n % nb) and 1 or 0)
    if k > 0 then
      local b = make(df.item_type.BARREL, wood)
      drop(b)
      local d = make(df.item_type.DRINK, mat, k)
      dfhack.items.moveToContainer(d, b)
    end
  end
  print(('STOCK drink %d -> %d'):format(before, sum(other.DRINK)))
elseif cmd == 'barrels_empty' then
  local n = tonumber(a[2])
  local xs = empty_barrels()
  local before = #xs
  table.sort(xs, function(p, q) return p.id > q.id end)
  for i = 1, #xs - n do dfhack.items.remove(xs[i]) end
  for _ = #xs + 1, n do drop(make(df.item_type.BARREL, wood)) end
  print(('STOCK barrels_empty %d -> %d'):format(before, #empty_barrels()))
elseif cmd == 'plants' or cmd == 'seeds' then
  local pid, n = a[2], tonumber(a[3])
  local vec = cmd == 'plants' and other.PLANT or other.SEEDS
  local function cnt() local c = 0 for _, it in ipairs(vec) do if usable(it) and of_plant(it, pid) then c = c + it.stack_size end end return c end
  local before = cnt()
  if before > n then
    remove_units(sorted_desc(vec, function(it) return usable(it) and of_plant(it, pid) end), before - n)
  elseif before < n then
    local mat = dfhack.matinfo.find('PLANT_MAT:' .. pid .. (cmd == 'plants' and ':STRUCTURAL' or ':SEED'))
    assert(mat, 'no material for ' .. pid)
    drop(make(cmd == 'plants' and df.item_type.PLANT or df.item_type.SEEDS, mat, n - before))
  end
  print(('STOCK %s %s %d -> %d'):format(cmd, pid, before, cnt()))
elseif cmd == 'plants_all' then
  local n = tonumber(a[2])
  local function cnt() local c = 0 for _, it in ipairs(other.PLANT) do if usable(it) then c = c + it.stack_size end end return c end
  local before = cnt()
  if before > n then remove_units(sorted_desc(other.PLANT, usable), before - n) end
  print(('STOCK plants_all %d -> %d'):format(before, cnt()))
elseif cmd == 'food' then
  local n, before = tonumber(a[2]), sum(other.ANY_GOOD_FOOD)
  local mat
  for _, it in ipairs(other.FISH) do mat = dfhack.matinfo.decode(it); if mat then break end end
  mat = mat or dfhack.matinfo.find('CREATURE_MAT:FISH_LUNGFISH:BONE')
  local now = before
  while now < n do
    local k = math.min(10, n - now)
    drop(make(df.item_type.FISH, mat, k))
    now = now + k
  end
  print(('STOCK food %d -> %d (%s)'):format(before, sum(other.ANY_GOOD_FOOD), mat:getToken()))
elseif cmd == 'furniture' then
  local t, n = a[2], tonumber(a[3])
  local vec = other[t]
  local function nfree() local c = 0 for _, it in ipairs(vec) do if usable(it) then c = c + 1 end end return c end
  local before = nfree()
  for _ = before + 1, n do drop(make(df.item_type[t], wood)) end
  print(('STOCK furniture %s %d -> %d'):format(t, before, nfree()))
else
  qerror('usage: fort_stock.lua logs|drink|barrels_empty|plants|plants_all|seeds|food|furniture ...')
end
