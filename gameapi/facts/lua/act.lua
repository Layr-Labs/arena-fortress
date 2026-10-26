-- act.lua CMD ARGS...: player-equivalent actions for the game API v0 (each mirrors something the game UI does).
-- Copied from #85's act2.lua (origin/obs-leaks) with the advice removed: no `hint`, `note` or `nearest_free_centre`
-- fields (docs/GAME-API.md §5); derived facts that were phrased as notes are plain fields now (appoint_manager:
-- citizens + required_office; assign_zone: chair). New in v0: build_workshop for every workshop/furnace type and
-- permitted custom workshop DF allows, add_order (any manager order, validated by DFHack's workorder code), slaughter.
--   assign_manager [unit_id]          nobles screen: appoint a manager
--   build_workshop TYPE x y z         place a workshop/furnace (x,y = centre of its footprint)
--   build_farm x y z w h              place a farm plot on soil floor
--   cancel_order ID                   remove a manager order
--   add_order JSON                    queue a manager order (DFHack workorder's JSON format, one order)
--   create_squad N [unit_id ...]      military screen: create the squad
--   equip_squad TEMPLATE              squad equipment: apply an entity uniform template
--   squad_order attack [unit_id ...] | station x y z | stand_down
--   civ_alert on|off                  DFHack gui/civ-alert
--   build_door door|hatch x y z       place a door / hatch cover
--   lock_door on|off [building_id]    door sheet: Lock / Unlock
--   build_wall x y z                  Build > Constructions > Wall
--   assign_zone ZONE_ID UNIT_ID       zone sheet: Assign
--   zone_at X Y Z                     read-only: the newest activity zone whose box starts at x,y,z
--   slaughter UNIT_ID                 creature list: mark a tame animal for slaughter (unit.flags2.slaughter)
local here = debug.getinfo(1, 'S').source:sub(2):match('(.*/)') or './'
local C = dofile(here .. 'common.lua')
local json = require('json')
local a = {...}
local cmd = a[1]
local ent = df.historical_entity.find(df.global.plotinfo.group_id)
local function out(t) print(json.encode(t, {pretty = false})) end
local seen, visible_unit, revealed = C.seen, C.visible_unit, C.revealed
local function fail(code, msg, extra)
  local t = extra or {}
  t.ok, t.error_code, t.error = false, code, msg
  return out(t)
end
local function usable(v) local n = 0 for _, it in ipairs(v) do if seen(it) and not (it.flags.in_building or it.flags.forbid or it.flags.in_job) then n = n + 1 end end return n end
local function free_items(itype)
  local n = 0
  for _, it in ipairs(df.global.world.items.other[df.item_type[itype]] or {}) do
    if seen(it) and not (it.flags.forbid or it.flags.in_building or it.flags.in_job or it.flags.in_inventory or it.flags.construction) then n = n + 1 end
  end
  return n
end

-- workshop/furnace/custom type name -> building_type, subtype, custom id (or nil, error)
local function workshop_spec(name)
  if name == nil or name == 'NONE' or name == 'Custom' then return nil end
  local t = df.workshop_type[name]
  if t then return df.building_type.Workshop, t, -1 end
  t = df.furnace_type[name]
  if t then return df.building_type.Furnace, t, -1 end
  local permitted = {}
  for _, id in ipairs(ent.entity_raw.workshops.permitted_building_id) do permitted[id] = true end
  for i, def in ipairs(df.global.world.raws.buildings.all) do
    if def.code == name and permitted[def.id] then
      local bt = def.building_type == df.building_type.Furnace and df.building_type.Furnace or df.building_type.Workshop
      return bt, bt == df.building_type.Furnace and df.furnace_type.Custom or df.workshop_type.Custom, def.id
    end
  end
end

if cmd == 'assign_manager' then
  local pos
  for _, ps in ipairs(ent.positions.own) do if ps.code == 'MANAGER' then pos = ps end end
  local asg
  for _, x in ipairs(ent.positions.assignments) do if x.position_id == pos.id then asg = x end end
  if asg.histfig ~= -1 then return fail('already_assigned', 'manager already assigned (hf ' .. asg.histfig .. ')') end
  local u
  if a[2] then u = df.unit.find(tonumber(a[2])) else
    for _, x in ipairs(df.global.world.units.active) do
      if dfhack.units.isCitizen(x) and not dfhack.units.getNoblePositions(x) then u = x break end
    end
  end
  if not u or not dfhack.units.isCitizen(u) then return fail('not_a_citizen', 'no citizen with id ' .. tostring(a[2])) end
  if dfhack.units.getNoblePositions(u) then return fail('already_assigned', 'that dwarf already holds a position') end
  local hf = df.historical_figure.find(u.hist_figure_id)
  asg.histfig = hf.id; asg.histfig2 = hf.id
  hf.entity_links:insert('#', {new = df.histfig_entity_link_positionst, entity_id = ent.id,
                               assignment_id = asg.id, start_year = df.global.cur_year, link_strength = 100})
  for k, v in pairs(pos.responsibilities) do
    if v and ent.assignments_by_type[k] then
      local present = false
      for _, x in ipairs(ent.assignments_by_type[k]) do if x == asg then present = true end end
      if not present then ent.assignments_by_type[k]:insert('#', asg) end
    end
  end
  return out({ok = true, manager = C.name(u), manager_id = u.id,
              citizens = #dfhack.units.getCitizens(), required_office = pos.required_office})

elseif cmd == 'build_workshop' then
  local btype, typ, custom = workshop_spec(a[2])
  if not btype then return fail('bad_arguments', 'unknown workshop type ' .. tostring(a[2])) end
  local filters = dfhack.buildings.getFiltersByType({}, btype, typ, custom)
  if not filters then return fail('bad_arguments', 'workshop type ' .. a[2] .. ' cannot be built') end
  local x, y, z = tonumber(a[3]), tonumber(a[4]), tonumber(a[5])
  local _, w, h, cx, cy = dfhack.buildings.getCorrectSize(1, 1, btype, typ, custom, 0)
  local x1, y1 = x - cx, y - cy
  for tx = x1, x1 + w - 1 do for ty = y1, y1 + h - 1 do
    if not revealed(tx, ty, z) then return fail('tile_hidden', ('tile %d,%d,%d is not a revealed tile'):format(tx, ty, z)) end
    local tt = dfhack.maps.getTileType(tx, ty, z)
    if not tt or df.tiletype.attrs[tt].shape ~= df.tiletype_shape.FLOOR or df.tiletype.attrs[tt].material == df.tiletype_material.TREE then
      return fail('not_open_floor', ('tile %d,%d,%d is not open floor'):format(tx, ty, z)) end
    if dfhack.buildings.findAtTile(xyz2pos(tx, ty, z)) then
      return fail('tile_occupied', ('tile %d,%d,%d already has a building'):format(tx, ty, z)) end
  end end
  -- the inputs DF's build menu asks for (DFHack's default filters for the type), checked against revealed, unclaimed
  -- items: a placement without its material is cancelled for good by the builder (frozen v2 rule, generalised)
  local logs, boulders = usable(df.global.world.items.other.WOOD), usable(df.global.world.items.other.BOULDER)
  for _, f in ipairs(filters) do
    local need = f.quantity or 1
    if f.item_type and f.item_type >= 0 then
      local n = free_items(f.item_type)
      if n < need then return fail('no_material', ('needs %d free %s item(s), %d available'):format(need, df.item_type[f.item_type], n), {needs_item = df.item_type[f.item_type]}) end
    elseif f.flags2 and f.flags2.fire_safe then
      if boulders < need then return fail('needs_stone', ('needs %d fire-safe building material (stone boulders), and there are %d usable boulders'):format(need, boulders)) end
    elseif f.flags2 and f.flags2.magma_safe then
      if boulders < need then return fail('needs_stone', ('needs %d magma-safe building material (stone boulders), and there are %d usable boulders'):format(need, boulders)) end
    elseif logs + boulders < need then
      return fail('no_material', ('no usable building material (%d usable logs, %d boulders; needs %d)'):format(logs, boulders, need))
    end
  end
  local b, err = dfhack.buildings.constructBuilding{type = btype, subtype = typ, custom = custom, pos = xyz2pos(x1, y1, z),
                                                    width = w, height = h}
  if not b then return fail('game_refused', 'the game refused the placement: ' .. tostring(err)) end
  return out({ok = true, id = b.id, type = a[2], x1 = x1, y1 = y1, x2 = x1 + w - 1, y2 = y1 + h - 1, z = z})

elseif cmd == 'build_farm' then
  local x, y, z, w, h = tonumber(a[2]), tonumber(a[3]), tonumber(a[4]), tonumber(a[5]), tonumber(a[6])
  for dx = 0, w - 1 do for dy = 0, h - 1 do
    if not revealed(x + dx, y + dy, z) then
      return fail('tile_hidden', ('tile %d,%d,%d is not a revealed tile'):format(x + dx, y + dy, z)) end
    local tt = dfhack.maps.getTileType(x + dx, y + dy, z)
    local at = tt and df.tiletype.attrs[tt]
    local soil = at and (at.material == df.tiletype_material.SOIL or at.material == df.tiletype_material.GRASS_LIGHT or at.material == df.tiletype_material.GRASS_DARK or at.material == df.tiletype_material.GRASS_DRY or at.material == df.tiletype_material.GRASS_DEAD)
    if not at or at.shape ~= df.tiletype_shape.FLOOR or not soil then return fail('not_soil_floor', ('tile %d,%d,%d is not soil floor'):format(x + dx, y + dy, z)) end
    if dfhack.buildings.findAtTile(xyz2pos(x + dx, y + dy, z)) then return fail('tile_occupied', ('tile %d,%d,%d has a building'):format(x + dx, y + dy, z)) end
  end end
  local b, err = dfhack.buildings.constructBuilding{type = df.building_type.FarmPlot, pos = xyz2pos(x, y, z), width = w, height = h}
  if not b then return fail('game_refused', 'the game refused the farm plot: ' .. tostring(err)) end
  -- subterranean: the frozen tool's SURFACE warning, as the fact it was made from
  return out({ok = true, id = b.id, subterranean = dfhack.maps.getTileFlags(x, y, z).subterranean})

elseif cmd == 'cancel_order' then
  local v = df.global.world.manager_orders.all
  for i = #v - 1, 0, -1 do if v[i].id == tonumber(a[2]) then v:erase(i) return out({ok = true, order_id = tonumber(a[2])}) end end
  return fail('no_such_order', 'no order with id ' .. tostring(a[2]))

elseif cmd == 'add_order' then
  -- One manager order in DFHack workorder's JSON format ({"job", "reaction", "material_category", "item_subtype",
  -- "material", "amount_total", "frequency", "item_conditions": [...]}), created by workorder's own code
  -- (create_orders, the path `workorder <json>` takes), so DF/DFHack validate it exactly as the frozen tool did.
  -- Before that: the job must be a manager-order job type (manager_order_types) and a reaction must be one this
  -- fortress's civilisation may use.
  local spec = C.json_arg(a[2])
  if type(spec) ~= 'table' or type(spec.job) ~= 'string' then return fail('bad_arguments', 'add_order needs a JSON order with a job') end
  local jt = df.job_type[spec.job]
  if not jt then return fail('bad_arguments', 'unknown job type ' .. spec.job) end
  local MT = dofile(here .. 'manager_types.lua')
  if not MT.is_order_job(jt) then return fail('bad_arguments', 'job type ' .. spec.job .. ' is not a manager order job') end
  if spec.job == 'CustomReaction' then
    if type(spec.reaction) ~= 'string' then return fail('bad_arguments', 'job CustomReaction needs a reaction') end
    if not MT.permitted_reactions()[spec.reaction] then return fail('bad_arguments', 'unknown or not permitted reaction ' .. spec.reaction) end
  elseif spec.reaction ~= nil then
    return fail('bad_arguments', 'a reaction goes only with job CustomReaction')
  end
  local wo = reqscript('workorder')
  local new_id = df.global.world.manager_orders.manager_order_next_id
  local before = #df.global.world.manager_orders.all
  local ok, err = pcall(function()
    local orders = wo.preprocess_orders(spec)
    wo.fillin_defaults(orders)
    wo.create_orders(orders, true)
  end)
  if not ok then
    local msg = tostring(err):gsub('\n.*', '')
    return fail(msg:find('Invalid') and 'bad_arguments' or 'game_refused', 'the game refused the order: ' .. msg)
  end
  if #df.global.world.manager_orders.all == before then return fail('game_refused', 'the game refused the order: no order was created') end
  local ord
  for _, x in ipairs(df.global.world.manager_orders.all) do if x.id == new_id then ord = x end end
  return out({ok = true, order_id = ord and ord.id or nil, job = spec.job, reaction = spec.reaction,
              amount = ord and ord.amount_total or nil,
              ["repeat"] = ord and ord.frequency ~= df.workquota_frequency_type.OneTime and df.workquota_frequency_type[ord.frequency]:lower() or nil,
              conditions = ord and #ord.item_conditions or 0})

elseif cmd == 'slaughter' then
  -- the creature list's Slaughter button: sets unit.flags2.slaughter on a tame animal of the fortress; a dwarf with
  -- the butchery labor then slaughters it at a Butchers workshop (DF makes the job). DFHack's autobutcher marks
  -- animals the same way.
  local u = df.unit.find(tonumber(a[2]) or -1)
  if not u or dfhack.units.isDead(u) then return fail('no_such_unit', 'no living unit with id ' .. tostring(a[2])) end
  if not visible_unit(u) then return fail('no_such_unit', 'no living unit with id ' .. tostring(a[2])) end
  if not dfhack.units.isAnimal(u) or dfhack.units.isCitizen(u) then return fail('not_slaughterable', 'unit ' .. u.id .. ' is not an animal') end
  if not dfhack.units.isOwnCiv(u) or not dfhack.units.isTame(u) then return fail('not_slaughterable', 'unit ' .. u.id .. ' is not a tame animal of the fortress') end
  if dfhack.units.isPet(u) then return fail('not_slaughterable', 'unit ' .. u.id .. ' is a pet with an owner') end
  local was = u.flags2.slaughter
  u.flags2.slaughter = true
  return out({ok = true, unit_id = u.id, race = df.creature_raw.find(u.race).creature_id, marked = true, was_marked = was})

elseif cmd == 'create_squad' then
  local want = tonumber(a[2]) or 4
  local pos, asg
  for _, ps in ipairs(ent.positions.own) do if ps.code == 'MILITIA_COMMANDER' then pos = ps end end
  for _, x in ipairs(ent.positions.assignments) do if pos and x.position_id == pos.id then asg = x end end
  if not asg then return fail('no_position', 'no militia commander position in this fortress') end
  if asg.squad_id ~= -1 and df.squad.find(asg.squad_id) then
    return fail('squad_exists', 'the fortress already has its squad (id ' .. asg.squad_id .. '); one squad is supported') end
  local function eligible(u)
    return u and dfhack.units.isCitizen(u) and dfhack.units.isAdult(u) and u.military.squad_id == -1
       and not dfhack.units.getNoblePositions(u)
  end
  local picked = {}
  if a[3] then
    for i = 3, #a do
      local u = df.unit.find(tonumber(a[i]))
      if not eligible(u) then return fail('not_eligible', 'unit ' .. a[i] .. ' is not an adult citizen without a position or squad') end
      picked[#picked + 1] = u
    end
  else
    -- frozen tool semantics: size N picks the highest combat skills (weapon skills; mining, a pick being a weapon),
    -- then strength
    local SK = {'AXE', 'SWORD', 'SPEAR', 'MACE', 'HAMMER', 'DAGGER', 'PIKE', 'WHIP', 'CROSSBOW', 'BOW',
                'MELEE_COMBAT', 'WRESTLING', 'DODGING', 'SHIELD', 'ARMOR', 'MINING'}
    local c = {}
    for _, u in ipairs(dfhack.units.getCitizens()) do
      if eligible(u) then
        local s = 0
        for _, k in ipairs(SK) do if df.job_skill[k] then s = s + dfhack.units.getNominalSkill(u, df.job_skill[k], true) end end
        c[#c + 1] = {u = u, s = s * 10000 + u.body.physical_attrs.STRENGTH.value}
      end
    end
    table.sort(c, function(p, q) return p.s > q.s end)
    for i = 1, math.min(want, #c) do picked[i] = c[i].u end
  end
  if #picked == 0 then return fail('not_eligible', 'no eligible citizens (adults without a position or squad)') end
  if #picked > 10 then return fail('bad_arguments', 'a squad has at most 10 members') end
  local lead = picked[1]
  local hf = df.historical_figure.find(lead.hist_figure_id)
  if asg.histfig ~= -1 and asg.histfig ~= hf.id then
    return fail('already_assigned', 'the militia commander is already someone else (hf ' .. asg.histfig .. ')') end
  asg.histfig = hf.id; asg.histfig2 = hf.id
  hf.entity_links:insert('#', {new = df.histfig_entity_link_positionst, entity_id = ent.id,
                               assignment_id = asg.id, start_year = df.global.cur_year, link_strength = 100})
  for k, v in pairs(pos.responsibilities) do
    if v and ent.assignments_by_type[k] then
      local present = false
      for _, x in ipairs(ent.assignments_by_type[k]) do if x == asg then present = true end end
      if not present then ent.assignments_by_type[k]:insert('#', asg) end
    end
  end
  local sq = dfhack.military.makeSquad(asg.id)
  if not sq then return fail('game_refused', 'the game refused to create the squad') end
  sq.alias = 'Guard'
  sq.positions[0].occupant = hf.id
  lead.military.squad_id = sq.id; lead.military.squad_position = 0
  hf.entity_links:insert('#', {new = df.histfig_entity_link_squadst, entity_id = sq.entity_id, squad_id = sq.id,
                               squad_position = 0, start_year = df.global.cur_year, link_strength = 100})
  local names, ids = {C.name(lead)}, {lead.id}
  for i = 2, #picked do
    if dfhack.military.addToSquad(picked[i].id, sq.id, -1) then names[#names + 1] = C.name(picked[i]); ids[#ids + 1] = picked[i].id end
  end
  return out({ok = true, squad_id = sq.id, members = names, member_ids = ids})

elseif cmd == 'equip_squad' then
  local sq
  for _, s in ipairs(df.global.world.squads.all) do if s.entity_id == ent.id then sq = s break end end
  if not sq then return fail('no_squad', 'the fortress has no squad') end
  local tname = ({weapon_only = 'Melee, leather armor', leather = 'Melee, leather armor', metal = 'Melee, metal armor'})[a[2]]
  local tpl
  for _, t in ipairs(ent.uniforms) do if t.name == tname then tpl = t end end
  if not tpl then return fail('game_refused', 'the fortress has no uniform template ' .. tostring(tname)) end
  for _, p in ipairs(sq.positions) do
    local eq = p.equipment
    for c = 0, #eq.uniform - 1 do
      local v = eq.uniform[c]
      for i = #v - 1, 0, -1 do v[i]:delete() v:erase(i) end
      if a[2] ~= 'weapon_only' or c == df.uniform_category.weapon then
        for i = 0, #tpl.uniform_item_types[c] - 1 do
          local info = tpl.uniform_item_info[c][i]
          local spec = df.squad_uniform_spec:new()
          spec.item_type = tpl.uniform_item_types[c][i]; spec.item_subtype = tpl.uniform_item_subtypes[c][i]
          spec.material_class = info.material_class; spec.mattype = info.mattype; spec.matindex = info.matindex
          spec.color = info.item_color
          spec.indiv_choice.whole = info.indiv_choice.whole
          if c == df.uniform_category.weapon then spec.indiv_choice.melee = true end
          v:insert('#', spec)
        end
      end
    end
    eq.flags.whole = tpl.flags.whole
  end
  local up = df.global.plotinfo.equipment.update
  up.weapon = true; up.armor = true; up.shoes = true; up.shield = true; up.helm = true; up.gloves = true; up.pants = true
  local free = 0
  for _, it in ipairs(df.global.world.items.other.WEAPON) do
    if seen(it) and not (it.flags.forbid or it.flags.in_inventory or it.flags.in_job or it.flags.trader) then free = free + 1 end
  end
  return out({ok = true, template = a[2], weapons_not_carried = free})

elseif cmd == 'squad_order' then
  local sq
  for _, s in ipairs(df.global.world.squads.all) do if s.entity_id == ent.id then sq = s break end end
  if not sq then return fail('no_squad', 'the fortress has no squad') end
  local function clear() for i = #sq.orders - 1, 0, -1 do sq.orders[i]:delete() sq.orders:erase(i) end end
  local kind = a[2]
  if kind == 'stand_down' then clear() return out({ok = true, order = 'stand_down'}) end
  local o
  if kind == 'attack' then
    local targets = {}
    if a[3] then
      for i = 3, #a do
        local u = df.unit.find(tonumber(a[i]))
        if not u or dfhack.units.isDead(u) or not visible_unit(u) or not dfhack.units.isDanger(u) then
          return fail('not_a_hostile', 'unit ' .. a[i] .. ' is not a visible living hostile') end
        targets[#targets + 1] = u.id
      end
    else
      for _, u in ipairs(df.global.world.units.active) do
        if dfhack.units.isDanger(u) and visible_unit(u) and not dfhack.units.isDead(u) then targets[#targets + 1] = u.id end
      end
    end
    if #targets == 0 then return fail('no_hostiles', 'no visible hostiles to attack') end
    o = df.squad_order_kill_listst:new()
    for _, id in ipairs(targets) do o.units:insert('#', id) end
    o.title = 'Kill hostiles'
  elseif kind == 'station' then
    local x, y, z = tonumber(a[3]), tonumber(a[4]), tonumber(a[5])
    local tt = dfhack.maps.getTileType(x, y, z)
    if not tt or not dfhack.maps.getTileFlags(x, y, z) or dfhack.maps.getTileFlags(x, y, z).hidden then
      return fail('tile_hidden', 'station tile is not a revealed map tile') end
    local sh = df.tiletype.attrs[tt].shape
    if not (sh == df.tiletype_shape.FLOOR or sh == df.tiletype_shape.STAIR_UP or sh == df.tiletype_shape.STAIR_DOWN
            or sh == df.tiletype_shape.STAIR_UPDOWN or sh == df.tiletype_shape.RAMP or sh == df.tiletype_shape.SHRUB
            or sh == df.tiletype_shape.SAPLING or sh == df.tiletype_shape.BOULDER or sh == df.tiletype_shape.PEBBLES) then
      return fail('not_walkable', 'station tile is not walkable') end
    o = df.squad_order_movest:new()
    o.pos.x, o.pos.y, o.pos.z = x, y, z
    o.point_id = -1
  else
    return fail('bad_arguments', 'unknown order ' .. tostring(kind))
  end
  o.year = df.global.cur_year; o.year_tick = df.global.cur_year_tick
  local lead = df.historical_figure.find(sq.positions[0].occupant)
  o.issuer_hf = lead and lead.id or -1
  clear()
  sq.orders:insert('#', o)
  return out({ok = true, order = kind, targets = kind == 'attack' and #o.units or nil})

elseif cmd == 'civ_alert' then
  local ca = reqscript('gui/civ-alert')
  if a[2] == 'on' then
    if not ca.can_sound_alarm() and not ca.can_clear_alarm() then
      return fail('no_burrow', 'there is no civilian-alert burrow') end
    ca.sound_alarm()
  else
    ca.clear_alarm()
  end
  return out({ok = true, civilian_alert = df.global.plotinfo.alerts.civ_alert_idx ~= 0})

elseif cmd == 'build_door' then
  local kind, x, y, z = a[2], tonumber(a[3]), tonumber(a[4]), tonumber(a[5])
  local btype = kind == 'hatch' and df.building_type.Hatch or df.building_type.Door
  local itype = kind == 'hatch' and df.item_type.HATCH_COVER or df.item_type.DOOR
  local tt = dfhack.maps.getTileType(x, y, z)
  if not tt or dfhack.maps.getTileFlags(x, y, z).hidden then return fail('tile_hidden', 'not a revealed tile') end
  local sh = df.tiletype.attrs[tt].shape
  if kind == 'hatch' and not (sh == df.tiletype_shape.STAIR_DOWN or sh == df.tiletype_shape.STAIR_UPDOWN
                              or sh == df.tiletype_shape.RAMP_TOP or sh == df.tiletype_shape.EMPTY) then
    return fail('wrong_tile_shape', 'a hatch cover goes over a down stair, up/down stair, ramp top or open space') end
  if kind ~= 'hatch' and sh ~= df.tiletype_shape.FLOOR then return fail('wrong_tile_shape', 'a door needs an open floor tile') end
  if dfhack.buildings.findAtTile(xyz2pos(x, y, z)) then return fail('tile_occupied', 'tile already has a building') end
  local free = 0
  for _, it in ipairs(df.global.world.items.other[df.item_type[itype]]) do
    if seen(it) and not (it.flags.forbid or it.flags.in_building or it.flags.in_job or it.flags.in_inventory) then free = free + 1 end
  end
  if free == 0 then return fail('no_material', 'no free ' .. (kind == 'hatch' and 'hatch cover' or 'door') .. ' item') end
  local b, err = dfhack.buildings.constructBuilding{type = btype, pos = xyz2pos(x, y, z)}
  if not b then return fail('game_refused', 'the game refused the placement: ' .. tostring(err)) end
  return out({ok = true, id = b.id})

elseif cmd == 'lock_door' then
  local lock = a[2] == 'on'
  local want = a[3] and tonumber(a[3])
  local n, ids, unbuilt = 0, {}, 0
  for _, b in ipairs(df.global.world.buildings.all) do
    if (df.building_doorst:is_instance(b) or df.building_hatchst:is_instance(b)) and (not want or b.id == want) then
      b.door_flags.forbidden = lock
      n = n + 1; ids[#ids + 1] = b.id
      if not C.built(b) then unbuilt = unbuilt + 1 end
    end
  end
  if n == 0 then
    if want then return fail('no_such_door', 'no door or hatch with id ' .. want) end
    return fail('no_doors', 'the fortress has no doors or hatches')
  end
  return out({ok = true, locked = lock, doors = ids, unbuilt = unbuilt})

elseif cmd == 'build_wall' then
  local x, y, z = tonumber(a[2]), tonumber(a[3]), tonumber(a[4])
  local tt = dfhack.maps.getTileType(x, y, z)
  local fl = dfhack.maps.getTileFlags(x, y, z)
  if not tt or fl.hidden then return fail('tile_hidden', 'not a revealed tile') end
  if df.tiletype.attrs[tt].shape ~= df.tiletype_shape.FLOOR then
    return fail('wrong_tile_shape', 'a wall goes on an open floor tile') end
  if dfhack.buildings.findAtTile(xyz2pos(x, y, z)) then return fail('tile_occupied', 'tile already has a building') end
  if usable(df.global.world.items.other.WOOD) == 0 and usable(df.global.world.items.other.BOULDER) == 0 then
    return fail('no_material', 'no usable building material (0 usable logs, 0 boulders)')
  end
  local b, err = dfhack.buildings.constructBuilding{type = df.building_type.Construction,
                                                    subtype = df.construction_type.Wall, pos = xyz2pos(x, y, z)}
  if not b then return fail('game_refused', 'the game refused the wall: ' .. tostring(err)) end
  return out({ok = true, id = b.id})

elseif cmd == 'assign_zone' then
  local zid, uid = tonumber(a[2]), tonumber(a[3])
  local z = zid and df.building.find(zid)
  if not z or not df.building_civzonest:is_instance(z) then
    return fail('no_such_zone', 'no zone with id ' .. tostring(a[2])) end
  local kind = df.civzone_type[z.type]
  if kind ~= 'Office' and kind ~= 'Bedroom' then
    return fail('not_assignable', kind .. ' zones are shared, not assigned') end
  local u = uid and df.unit.find(uid)
  if not u or not dfhack.units.isCitizen(u) then return fail('not_a_citizen', 'no citizen with id ' .. tostring(a[3])) end
  local chair = false
  for _, b in ipairs(z.contained_buildings) do
    if df.building_chairst:is_instance(b) and C.built(b) then chair = true end
  end
  if z.assigned_unit_id == u.id then return out({ok = true, zone_id = z.id, kind = kind:lower(), owner = u.id, changed = false, chair = chair}) end
  if not dfhack.buildings.setOwner(z, u) then return fail('game_refused', 'the game refused the assignment') end
  return out({ok = true, zone_id = z.id, kind = kind:lower(), owner = u.id, owner_name = C.name(u), changed = true, chair = chair})

elseif cmd == 'zone_at' then
  local x, y, z = tonumber(a[2]), tonumber(a[3]), tonumber(a[4])
  local best
  for _, zn in ipairs(df.global.world.buildings.other.ACTIVITY_ZONE) do
    if zn.x1 == x and zn.y1 == y and zn.z == z and (not best or zn.id > best.id) then best = zn end
  end
  if not best then return fail('no_such_zone', 'no zone at ' .. x .. ',' .. y .. ',' .. z) end
  return out({ok = true, zone_id = best.id, kind = df.civzone_type[best.type]})

else
  fail('internal_error', 'unknown command ' .. tostring(cmd))
end
