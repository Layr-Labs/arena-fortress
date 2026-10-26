-- world_probe.lua: dump the generated world in stages, so two gens of one seed can be compared stage by stage
-- (embark/world_check.sh, embark/world_compare.py, research/seed-portability.md). Run on the site screen.
--   lua -f embark/world_probe.lua world <out.json>              terrain, geology, rivers, sites, history counts
--   lua -f embark/world_probe.lua details <wx> <wy> <out.json>  one tile's mid-level details (biome, elevation, rivers)
-- Reads world-gen data only, at capture time; nothing reaches an agent.
local json = require('json')
local args = {...}
local wd = df.global.world.world_data

local function write(path, v)
  local f = assert(io.open(path, 'w'))
  f:write(json.encode(v)); f:close()
end

local function soil_layers(gi)
  local gb = df.world_geo_biome.find(gi)
  if not gb then return -1 end
  local n = 0
  for _, l in ipairs(gb.layers) do
    if l.type == df.geo_layer_type.SOIL then n = n + 1 else break end
  end
  return n
end

if args[1] == 'world' then
  local terrain, flags, sitemask = {}, {}, {}
  for wy = 0, wd.world_height - 1 do
    for wx = 0, wd.world_width - 1 do
      local e = dfhack.maps.getRegionBiome(wx, wy)
      terrain[#terrain + 1] = {wx, wy, e.elevation, e.rainfall, e.vegetation, e.temperature, e.evilness, e.drainage,
        e.volcanism, e.savagery, e.salinity, dfhack.maps.getBiomeType(wx, wy), e.geo_index, soil_layers(e.geo_index),
        e.region_id, e.landmass_id}
      flags[#flags + 1] = {wx, wy, e.flags.has_river and 1 or 0, e.flags.is_brook and 1 or 0, e.flags.is_lake and 1 or 0,
        e.flags.is_peak and 1 or 0}
      sitemask[#sitemask + 1] = {wx, wy, e.flags.has_site and 1 or 0, e.flags.has_road and 1 or 0}
    end
  end
  local rivers = {}
  for i, r in ipairs(wd.rivers) do
    local pts = {}
    for k = 0, #r.path.x - 1 do pts[#pts + 1] = {r.path.x[k], r.path.y[k]} end
    rivers[#rivers + 1] = {pts = pts, end_x = r.end_pos.x, end_y = r.end_pos.y}
  end
  local sites, names = {}, {}
  for _, s in ipairs(wd.sites) do
    local civ = df.historical_entity.find(s.civ_id)
    sites[#sites + 1] = {id = s.id, type = df.world_site_type[s.type], x = s.pos.x, y = s.pos.y,
      rect = {s.global_min_x, s.global_min_y, s.global_max_x, s.global_max_y},
      civ_race = civ and civ.race >= 0 and df.creature_raw.find(civ.race).creature_id or nil}
    names[#names + 1] = dfhack.translation.translateName(s.name, true)
  end
  local h = df.global.world.history
  local ev_types = {}
  for _, ev in ipairs(h.events) do ev_types[#ev_types + 1] = ev:getType() end
  local ents = {}
  for _, en in ipairs(df.global.world.entities.all) do
    ents[#ents + 1] = {en.type, en.race}
  end
  write(args[2], {
    dims = {wd.world_width, wd.world_height},
    world_name = dfhack.translation.translateName(wd.name, true),
    cur_year = df.global.cur_year,
    terrain = terrain, river_flags = flags, sitemask = sitemask, rivers = rivers,
    geo_biomes = #df.global.world.world_data.geo_biomes,
    sites = sites, site_names = names,
    history = {figures = #h.figures, events = #h.events, entities = #df.global.world.entities.all,
               event_types = ev_types, entity_kinds = ents},
  })
  print('WORLD_PROBE ok sites=' .. #sites .. ' events=' .. #h.events .. ' figures=' .. #h.figures)
elseif args[1] == 'details' then
  local wx, wy = tonumber(args[2]), tonumber(args[3])
  local rd
  for _, d in ipairs(wd.midmap_data.region_details) do
    if d.pos.x == wx and d.pos.y == wy then rd = d end
  end
  if not rd then print('NOTLOADED') return end
  local b, el, rv, rh = {}, {}, {}, {}
  for x = 0, 15 do
    for y = 0, 15 do
      b[#b + 1] = rd.biome[x][y]; el[#el + 1] = rd.elevation[x][y]
      rv[#rv + 1] = rd.rivers_vertical.active[x][y]
      local ok, v = pcall(function() return rd.rivers_horizontal.active[x][y] end)
      rh[#rh + 1] = ok and v or -1
    end
  end
  write(args[4], {wx = wx, wy = wy, biome = b, elevation = el, rivers_v = rv, rivers_h = rh})
  print('DETAILS ok')
else
  qerror('usage: world_probe.lua world <out> | details <wx> <wy> <out>')
end
