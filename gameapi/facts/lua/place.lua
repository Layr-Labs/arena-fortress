-- place.lua KIND X Y Z W H [N] : find where furniture can go (HARNESS-PLAN 1.9). Read-only; prints JSON.
-- Copied from #85 (origin/obs-leaks:place.lua) with the advice field removed (game API v0).
--   KIND: bed | table | chair | door | container
--   X,Y,Z,W,H: a box to search (W=H=1 for one tile). Picks the first revealed, open floor tile in it with no
--   building, no dig designation and no stair, and checks that a free item of that kind exists (not built,
--   forbidden or reserved for a job). harness2.place_furniture then places it with quickfort.
--   N (v2): also list up to N candidate tiles (`tiles`, in search order) and `available` free items, so harness2
--   can place several.
local json = require('json')
local kind, x0, y0, z, w, h, n = ...
x0, y0, z, w, h, n = tonumber(x0), tonumber(y0), tonumber(z), tonumber(w) or 1, tonumber(h) or 1, tonumber(n)
local ITEM = {bed = 'BED', table = 'TABLE', chair = 'CHAIR', door = 'DOOR', container = 'BOX'}
local out = {ok = false}
local it_type = ITEM[kind]
if not it_type then
  out.error_code, out.error = 'bad_arguments', 'unknown furniture kind ' .. tostring(kind)
  print(json.encode(out)) return
end
local free = 0
local function seen(it)   -- v2.2: items on unrevealed tiles aren't counted (observe2.lua's rule)
  local x, y, z = dfhack.items.getPosition(it)
  if not x then return true end
  local fl = dfhack.maps.getTileFlags(x, y, z)
  return not (fl and fl.hidden)
end
for _, it in ipairs(df.global.world.items.other[it_type]) do
  if seen(it) and not (it.flags.in_building or it.flags.forbid or it.flags.in_job or it.flags.construction) then free = free + 1 end
end
out.free_items = free
out.available = free   -- quickfort's placements claim their item at once (in_job), so `free` already excludes them
if n and out.available == 0 then
  out.error_code, out.error = 'no_material', ('no free %s item'):format(kind)
  print(json.encode(out)) return
end
if free == 0 then
  out.error_code, out.error = 'no_material', ('no free %s item'):format(kind)
  print(json.encode(out)) return
end
-- v2: the same tile rules quickfort's #build applies (hack/scripts/internal/quickfort/build.lua), so a tile listed
-- here is one quickfort accepts: revealed, at most 1/7 of liquid, no building on it, a floor-like shape; beds only
-- indoors (not `outside`); doors next to a wall. Plus no dig designation and no stair.
local GENERIC = {FLOOR = true, BOULDER = true, PEBBLES = true, TWIG = true, SAPLING = true, SHRUB = true}
local function wall_adjacent(x, y)
  for _, d in ipairs({{1, 0}, {-1, 0}, {0, 1}, {0, -1}}) do
    local t = dfhack.maps.getTileType(x + d[1], y + d[2], z)
    if t and df.tiletype.attrs[t].shape == df.tiletype_shape.WALL then return true end
  end
end
local outside = 0
for y = y0, y0 + h - 1 do
  for x = x0, x0 + w - 1 do
    local tt = dfhack.maps.getTileType(x, y, z)
    local fl, occ = dfhack.maps.getTileFlags(x, y, z)
    local a = tt and df.tiletype.attrs[tt]
    local ok = a and fl and not fl.hidden and GENERIC[df.tiletype_shape[a.shape]] and fl.flow_size <= 1
       and occ and occ.building == 0 and fl.dig == df.tile_dig_designation.No
       and not dfhack.buildings.findAtTile(xyz2pos(x, y, z))
    if ok and kind == 'bed' and fl.outside then ok = false; outside = outside + 1 end
    if ok and kind == 'door' and not wall_adjacent(x, y) then ok = false end
    if ok then
      if not out.ok then out.ok, out.x, out.y, out.z = true, x, y, z end
      if not n then print(json.encode(out)) return end
      out.tiles = out.tiles or {}
      out.tiles[#out.tiles + 1] = {x, y, z}
      if #out.tiles >= n then print(json.encode(out)) return end
    end
  end
end
if out.ok then print(json.encode(out)) return end
out.error_code = 'no_space'
out.error = ('no free floor tile in %d,%d,%d (%dx%d): every tile is wall, undug, built on or designated'):format(x0, y0, z, w, h)
if outside > 0 then
  out.error = ('no free indoor tile in %d,%d,%d (%dx%d): beds go only under a roof, and %d free tile(s) here are outside'):format(x0, y0, z, w, h, outside)
end
print(json.encode(out))
