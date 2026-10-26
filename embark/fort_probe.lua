-- fort_probe.lua <rules.json> : site acceptance + determinism fingerprint, run on a fresh embark (paused, day 0).
-- Prints one JSON line: {"accept":bool, "why":[...], "site":..., "soil":..., "trees":.., "water":.., "aquifer":..,
-- "fingerprint":{map, plants, roster, items}}. Capture-time only (embark/make_embark.sh): the agent never sees it
-- (BENCHMARK-v1 §4.3). It reads the whole map, revealed or not, which is exactly why it must not run during a run.
local json = require('json')
local path = ...
local f = assert(io.open(path, 'r'), 'cannot open ' .. tostring(path))
local rules = json.decode(f:read('*a')); f:close()
local A = rules.accept or {}

local map = df.global.world.map
local X, Y, Z = map.x_count, map.y_count, map.z_count
local TT = df.tiletype
local attrs = df.tiletype.attrs
local SHAPE, MAT = df.tiletype_shape, df.tiletype_material

-- FNV-1a, 32 bit
local H0 = 2166136261
local function fnv(h, v)
  v = math.floor(v) & 0xffffffff
  for _ = 1, 4 do
    h = ((h ~ (v & 0xff)) * 16777619) & 0xffffffff
    v = v >> 8
  end
  return h
end
local function fnvs(h, s)
  for i = 1, #s do h = ((h ~ s:byte(i)) * 16777619) & 0xffffffff end
  return h
end

local wagon
for _, b in ipairs(df.global.world.buildings.all) do
  if df.building_wagonst:is_instance(b) then wagon = {x = b.centerx, y = b.centery, z = b.z} end
end

