-- Read-only map queries for the automation arm (automation/commands.py, policies.Automation). Prints one JSON object. Changes nothing.
--   stair_site                 an access-stair tile for automation/yukon-automation.csv: open surface floor near the
--                              wagon whose footprint on the 3 levels below looks safe from what is visible (below)
--   orders                     number of manager orders
--   undug x y z w h            how many tiles of a rectangle are not yet open floor (0 = room fully dug)
local json = require('json')
local a = {...}
local function out(t) print(json.encode(t)) end

local function wagon()
  for _, b in ipairs(df.global.world.buildings.all) do
    if df.building_wagonst:is_instance(b) then return b end
  end
end

local function attrs(x, y, z)
  local tt = dfhack.maps.getTileType(x, y, z)
  return tt and df.tiletype.attrs[tt]
end

-- solid, undug soil with no water table and no liquid: digging it cannot flood the fort
local function dry_soil_wall(x, y, z)
  local at = attrs(x, y, z)
  if not at or at.shape ~= df.tiletype_shape.WALL or at.material ~= df.tiletype_material.SOIL then return false end
  local f = dfhack.maps.getTileFlags(x, y, z)
  return f and not f.water_table and f.flow_size == 0 and f.dig == df.tile_dig_designation.No
end

local function open_floor(x, y, z)
  local at = attrs(x, y, z)
  if not at or at.shape ~= df.tiletype_shape.FLOOR or at.material == df.tiletype_material.TREE then return false end
  local f = dfhack.maps.getTileFlags(x, y, z)
  return f and f.flow_size == 0 and f.dig == df.tile_dig_designation.No and not dfhack.buildings.findAtTile(xyz2pos(x, y, z))
end

-- What the player can see: a revealed tile is judged by its type; an unrevealed one (all of them underground at the
-- start) only by the surface above it, which must be plain floor: no tree (roots), water, ramp or wall. Hidden
-- tiles are never read, so the arm knows no more than a player looking at the map. The depth it digs to (three
-- soil levels) is design-time site knowledge, like the soil level the v2 manual tells every arm about.
local function surface_clear(x, y, z)
  local at = attrs(x, y, z)
  if not at or at.material == df.tiletype_material.TREE then return false end
  local s = at.shape
  local T = df.tiletype_shape
  if s ~= T.FLOOR and s ~= T.SHRUB and s ~= T.SAPLING and s ~= T.PEBBLES and s ~= T.BOULDER then return false end
  local f = dfhack.maps.getTileFlags(x, y, z)
  return f and f.flow_size == 0
end

local function diggable(x, y, z, wz)
  local f = dfhack.maps.getTileFlags(x, y, z)
  if not f then return false end
  if f.hidden then return surface_clear(x, y, wz) end
  return dry_soil_wall(x, y, z)
end

-- footprint of yukon-automation.csv relative to the stair at (0,0): {z offset, x0, x1} over rows y-1..y+1,
-- plus a 1-tile margin so no room breaks into water, aquifer or tree roots next to it
local FOOT = {{-1, -1, 12}, {-2, -6, 12}, {-3, -1, 12}}

local function fits(x, y, z)
  -- stair tile and its neighbours on the surface: open floor with no building (keeps the stair reachable)
  for dx = -1, 1 do for dy = -1, 1 do if not open_floor(x + dx, y + dy, z) then return false end end end
  for _, f in ipairs(FOOT) do
    for fx = f[2], f[3] do for fy = -2, 2 do   -- rows y-1..y+1 and the margin
      if not diggable(x + fx, y + fy, z + f[1], z) then return false end
    end end
  end
  return true
end

if a[1] == 'stair_site' then
  local w = wagon()
  local wx, wy, wz = w and w.centerx or 97, w and w.centery or 96, w and w.z or 106
  local best
  for r = 6, 40 do
    for dx = -r, r do for dy = -r, r do
      if not best and math.max(math.abs(dx), math.abs(dy)) == r and fits(wx + dx, wy + dy, wz) then
        best = {x = wx + dx, y = wy + dy, z = wz}
      end
    end end
    if best then break end
  end
  if best then return out({ok = true, site = best}) end
  return out({ok = false, error = 'no surface site within 40 tiles has a clear footprint for 3 levels'})
elseif a[1] == 'orders' then
  return out({ok = true, n = #df.global.world.manager_orders.all})
elseif a[1] == 'undug' then
  local x, y, z, w, h = tonumber(a[2]), tonumber(a[3]), tonumber(a[4]), tonumber(a[5]), tonumber(a[6])
  local n = 0
  for ix = x, x + w - 1 do for iy = y, y + h - 1 do
    local at = attrs(ix, iy, z)
    if not at or at.shape ~= df.tiletype_shape.FLOOR then n = n + 1 end
  end end
  return out({ok = true, undug = n})
end
out({ok = false, error = 'usage: stair_site | orders | undug x y z w h'})
