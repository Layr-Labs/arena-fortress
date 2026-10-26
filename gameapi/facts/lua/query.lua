-- query.lua NAME [ARGS_JSON]: read-only queries for the game API v0 (docs/GAME-API.md §5.2). Prints one JSON object.
-- Every list is bounded (`limit`, validated in Python as well) and says how many matched (`total`) so a cut is never
-- silent. Hidden-information rules as in observe.lua (common.lua): revealed items, visible units, revealed tiles.
local here = debug.getinfo(1, 'S').source:sub(2):match('(.*/)') or './'
local C = dofile(here .. 'common.lua')
local json = require('json')
local name = ({...})[1]
local A = C.json_arg(({...})[2]) or {}
local function out(t) print(json.encode(t, {pretty = false})) end
local function lim(default, max) local n = tonumber(A.limit) or default if n < 1 then n = 1 end if n > max then n = max end return n end
local seen, visible_unit, revealed, built = C.seen, C.visible_unit, C.revealed, C.built
local ent = df.historical_entity.find(df.global.plotinfo.group_id)
local Q = {}

-- stocks: revealed items grouped by item type, subtype and material, with stack sums and flag counts
function Q.stocks()
  local want = A.item_type and df.item_type[A.item_type]
  if A.item_type and not want then return {ok = false, error_code = 'bad_arguments', error = 'unknown item_type ' .. tostring(A.item_type)} end
  local pool = want and df.global.world.items.other[df.items_other_id[A.item_type] or 'IN_PLAY'] or df.global.world.items.other.IN_PLAY
  local groups, order = {}, {}
  local items = 0
  for _, it in ipairs(pool) do
    local t = it:getType()
    if (not want or t == want) and seen(it) and not it.flags.garbage_collect and not it.flags.removed then
      items = items + 1
      local key = t .. ':' .. it:getSubtype() .. ':' .. it:getMaterial() .. ':' .. it:getMaterialIndex()
      local g = groups[key]
      if not g then
        g = {item_type = df.item_type[t], item_subtype = C.subtype_id(t, it:getSubtype()),
             material = C.mat_string(it:getMaterial(), it:getMaterialIndex()), items = 0, count = 0,
             rotten = 0, forbidden = 0, in_job = 0, in_building = 0, in_inventory = 0, construction = 0}
        groups[key] = g; order[#order + 1] = key
      end
      local f = it.flags
      g.items = g.items + 1; g.count = g.count + it.stack_size
      if f.rotten then g.rotten = g.rotten + 1 end
      if f.forbid then g.forbidden = g.forbidden + 1 end
      if f.in_job then g.in_job = g.in_job + 1 end
      if f.in_building then g.in_building = g.in_building + 1 end
      if f.in_inventory then g.in_inventory = g.in_inventory + 1 end
      if f.construction then g.construction = g.construction + 1 end
    end
  end
  local list = {}
  for _, k in ipairs(order) do list[#list + 1] = groups[k] end
  table.sort(list, function(p, q) if p.item_type ~= q.item_type then return p.item_type < q.item_type end return p.count > q.count end)
  local n, r = lim(200, 1000), {}
  for i = 1, math.min(n, #list) do r[i] = list[i] end
  return {ok = true, groups = r, total = #list, items = items}
end

-- units: citizens (labors, skills, needs, stress, positions), the fortress's animals, or other visible units
local function skills_of(u)
  local r = {}
  local s = u.status.current_soul
  if s then for _, sk in ipairs(s.skills) do
    if sk.rating > 0 or sk.experience > 0 then r[df.job_skill[sk.id] or tostring(sk.id)] = sk.rating end
  end end
  return r
end
local function labors_of(u)
  local r = {}
  for i, v in ipairs(u.status.labors) do if v and df.unit_labor[i] then r[#r + 1] = df.unit_labor[i] end end
  return r
end
local function needs_of(u)
  local r = {}
  local s = u.status.current_soul
  if s then for _, nd in ipairs(s.personality.needs) do
    r[#r + 1] = {need = df.need_type[nd.id] or tostring(nd.id), focus_level = nd.focus_level, need_level = nd.need_level}
  end end
  return r
end
function Q.units()
  local kind = A.kind or 'citizens'
  local one = A.id and tonumber(A.id)
  local n, r, total = lim(kind == 'citizens' and 100 or 100, 300), {}, 0
  for _, u in ipairs(df.global.world.units.active) do
    if not dfhack.units.isDead(u) and (not one or u.id == one) then
      local e
      if kind == 'citizens' and dfhack.units.isCitizen(u) then
        local titles = {}
        for _, p in ipairs(dfhack.units.getNoblePositions(u) or {}) do titles[#titles + 1] = p.position.code end
        e = {id = u.id, name = C.name(u), profession = dfhack.units.getProfessionName(u),
             adult = dfhack.units.isAdult(u), positions = titles,
             squad_id = u.military.squad_id ~= -1 and u.military.squad_id or nil,
             job = u.job.current_job and df.job_type[u.job.current_job.job_type] or 'idle',
             stress = dfhack.units.getStressCategory(u), x = u.pos.x, y = u.pos.y, z = u.pos.z,
             mood = u.mood ~= -1 and df.mood_type[u.mood] or nil,
             labors = labors_of(u), skills = skills_of(u), needs = needs_of(u)}
      elseif kind == 'animals' and dfhack.units.isAnimal(u) and dfhack.units.isOwnCiv(u) and visible_unit(u) then
        e = {id = u.id, race = df.creature_raw.find(u.race).creature_id, tame = dfhack.units.isTame(u),
             adult = dfhack.units.isAdult(u), female = dfhack.units.isFemale(u),
             pet_owner_id = dfhack.units.isPet(u) and u.relationship_ids.PetOwner or nil,
             marked_for_slaughter = dfhack.units.isMarkedForSlaughter(u), x = u.pos.x, y = u.pos.y, z = u.pos.z}
      elseif kind == 'others' and not dfhack.units.isCitizen(u) and not (dfhack.units.isAnimal(u) and dfhack.units.isOwnCiv(u))
             and visible_unit(u) then
        e = {id = u.id, race = df.creature_raw.find(u.race).creature_id, hostile = dfhack.units.isDanger(u),
             visitor = dfhack.units.isVisitor and dfhack.units.isVisitor(u) or nil, x = u.pos.x, y = u.pos.y, z = u.pos.z}
      end
      if e then total = total + 1 if #r < n then r[#r + 1] = e end end
    end
  end
  if kind ~= 'citizens' and kind ~= 'animals' and kind ~= 'others' then
    return {ok = false, error_code = 'bad_arguments', error = 'kind must be citizens, animals or others'} end
  return {ok = true, kind = kind, units = r, total = total}
end

-- jobs: the fortress's job list (DF's job screen); positions only on revealed tiles
function Q.jobs()
  local n, r, total = lim(200, 500), {}, 0
  local l = df.global.world.jobs.list.next
  while l do
    local j = l.item
    total = total + 1
    if #r < n then
      local w = dfhack.job.getWorker(j)
      local b = dfhack.job.getHolder(j)
      local e = {id = j.id, job = df.job_type[j.job_type], reaction = j.reaction_name ~= '' and j.reaction_name or nil,
                 worker_id = w and w.id or nil, building_id = b and b.id or nil,
                 order_id = j.order_id ~= -1 and j.order_id or nil,
                 suspended = j.flags.suspend or nil, do_now = j.flags.do_now or nil, by_manager = j.flags.by_manager or nil,
                 ["repeat"] = j.flags["repeat"] or nil, items_attached = #j.items}
      if j.pos and j.pos.x >= 0 and revealed(j.pos.x, j.pos.y, j.pos.z) then e.x, e.y, e.z = j.pos.x, j.pos.y, j.pos.z end
      r[#r + 1] = e
    end
    l = l.next
  end
  return {ok = true, jobs = r, total = total}
end

-- orders: every manager order with all its fields and conditions
local function cond_facts(c)
  local fl = C.item_flags(c)
  return {item_type = C.item_type_name(c.item_type), item_subtype = C.subtype_id(c.item_type, c.item_subtype),
          material = C.mat_string(c.mat_type, c.mat_index), flags = #fl > 0 and fl or nil,
          reaction_class = c.reaction_class ~= '' and c.reaction_class or nil,
          reaction_product = c.has_material_reaction_product ~= '' and c.has_material_reaction_product or nil,
          tool_use = c.has_tool_use >= 0 and df.tool_uses[c.has_tool_use] or nil,
          bearing = c.metal_ore >= 0 and df.global.world.raws.inorganics.all[c.metal_ore].id or nil,
          test = df.logic_condition_type[c.compare_type], value = c.compare_val}
end
function Q.orders()
  local n, r = lim(200, 500), {}
  local spawned = {}
  local l = df.global.world.jobs.list.next
  while l do if l.item.order_id ~= -1 then spawned[l.item.order_id] = (spawned[l.item.order_id] or 0) + 1 end l = l.next end
  for _, ord in ipairs(df.global.world.manager_orders.all) do
    if #r < n then
      local w, oc = {}, {}
      for _, c in ipairs(ord.item_conditions) do w[#w + 1] = cond_facts(c) end
      for _, c in ipairs(ord.order_conditions) do oc[#oc + 1] = {order_id = c.order_id, condition = df.workquota_order_condition_type[c.condition]} end
      local mc = C.bits(ord.material_category)
      r[#r + 1] = {id = ord.id, job = df.job_type[ord.job_type], reaction = ord.reaction_name ~= '' and ord.reaction_name or nil,
                   item_type = C.item_type_name(ord.item_type), item_subtype = C.subtype_id(ord.item_type >= 0 and ord.item_type or df.job_type.attrs[ord.job_type].item, ord.item_subtype),
                   material = ord.job_type ~= df.job_type.PrepareMeal and C.mat_string(ord.mat_type, ord.mat_index) or nil,
                   meal_kind = ord.job_type == df.job_type.PrepareMeal and ord.mat_type or nil,
                   material_category = #mc > 0 and mc or nil,
                   left = ord.amount_left, total = ord.amount_total, validated = ord.status.validated, active = ord.status.active,
                   frequency = df.workquota_frequency_type[ord.frequency],
                   workshop_id = ord.workshop_id ~= -1 and ord.workshop_id or nil, max_workshops = ord.max_workshops,
                   jobs_in_progress = spawned[ord.id] or 0, item_conditions = w, order_conditions = oc}
    end
  end
  return {ok = true, orders = r, total = #df.global.world.manager_orders.all}
end

-- buildings: every building on a revealed tile (zones are the zones query)
function Q.buildings()
  local n, r, total = lim(300, 1000), {}, 0
  local want = A.type
  for _, b in ipairs(df.global.world.buildings.all) do
    if not df.building_civzonest:is_instance(b) and revealed(b.centerx, b.centery, b.z) then
      local t, st = C.building_kind(b)
      if not want or want == t or want == st then
        total = total + 1
        if #r < n then
          local zs = C.zone_ids(b)
          r[#r + 1] = {id = b.id, type = t, subtype = st, x1 = b.x1, y1 = b.y1, x2 = b.x2, y2 = b.y2, z = b.z,
                       x = b.centerx, y = b.centery, built = built(b), stage = b:getBuildStage(), max_stage = b:getMaxBuildStage(),
                       jobs = #b.jobs, zone_ids = #zs > 0 and zs or nil,
                       material = C.mat_string(b.mat_type, b.mat_index)}
        end
      end
    end
  end
  return {ok = true, buildings = r, total = total}
end

-- zones: every activity zone with its box, owner and the buildings in it
function Q.zones()
  local n, r, total = lim(300, 1000), {}, 0
  for _, z in ipairs(df.global.world.buildings.other.ACTIVITY_ZONE) do
    total = total + 1
    if #r < n then
      local bs = {}
      for _, b in ipairs(z.contained_buildings) do
        local t, st = C.building_kind(b)
        bs[#bs + 1] = {id = b.id, type = t, subtype = st, built = built(b), x = b.centerx, y = b.centery}
      end
      local tiles = 0
      pcall(function()
        if z.room.extents then
          for i = 0, z.room.width * z.room.height - 1 do if z.room.extents[i] ~= 0 then tiles = tiles + 1 end end
        end
      end)
      r[#r + 1] = {id = z.id, type = df.civzone_type[z.type], x1 = z.x1, y1 = z.y1, x2 = z.x2, y2 = z.y2, z = z.z,
                   tiles = tiles > 0 and tiles or (z.x2 - z.x1 + 1) * (z.y2 - z.y1 + 1),
                   owner = z.assigned_unit_id ~= -1 and z.assigned_unit_id or nil,
                   active = (function() local ok, v = pcall(function() return z.spec_sub_flag.active end) return ok and v or nil end)(),
                   buildings = bs}
    end
  end
  return {ok = true, zones = r, total = total}
end

-- map: revealed tiles in a box, by level. Hidden tiles are '?' in every layer and carry no other facts.
local SHAPE_CH = {EMPTY = ' ', FLOOR = '.', BOULDER = 'o', PEBBLES = ',', WALL = '#', FORTIFICATION = 'F',
                  STAIR_UP = '<', STAIR_DOWN = '>', STAIR_UPDOWN = 'X', RAMP = '^', RAMP_TOP = 'v',
                  BROOK_BED = '_', BROOK_TOP = '~', BRANCH = 'b', TRUNK_BRANCH = 't', TWIG = 'w', SAPLING = 's',
                  SHRUB = '"', ENDLESS_PIT = 'P', NONE = '!'}
local MAT_CH = {AIR = ' ', SOIL = 's', STONE = 'r', FEATURE = 'f', LAVA_STONE = 'l', MINERAL = 'm',
                FROZEN_LIQUID = 'i', CONSTRUCTION = 'c', GRASS_LIGHT = 'g', GRASS_DARK = 'g', GRASS_DRY = 'g',
                GRASS_DEAD = 'g', PLANT = 'p', HFS = 'H', CAMPFIRE = 'x', FIRE = 'x', ASHES = 'a', MAGMA = 'M',
                DRIFTWOOD = 'd', POOL = 'o', BROOK = 'k', RIVER = 'R', ROOT = 'u', TREE = 'T', MUSHROOM = 'h',
                UNDERWORLD_GATE = 'U', NONE = '!'}
function Q.map()
  local R = tonumber(A.radius) or 10
  if R < 0 then R = 0 end if R > 20 then R = 20 end
  local cx, cy, cz = tonumber(A.x), tonumber(A.y), tonumber(A.z)
  if not (cx and cy and cz) then
    local w = C.wagon()
    if not w then return {ok = false, error_code = 'bad_arguments', error = 'map needs x, y, z'} end
    cx, cy, cz = cx or w.centerx, cy or w.centery, cz or w.z
  end
  local z2 = tonumber(A.z2) or cz
  if math.abs(z2 - cz) > 4 then return {ok = false, error_code = 'bad_arguments', error = 'at most 5 levels (|z2 - z| <= 4)'} end
  local zs, ze = math.max(cz, z2), math.min(cz, z2)
  local levels, buildings, designations, liquid = {}, {}, {}, {}
  local bseen = {}
  for z = zs, ze, -1 do
    local shape, mat, light = {}, {}, {}
    for y = cy - R, cy + R do
      local s, m, l = {}, {}, {}
      for x = cx - R, cx + R do
        local fl = dfhack.maps.getTileFlags(x, y, z)
        if fl and fl.dig ~= df.tile_dig_designation.No and #designations < 500 then
          designations[#designations + 1] = {x = x, y = y, z = z, dig = df.tile_dig_designation[fl.dig], hidden = fl.hidden or nil}
        end
        if not fl or fl.hidden then s[#s + 1], m[#m + 1], l[#l + 1] = '?', '?', '?'
        else
          local tt = dfhack.maps.getTileType(x, y, z)
          local at = tt and df.tiletype.attrs[tt]
          s[#s + 1] = at and (SHAPE_CH[df.tiletype_shape[at.shape]] or '!') or '!'
          m[#m + 1] = at and (MAT_CH[df.tiletype_material[at.material]] or '!') or '!'
          l[#l + 1] = fl.subterranean and 'u' or (fl.outside and 'o' or 'i')
          if fl.flow_size > 0 and #liquid < 500 then liquid[#liquid + 1] = {x = x, y = y, z = z, depth = fl.flow_size, magma = fl.liquid_type or nil} end
          local b = dfhack.buildings.findAtTile(xyz2pos(x, y, z))
          if b and not bseen[b.id] and #buildings < 300 then
            bseen[b.id] = true
            local t, st = C.building_kind(b)
            buildings[#buildings + 1] = {id = b.id, type = t, subtype = st, x1 = b.x1, y1 = b.y1, x2 = b.x2, y2 = b.y2, z = b.z, built = built(b)}
          end
        end
      end
      shape[#shape + 1], mat[#mat + 1], light[#light + 1] = table.concat(s), table.concat(m), table.concat(l)
    end
    levels[#levels + 1] = {z = z, shape = shape, material = mat, light = light}
  end
  local function legend(t) local r = {} for k, v in pairs(t) do r[v] = r[v] and (r[v] .. '|' .. k) or k end r['?'] = 'hidden' return r end
  return {ok = true, x1 = cx - R, y1 = cy - R, x2 = cx + R, y2 = cy + R, levels = levels,
          legend = {shape = legend(SHAPE_CH), material = legend(MAT_CH), light = {u = 'subterranean', o = 'outside', i = 'inside, above ground', ['?'] = 'hidden'}},
          buildings = buildings, designations = designations, liquid = liquid,
          rows = 'levels[].shape[i] is the row y = y1 + i, character j is x = x1 + j'}
end

-- manager_order_types: what add_order accepts
function Q.manager_order_types()
  local MT = dofile(here .. 'manager_types.lua')
  local reactions = {}
  for code, rx in pairs(MT.permitted_reactions()) do
    reactions[#reactions + 1] = {reaction = code, name = rx.name, skill = rx.skill >= 0 and df.job_skill[rx.skill] or nil,
                                 buildings = MT.reaction_buildings(rx)}
  end
  table.sort(reactions, function(p, q) return p.reaction < q.reaction end)
  local mc = {}
  local m = df.job_material_category:new()
  for k, _ in pairs(m) do if type(k) == 'string' and not k:find('^UNUSED') then mc[#mc + 1] = k end end
  m:delete()
  table.sort(mc)
  local cf = {}
  local c = df.manager_order_condition_item:new()
  for _, f in ipairs({'flags1', 'flags2', 'flags3'}) do
    for k, _ in pairs(c[f]) do if type(k) == 'string' and not k:find('^UNUSED') then cf[#cf + 1] = k end end
  end
  c:delete()
  table.sort(cf)
  local its = {}
  for i, n in ipairs(df.item_type) do if i >= 0 then its[#its + 1] = n end end
  return {ok = true, job_types = MT.job_types(), reactions = reactions, material_categories = mc,
          condition_flags = cf, item_types = its}
end

-- workshop_types: every workshop/furnace type and permitted custom workshop DF can build, with its footprint and inputs
function Q.workshop_types()
  local r = {}
  local function add(name, bt, st, cu, custom_code)
    local f = dfhack.buildings.getFiltersByType({}, bt, st, cu)
    if not f then return end
    local _, w, h = dfhack.buildings.getCorrectSize(1, 1, bt, st, cu, 0)
    local inputs = {}
    for _, x in ipairs(f) do
      local e = {quantity = x.quantity or 1}
      if x.item_type and x.item_type >= 0 then e.item_type = df.item_type[x.item_type] end
      local fl = {}
      for _, k in ipairs({'flags1', 'flags2', 'flags3'}) do if x[k] then for n, v in pairs(x[k]) do if v then fl[#fl + 1] = n end end end end
      table.sort(fl)
      if #fl > 0 then e.flags = fl end
      inputs[#inputs + 1] = e
    end
    local magma = name:find('^Magma') ~= nil
    r[#r + 1] = {type = name, building_type = df.building_type[bt], w = w, h = h, inputs = inputs,
                 needs_magma = magma or nil, custom = custom_code and true or nil}
  end
  for st, n in ipairs(df.workshop_type) do if st >= 0 and n ~= 'Custom' then add(n, df.building_type.Workshop, st, -1) end end
  for st, n in ipairs(df.furnace_type) do if st >= 0 and n ~= 'Custom' then add(n, df.building_type.Furnace, st, -1) end end
  for _, id in ipairs(ent.entity_raw.workshops.permitted_building_id) do
    local def = df.global.world.raws.buildings.all[id]
    if def then
      local bt = def.building_type == df.building_type.Furnace and df.building_type.Furnace or df.building_type.Workshop
      add(def.code, bt, bt == df.building_type.Furnace and df.furnace_type.Custom or df.workshop_type.Custom, def.id, def.code)
    end
  end
  return {ok = true, workshop_types = r}
end

local fn = Q[name or '']
if not fn then out({ok = false, error_code = 'bad_arguments', error = 'unknown query ' .. tostring(name)}) return end
local ok, res = pcall(fn)
if not ok then out({ok = false, error_code = 'internal_error', error = tostring(res)}) return end
out(res)
