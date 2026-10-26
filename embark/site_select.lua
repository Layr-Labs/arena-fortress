-- site_select.lua: embark-site selection on the "choose start site" screen (embark/make_embark.sh drives it).
--   lua -f embark/site_select.lua list  <rules.json>          CAND <wx> <wy> <score> <biome> ... (best first)
--   lua -f embark/site_select.lua rect  <rules.json> <wx> <wy> RECT <lx> <ly> <river_cells> <elev_range> | NORECT <why>
--   lua -f embark/site_select.lua loaded <wx> <wy>             LOADED | NOTLOADED (region details for the tile)
--   lua -f embark/site_select.lua warn                          WARN <flag>... (set after the embark click)
-- Reads world-gen data only (region map, geology, mid-level region details). It runs at capture time, never during a
-- run, and nothing it prints reaches the agent (BENCHMARK-v1 §4.3). Every ordering is deterministic: ties break on
-- coordinates, so the same world and rules give the same site.
local json = require('json')
local args = {...}
local mode = args[1]
local wd = df.global.world.world_data

local function rules(path)
  local f = assert(io.open(path, 'r'), 'cannot open ' .. tostring(path))
  local r = json.decode(f:read('*a')); f:close()
  return r.region or {}, r.rect or {}
end

local function soil_layers(e)
  local gb = df.world_geo_biome.find(e.geo_index)
  if not gb then return 0 end
  local n = 0
  for _, l in ipairs(gb.layers) do
    if l.type == df.geo_layer_type.SOIL then n = n + 1 else break end   -- contiguous soil from the top
  end
  return n
end

local function inlist(v, list)
  for _, x in ipairs(list or {}) do if x == v then return true end end
  return false
end

local function site_near(wx, wy, margin)
  for x = math.max(0, wx - margin), math.min(wd.world_width - 1, wx + margin) do
    for y = math.max(0, wy - margin), math.min(wd.world_height - 1, wy + margin) do
      if dfhack.maps.getRegionBiome(x, y).flags.has_site then return true end
    end
  end
  return false
end

local function region_ok(R, wx, wy)
  local e = dfhack.maps.getRegionBiome(wx, wy)
  local biome = df.biome_type[dfhack.maps.getBiomeType(wx, wy)] or '?'
  local soil = soil_layers(e)
  local river = e.flags.has_river or e.flags.is_brook
  local why
  if R.biomes and not inlist(biome, R.biomes) then why = 'biome'
  elseif e.flags.is_lake or e.flags.is_peak then why = 'lake_or_peak'
  elseif R.require_river and not river then why = 'no_river'
  elseif soil < (R.soil_layers_min or 0) then why = 'soil'
  elseif R.soil_layers_max and soil > R.soil_layers_max then why = 'soil_deep'
  elseif e.salinity > (R.salinity_max or 100) then why = 'salt'
  elseif e.savagery > (R.savagery_max or 100) then why = 'savage'
  elseif e.evilness > (R.evilness_max or 100) or e.evilness < (R.evilness_min or 0) then why = 'evil_or_good'
  elseif e.vegetation < (R.vegetation_min or 0) or e.vegetation > (R.vegetation_max or 100) then why = 'vegetation'
  elseif e.temperature < (R.temperature_min or -1000) or e.temperature > (R.temperature_max or 1000) then why = 'temperature'
  elseif e.drainage < (R.drainage_min or 0) or e.drainage > (R.drainage_max or 100) then why = 'drainage'
  elseif R.site_margin and site_near(wx, wy, R.site_margin) then why = 'site'
  end
  return why, e, biome, soil, river
end

local function details(wx, wy)
  for _, rd in ipairs(wd.midmap_data.region_details) do
    if rd.pos.x == wx and rd.pos.y == wy then return rd end
  end
end