-- per-column surface z (highest tile that isn't open space) and the soil levels right below it
local function column(x, y)
  for z = Z - 1, 0, -1 do
    local tt = dfhack.maps.getTileType(x, y, z)
    if tt then
      local sh = attrs[tt].shape
      if sh ~= SHAPE.EMPTY and sh ~= SHAPE.RAMP_TOP and sh ~= SHAPE.NONE then
        -- a floor-type surface tile sits on the level below; a wall at the top means the column starts there
        local zs = (sh == SHAPE.WALL) and z + 1 or z
        local soil = 0
        for zz = zs - 1, 0, -1 do
          local t2 = dfhack.maps.getTileType(x, y, zz)
          if t2 and attrs[t2].material == MAT.SOIL then soil = soil + 1 else break end
        end
        return zs, soil
      end
    end
  end
end

local mh, water_table, flow_out, flow_tiles, brook = H0, 0, 0, 0, 0
local wt_top = {}   -- [x*4096+y] = highest z with an aquifer tile in that column
for z = 0, Z - 1 do
  for by = 0, Y - 1, 16 do
    for bx = 0, X - 1, 16 do
      local blk = dfhack.maps.getTileBlock(bx, by, z)
      for y = 0, 15 do
        for x = 0, 15 do
          local tt = blk and blk.tiletype[x][y] or -1
          local d = blk and blk.designation[x][y]
          mh = fnv(mh, tt)
          if d then
            mh = fnv(mh, (d.water_table and 1 or 0) + 2 * d.flow_size + (d.liquid_type and 32 or 0))
            if d.water_table then
              water_table = water_table + 1
              local key = (bx + x) * 4096 + (by + y)
              if not wt_top[key] or z > wt_top[key] then wt_top[key] = z end
            end
            if d.flow_size > 0 and not d.liquid_type then
              flow_tiles = flow_tiles + 1
              if d.outside then flow_out = flow_out + 1 end
            end
          end
          if tt >= 0 then
            local sh = attrs[tt].shape
            if sh == SHAPE.BROOK_BED or sh == SHAPE.BROOK_TOP then brook = brook + 1 end
          end
        end
      end
    end
  end
end

-- soil depth on a 3-tile grid over the whole embark, and within NEAR tiles of the wagon
local NEAR = A.near_radius or 15
local all, near, near_soil = {}, {}, {}
local aq_depth   -- fewest levels from the surface down to the aquifer, over wagon-level columns near the wagon
local zmin, zmax = 1e9, -1e9
for x = 1, X - 2, 3 do
  for y = 1, Y - 2, 3 do
    local zs, soil = column(x, y)
    if zs then
      all[#all + 1] = soil
      if wagon and math.abs(x - wagon.x) <= NEAR and math.abs(y - wagon.y) <= NEAR then
        near[#near + 1] = soil
        zmin, zmax = math.min(zmin, zs), math.max(zmax, zs)
        if wagon and zs == wagon.z then
          near_soil[#near_soil + 1] = soil
          local top = wt_top[x * 4096 + y]
          if top and (not aq_depth or zs - top < aq_depth) then aq_depth = zs - top end
        end
      end
    end
  end
end
local function frac(t, k) local n = 0 for _, v in ipairs(t) do if v >= k then n = n + 1 end end return #t > 0 and n / #t or 0 end
local function median(t) local c = {} for i, v in ipairs(t) do c[i] = v end table.sort(c) return c[math.max(1, (#c + 1) // 2)] or 0 end

-- trees and other plants (positions + species), sorted so the hash is order-free
local trees, plist = 0, {}
for _, p in ipairs(df.global.world.plants.all) do
  if p.tree_info then trees = trees + 1 end
  plist[#plist + 1] = ('%d,%d,%d,%d'):format(p.pos.x, p.pos.y, p.pos.z, p.material)
end
table.sort(plist)
local ph = H0
for _, s in ipairs(plist) do ph = fnvs(ph, s) end

-- the embark party: profession + skills per citizen (names are cosmetic and come from the civ's language).
-- "Play now!" fixes professions and work skills; the performance skills below come from each dwarf's random
-- personality, so roster_core leaves them out (roster keeps everything)
local PERFORM = {DANCE = true, SING_MUSIC = true, MAKE_MUSIC = true, PLAY_KEYBOARD_INSTRUMENT = true,
                 PLAY_STRINGED_INSTRUMENT = true, PLAY_WIND_INSTRUMENT = true, PLAY_PERCUSSION_INSTRUMENT = true,
                 POETRY = true}
local roster, core = {}, {}
local npop = 0
for _, u in ipairs(df.global.world.units.active) do
  if dfhack.units.isCitizen(u) then
    npop = npop + 1
    local sk, sc = {}, {}
    local soul = u.status.current_soul
    if soul then
      for _, s in ipairs(soul.skills) do
        local n = df.job_skill[s.id]
        sk[#sk + 1] = n .. '=' .. s.rating
        if not PERFORM[n] then sc[#sc + 1] = n .. '=' .. s.rating end
      end
    end
    table.sort(sk); table.sort(sc)
    roster[#roster + 1] = df.profession[u.profession] .. ':' .. table.concat(sk, ',')
    core[#core + 1] = df.profession[u.profession] .. ':' .. table.concat(sc, ',')
  end
end
table.sort(roster); table.sort(core)
local rh, rch = H0, H0
for _, s in ipairs(roster) do rh = fnvs(rh, s) end
for _, s in ipairs(core) do rch = fnvs(rch, s) end

-- items: all in play (by type), and the embark loadout = items no unit holds and that aren't spider webs, by type,
-- weapons apart. Webs, the gear wildlife/cavern units carry, and the number and kinds of the loadout's weapons are
-- random per embark (6-8 weapons seen for one seed), so `loadout` leaves weapons out and `loadout_weapons` lists them
local icount, lcount, weapons = {}, {}, {}
for _, it in ipairs(df.global.world.items.other.IN_PLAY) do
  local k = df.item_type[it:getType()]
  icount[k] = (icount[k] or 0) + 1
  if not dfhack.items.getHolderUnit(it) and not it.flags.spider_web then
    if k == 'WEAPON' then
      local d = dfhack.items.getDescription(it, 0, true)
      weapons[d] = (weapons[d] or 0) + 1
    else
      lcount[k] = (lcount[k] or 0) + 1
    end
  end
end
local function hashcounts(c)
  local keys = {}
  for k in pairs(c) do keys[#keys + 1] = k end
  table.sort(keys)
  local h = H0
  for _, k in ipairs(keys) do h = fnvs(h, k .. '=' .. c[k]) end
  return h
end
local ih, lh, items = hashcounts(icount), hashcounts(lcount), icount

local s = df.world_site.find(df.global.plotinfo.site_id)
local wx, wy = s and s.pos.x, s and s.pos.y
local e = wx and dfhack.maps.getRegionBiome(wx, wy)
local out = {
  site = {wx = wx, wy = wy, rect = s and {s.global_min_x, s.global_min_y, s.global_max_x, s.global_max_y},
          biome = wx and df.biome_type[dfhack.maps.getBiomeType(wx, wy)],
          savagery = e and e.savagery, evilness = e and e.evilness, temperature = e and e.temperature,
          vegetation = e and e.vegetation, rainfall = e and e.rainfall, drainage = e and e.drainage},
  map = {x = X, y = Y, z = Z, surface_z_near = {zmin, zmax}},
  wagon = wagon,
  citizens = npop,
  abs_tick = df.global.cur_year * 403200 + df.global.cur_year_tick,
  soil = {median_all = median(all), median_near = median(near), frac_ge2_near = frac(near, 2),
          frac_ge2_wagon_level = frac(near_soil, 2), frac_le1_near = #near > 0 and (1 - frac(near, 2)) or 0,
          samples_near = #near, samples_wagon_level = #near_soil},
  trees = trees,
  water = {flow_tiles = flow_tiles, surface_flow_tiles = flow_out, brook_tiles = brook},
  aquifer_tiles = water_table,
  aquifer_depth_near = aq_depth,   -- nil: no aquifer under the wagon-level ground near the wagon
  -- map, plants, roster_core and loadout are reproducible from (seed, paramset, rules); roster and items are not
  fingerprint = {map = ('%08x'):format(mh), plants = ('%08x'):format(ph), roster_core = ('%08x'):format(rch),
                 loadout = ('%08x'):format(lh), roster = ('%08x'):format(rh), items = ('%08x'):format(ih)},
  items = items, loadout = lcount, loadout_weapons = weapons, roster_core = core,
}

local why = {}
local function need(ok, msg) if not ok then why[#why + 1] = msg end end
-- soil is judged on the wagon-level ground near the wagon, where the reference policies dig their first stair
if A.wagon_level_samples_min then need(#near_soil >= A.wagon_level_samples_min, 'little_level_ground') end
if A.soil_frac_ge2_min then need(out.soil.frac_ge2_wagon_level >= A.soil_frac_ge2_min, 'soil_shallow') end
if A.soil_frac_le1_min then need(1 - out.soil.frac_ge2_wagon_level >= A.soil_frac_le1_min, 'soil_deep') end
if A.trees_min then need(trees >= A.trees_min, 'few_trees') end
if A.trees_max then need(trees <= A.trees_max, 'many_trees') end
if A.surface_water_min then need(flow_out >= A.surface_water_min, 'no_surface_water') end
if A.aquifer == false then need(water_table == 0, 'aquifer') end
if A.aquifer_depth_min then need(not aq_depth or aq_depth >= A.aquifer_depth_min, 'aquifer_shallow') end
if A.surface_z_range_max then need(zmax - zmin <= A.surface_z_range_max, 'uneven') end
need(npop == (A.citizens or 7), 'citizens')
out.accept = #why == 0
out.why = why
print(json.encode(out, {pretty = false}))
