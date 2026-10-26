-- fort_site.lua : site helpers for embark/build_fort.py (task forts from a seed). Reads hidden tiles: build time only.
--   fort_site.lua anchor                 print ANCHOR x y z: the map's centre column on the wagon's level. DF places the
--                                        wagon at a random tile of the centre (+-1 from one embark of a seed to the
--                                        next), so everything a recipe builds is placed relative to this fixed point,
--                                        not to the wagon: then the layout is the same in every build of a seed
--   fort_site.lua sites <n>              print SITES <json>: up to n free 3x3 surface sites, nearest the anchor first,
--                                        by observe2.lua's rules (open floor, not a tree, no building, not hidden, no
--                                        dig designation; never overlapping) plus a 9x9 keep-out box around the anchor,
--                                        which covers every wagon position
--   fort_site.lua room <x> <y> <z> <w> <h>   OK when every tile of the box is a soil wall: no tree roots (DF cancels
--                                        digging a root wall under a living tree; dig-now skips it too), no stone (no
--                                        farm plot), no liquid, no aquifer, nothing already open. Else BAD <why> <x,y,z>
local A = {...}
local mode = A[1]
local wagon
for _, b in ipairs(df.global.world.buildings.all) do if df.building_wagonst:is_instance(b) then wagon = b end end
local ax, ay = df.global.world.map.x_count // 2, df.global.world.map.y_count // 2
local az = wagon and wagon.z
if mode == 'anchor' then
  print(('ANCHOR %d %d %d'):format(ax, ay, az))
elseif mode == 'sites' then
  local n = tonumber(A[2]) or 8
  local function free(x, y, z)
    if math.abs(x - ax) <= 4 and math.abs(y - ay) <= 4 then return false end
    local tt = dfhack.maps.getTileType(x, y, z)
    if not tt then return false end
    local a = df.tiletype.attrs[tt]
    if a.shape ~= df.tiletype_shape.FLOOR or a.material == df.tiletype_material.TREE then return false end
    if dfhack.buildings.findAtTile(xyz2pos(x, y, z)) then return false end
    local d = dfhack.maps.getTileFlags(x, y, z)
    return d and not d.hidden and d.dig == df.tile_dig_designation.No and d.flow_size == 0
  end
  local sites, taken = {}, {}
  for r = 3, 20 do
    for dx = -r, r, 2 do for dy = -r, r, 2 do
      if math.max(math.abs(dx), math.abs(dy)) == r and #sites < n then
        local x, y, ok = ax + dx, ay + dy, true
        for i = -1, 1 do for j = -1, 1 do
          if not free(x + i, y + j, az) or taken[(x + i) .. ',' .. (y + j)] then ok = false end
        end end
        if ok then
          sites[#sites + 1] = ('{"x": %d, "y": %d, "z": %d}'):format(x, y, az)
          for i = -1, 1 do for j = -1, 1 do taken[(x + i) .. ',' .. (y + j)] = true end end
        end
      end
    end end
  end
  print('SITES [' .. table.concat(sites, ', ') .. ']')
elseif mode == 'room' then
  local x0, y0, z, w, h = tonumber(A[2]), tonumber(A[3]), tonumber(A[4]), tonumber(A[5]), tonumber(A[6])
  for y = y0, y0 + h - 1 do
    for x = x0, x0 + w - 1 do
      local tt = dfhack.maps.getTileType(x, y, z)
      local fl = dfhack.maps.getTileFlags(x, y, z)
      if not tt or not fl then print(('BAD off_map %d,%d,%d'):format(x, y, z)) return end
      local at = df.tiletype.attrs[tt]
      local why = (at.shape ~= df.tiletype_shape.WALL and 'open') or (at.material == df.tiletype_material.ROOT and 'roots')
                  or (at.material ~= df.tiletype_material.SOIL and 'not_soil') or (fl.flow_size > 0 and 'liquid')
                  or (fl.water_table and 'aquifer') or nil
      if why then print(('BAD %s %d,%d,%d'):format(why, x, y, z)) return end
    end
  end
  print('OK')
else
  qerror('usage: fort_site.lua anchor | sites <n> | room <x> <y> <z> <w> <h>')
end