if mode == 'list' then
  local R = rules(args[2])
  local out, rejected = {}, {}
  for wx = 0, wd.world_width - 1 do
    for wy = 0, wd.world_height - 1 do
      local why, e, biome, soil, river = region_ok(R, wx, wy)
      if why then
        rejected[why] = (rejected[why] or 0) + 1
      else
        -- prefer deep soil and middling vegetation, then the tile nearest the world's centre (fewer ocean edges)
        local cx, cy = (wd.world_width - 1) / 2, (wd.world_height - 1) / 2
        local score = math.min(soil, 6) * 10 - math.abs(e.vegetation - (R.vegetation_target or 60)) / 5
                      - (math.abs(wx - cx) + math.abs(wy - cy)) / 4
        out[#out + 1] = {wx = wx, wy = wy, score = score, biome = biome, soil = soil, e = e}
      end
    end
  end
  table.sort(out, function(a, b)
    if a.score ~= b.score then return a.score > b.score end
    if a.wy ~= b.wy then return a.wy < b.wy end
    return a.wx < b.wx
  end)
  for _, c in ipairs(out) do
    local e = c.e
    print(('CAND %d %d %.2f %s soil=%d veg=%d temp=%d rain=%d drain=%d sav=%d evil=%d salt=%d elev=%d'):format(
      c.wx, c.wy, c.score, c.biome, c.soil, e.vegetation, e.temperature, e.rainfall, e.drainage, e.savagery,
      e.evilness, e.salinity, e.elevation))
  end
  local r = {}
  for k, v in pairs(rejected) do r[#r + 1] = k .. '=' .. v end
  table.sort(r)
  print('REJECTED ' .. table.concat(r, ' '))
elseif mode == 'loaded' then
  print(details(tonumber(args[2]), tonumber(args[3])) and 'LOADED' or 'NOTLOADED')
elseif mode == 'rect' then
  local _, Q = rules(args[2])
  local wx, wy = tonumber(args[3]), tonumber(args[4])
  local rd = details(wx, wy)
  if not rd then print('NORECT details_not_loaded') return end
  local function river(x, y)
    local v = rd.rivers_vertical.active[x][y] ~= 0
    local h = false
    pcall(function() h = rd.rivers_horizontal.active[x][y] ~= 0 end)
    return v or h
  end
  -- existing sites' mid-level rectangles (DF refuses an embark that overlaps one), grown by `avoid_sites` tiles
  local sites = {}
  local m = Q.avoid_sites or 0
  for _, s in ipairs(wd.sites) do
    sites[#sites + 1] = {s.global_min_x - m, s.global_min_y - m, s.global_max_x + m, s.global_max_y + m}
  end
  local function hits_site(gx0, gy0, gx1, gy1)
    for _, r in ipairs(sites) do
      if gx0 <= r[3] and gx1 >= r[1] and gy0 <= r[4] and gy1 >= r[2] then return true end
    end
    return false
  end
  local best
  for ly = 0, 12 do
    for lx = 0, 12 do
      local pure, rcells, emin, emax = true, 0, 1e9, -1e9
      for x = lx, lx + 3 do
        for y = ly, ly + 3 do
          if rd.biome[x][y] ~= 5 then pure = false end       -- 5 = this region tile's own biome (keypad centre)
          if river(x, y) then rcells = rcells + 1 end
          local el = rd.elevation[x][y]
          emin, emax = math.min(emin, el), math.max(emax, el)
        end
      end
      local ok = pure and not hits_site(wx * 16 + lx, wy * 16 + ly, wx * 16 + lx + 3, wy * 16 + ly + 3) and (rcells >= (Q.river_cells_min or 0)) and (rcells <= (Q.river_cells_max or 16))
                 and (emax - emin <= (Q.elev_range_max or 100))
      if ok then
        -- nearest the tile's centre, then flattest; ties break on (ly, lx) by scan order
        local cost = math.abs(lx - 6) + math.abs(ly - 6) + 2 * (emax - emin)
        if not best or cost < best.cost then
          best = {lx = lx, ly = ly, cost = cost, rcells = rcells, er = emax - emin}
        end
      end
    end
  end
  if best then
    print(('RECT %d %d %d %d'):format(best.lx, best.ly, best.rcells, best.er))
  else
    print('NORECT no_rect')
  end
elseif mode == 'warn' then
  local v = dfhack.gui.getDFViewscreen(true)
  local w = {}
  if v.warn_flags then
    for k, x in pairs(v.warn_flags) do if x and type(k) == 'string' then w[#w + 1] = k end end
  end
  table.sort(w)
  print('WARN ' .. table.concat(w, ' '))
else
  qerror('usage: site_select.lua list|rect|loaded|warn ...')
end
