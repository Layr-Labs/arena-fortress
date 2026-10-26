-- count designations in a box around a point: lua -f desig.lua x y z r
local a = {...}; local x0, y0, z, r = tonumber(a[1]), tonumber(a[2]), tonumber(a[3]), tonumber(a[4])
local n = 0
for x = x0 - r, x0 + r do for y = y0 - r, y0 + r do
  local d = dfhack.maps.getTileFlags(x, y, z)
  if d and d.dig ~= df.tile_dig_designation.No then n = n + 1 end
end end
print('designated', n)
