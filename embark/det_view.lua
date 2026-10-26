-- det_view.lua camera | reset : keep rendering from touching simulation state (research/determinism.md).
--
-- Units' body-part and nerve data are lazily computed caches (unit.flags2.calculated_nerves / calculated_bodyparts,
-- with calculated_insulation / calculated_inventory alike, and the matching unit.enemy vectors). Drawing a unit on
-- screen computes them, and frames render on wall-clock timing, so which units have them by a given tick differs from
-- run to run, and the simulation's later computation takes a different number of RNG draws.
--   camera  point the fortress view at the top z-level, corner (0,0): normally open sky with no units in view
--   reset   camera, plus clear the four calculated_* flags on every active unit so all caches start uncomputed
-- Prints JSON {window: [x,y,z], cleared: n}.
local cmd = ({...})[1] or 'camera'
local z = df.global.world.map.z_count - 1
df.global.window_x, df.global.window_y, df.global.window_z = 0, 0, z
local cleared = 0
if cmd == 'reset' then
  for _, u in ipairs(df.global.world.units.active) do
    for _, f in ipairs({'calculated_nerves', 'calculated_bodyparts', 'calculated_insulation', 'calculated_inventory'}) do
      if u.flags2[f] then u.flags2[f] = false; cleared = cleared + 1 end
    end
  end
end
print(require('json').encode({window = {df.global.window_x, df.global.window_y, df.global.window_z}, cleared = cleared}))
