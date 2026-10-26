-- manager_office.lua : give the appointed manager a working office (an Office zone with a chair, assigned to them).
-- Why: once a fort has 20 or more citizens, new work orders wait for the manager's validation, and the manager
-- validates only from an office of their own (checked 2026-10-10 on scripted-y1 after a migrant wave: an Office zone
-- with a built chair validated a new order within 2 days once assigned to the manager, and never while
-- unassigned). The tool API can make an office zone and place a chair but can't assign a zone to a dwarf
-- (a v1.1 candidate), so a scenario that pushes the fort past 20 must set this up itself, as a player would have.
-- Picks the first free surface floor tile 9-14 tiles from the wagon (out of the way of the W sites, which are the
-- nearest free 3x3s), designates a chair there (a dwarf installs one of the fort's free chairs) and a 1x1 Office
-- zone over it, and assigns the zone to the manager. Prints OFFICE x y z manager=<unit id>.
local ent = df.historical_entity.find(df.global.plotinfo.group_id)
local manager
for _, a in ipairs(ent.positions.assignments) do
  for _, p in ipairs(ent.positions.own) do
    if p.id == a.position_id and p.code == 'MANAGER' and a.histfig2 ~= -1 then
      local hf = df.historical_figure.find(a.histfig2)
      manager = hf and df.unit.find(hf.unit_id)
    end
  end
end
if not manager then qerror('no manager appointed') end
local wx, wy, wz
for _, b in ipairs(df.global.world.buildings.all) do
  if df.building_wagonst:is_instance(b) then wx, wy, wz = b.centerx, b.centery, b.z end
end
if not wx then qerror('no wagon') end
local function ok(x, y, z)
  local tt = dfhack.maps.getTileType(x, y, z)
  local fl = dfhack.maps.getTileFlags(x, y, z)
  local a = tt and df.tiletype.attrs[tt]
  return a and fl and not fl.hidden and a.shape == df.tiletype_shape.FLOOR and fl.dig == df.tile_dig_designation.No
         and not dfhack.buildings.findAtTile(xyz2pos(x, y, z)) and fl.flow_size == 0
end
local px, py
for r = 9, 14 do
  for dy = -r, r do
    for dx = -r, r do
      if not px and math.max(math.abs(dx), math.abs(dy)) == r and ok(wx + dx, wy + dy, wz) then px, py = wx + dx, wy + dy end
    end
  end
end
if not px then qerror('no free tile for the office') end
local out = ''
for _, nb in ipairs({{'scenario_office_zone', '#zone\no\n'}, {'scenario_office_chair', '#build\nc\n'}}) do
  local name, body = nb[1], nb[2]
  local f = io.open(dfhack.getDFPath() .. '/dfhack-config/blueprints/' .. name .. '.csv', 'w'); f:write(body); f:close()
  out = out .. dfhack.run_command_silent('quickfort', 'run', name .. '.csv', '-c', ('%d,%d,%d'):format(px, py, wz))
end
local zone
for _, z in ipairs(df.global.world.buildings.other.ACTIVITY_ZONE) do
  if z.type == df.civzone_type.Office and z.x1 <= px and px <= z.x2 and z.y1 <= py and py <= z.y2 and z.z == wz then zone = z end
end
if not zone then qerror('office zone not created: ' .. tostring(out)) end
if not dfhack.buildings.setOwner(zone, manager) then qerror('could not assign the office') end
print(('OFFICE %d %d %d manager=%d zone=%d'):format(px, py, wz, manager.id, zone.id))
