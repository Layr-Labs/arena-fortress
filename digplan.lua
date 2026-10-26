-- digplan.lua x y z w h : print which cells of the rectangle already carry a stair
-- designation or are already open stairs, so dig_room can leave them alone.
local a = {...}
local x, y, z, w, h = tonumber(a[1]), tonumber(a[2]), tonumber(a[3]), tonumber(a[4]), tonumber(a[5])
local keep = {}
local stairdes = {[df.tile_dig_designation.UpStair] = 'u', [df.tile_dig_designation.DownStair] = 'j', [df.tile_dig_designation.UpDownStair] = 'i'}
for dy = 0, h - 1 do for dx = 0, w - 1 do
  local f = dfhack.maps.getTileFlags(x + dx, y + dy, z)
  local tt = f and not f.hidden and dfhack.maps.getTileType(x + dx, y + dy, z)   -- v2.2: no shape for unrevealed tiles
  local shape = tt and df.tiletype.attrs[tt].shape
  if (f and stairdes[f.dig]) or shape == df.tiletype_shape.STAIR_UP or shape == df.tiletype_shape.STAIR_DOWN or shape == df.tiletype_shape.STAIR_UPDOWN then
    keep[#keep + 1] = dx .. ',' .. dy
  end
end end
print('KEEP ' .. table.concat(keep, ' '))
