-- invade_edge.lua RACE N [CIV_CODE|-] [WEAPON_SUBTYPE_ID|-] [MARK_DAYS] [WAIT_DAYS] [LEAVE_DAY]
-- invade.lua at a spawn point picked from the map instead of fixed coordinates, for seed-built forts (LT05 on
-- embark/forts/worked-y1): the walkable surface tile in the wagon's walkable group nearest the map's southern edge
-- (from 3 tiles inside it northwards), nearest the wagon's x on that row. On scripted-y1 this rule gives the
-- coordinates LT05 hard-codes (the south edge below the wagon). Prints SPAWN x y z, then invade.lua's output.
local a = {...}
local wagon
for _, b in ipairs(df.global.world.buildings.all) do if df.building_wagonst:is_instance(b) then wagon = b end end
assert(wagon, 'no wagon')
local function wgroup(x, y, z) local b = dfhack.maps.getTileBlock(x, y, z) return b and b.walkable[x % 16][y % 16] or 0 end
local g0 = wgroup(wagon.centerx, wagon.centery + 2, wagon.z)
if g0 == 0 then g0 = wgroup(wagon.centerx + 2, wagon.centery, wagon.z) end
assert(g0 ~= 0, 'no walkable tile beside the wagon')
local mx, my = df.global.world.map.x_count, df.global.world.map.y_count
local sx, sy, sz
for y = my - 4, wagon.centery + 10, -1 do
  for d = 0, mx do
    for _, x in ipairs({wagon.centerx - d, wagon.centerx + d}) do
      if x >= 1 and x < mx - 1 then
        for dz = 0, 6 do
          for _, z in ipairs({wagon.z - dz, wagon.z + dz}) do
            local fl = dfhack.maps.getTileFlags(x, y, z)
            if not sx and fl and not fl.hidden and fl.outside and wgroup(x, y, z) == g0 then sx, sy, sz = x, y, z end
          end
        end
      end
    end
    if sx then break end
  end
  if sx then break end
end
assert(sx, 'no spawn tile at the southern edge in the fort\'s walkable group')
print(('SPAWN %d %d %d'):format(sx, sy, sz))
local f = assert(loadfile(dfhack.getDFPath() .. '/../scenarios/lua/invade.lua'))
f(a[1], a[2], tostring(sx), tostring(sy), tostring(sz), a[3] or '-', a[4] or '-', a[5], a[6], a[7])
