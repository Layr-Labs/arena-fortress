-- act2.lua: player-equivalent actions for harness v2 (each mirrors something the game UI does).
--   assign_manager [unit_id]          nobles screen: appoint a manager (also fills DF's responsibility cache)
--   build_workshop TYPE x y z         place a workshop; dwarves fetch a log/stone and build it
--   build_farm x y z w h              place a farm plot on soil floor; dwarves build it, then plant
--   cancel_order ID                   remove a manager order
-- Defence (research/defensive-tools.md; every memory write below is listed there with the UI action it mirrors):
--   create_squad N [unit_id ...]      military screen: create the squad, appoint its leader (militia commander), add members
--   equip_squad TEMPLATE              squad equipment: apply an entity uniform template (weapon_only|leather|metal)
--   squad_order attack [unit_id ...]  squads panel: Attack (kill list of the given or all visible hostiles)
--   squad_order station x y z         squads panel: Move/station at a tile
--   squad_order stand_down            squads panel: cancel orders
--   create_burrow x y z w h nz        burrows screen: paint a box into the 'Shelter' burrow (via quickfort #burrow,
--                                     registered as the civilian-alert burrow); done by harness2 with quickfort
--   civ_alert on|off                  DFHack gui/civ-alert button (restrict civilians to the shelter burrow)
--   build_door door|hatch x y z       place a door / hatch cover; a dwarf hauls the item and builds it
--   lock_door on|off [building_id]    door/hatch sheet: Lock / Unlock (one door, or every door and hatch)
-- Zones (v2, docs/BENCHMARK-v2.md):
--   build_wall x y z                  Build > Constructions > Wall on one floor tile (a doorway): a dwarf brings a log or
--                                     boulder and builds it (v2)
--   assign_zone ZONE_ID UNIT_ID       zone sheet: Assign (an Office or Bedroom zone to a citizen; the noble screen's
--                                     "assign office" does the same for the manager)
--   zone_at X Y Z                     read-only: the newest activity zone whose box starts at x,y,z (make_zone's id)
local json = require('json')
local a = {...}
local cmd = a[1]
local ent = df.historical_entity.find(df.global.plotinfo.group_id)
local function out(t) print(json.encode(t)) end
-- v2.2: nothing on an unrevealed tile is known to a player (the same rules as observe2.lua): items there aren't
-- counted, units there can't be targeted, and tiles there can't be built on or searched for sites
local function seen(it)
  local x, y, z = dfhack.items.getPosition(it)
  if not x then return true end
  local fl = dfhack.maps.getTileFlags(x, y, z)
  return not (fl and fl.hidden)
end
local function visible_unit(u) return dfhack.units.isVisible(u) and not dfhack.units.isHidden(u) end
local function revealed(x, y, z) local fl = dfhack.maps.getTileFlags(x, y, z) return fl and not fl.hidden end
-- every failure: a stable error_code (harness2.ERROR_HINTS), what failed, and optionally what to do (hint;
-- bench/ablate.py hints strips it). Advice goes in hint, never in error.
local function fail(code, msg, hint, extra)
  local t = extra or {}
  t.ok, t.error_code, t.error, t.hint = false, code, msg, hint
  return out(t)
end

if cmd == 'assign_manager' then
  local pos
  for _, ps in ipairs(ent.positions.own) do if ps.code == 'MANAGER' then pos = ps end end
  local asg
  for _, x in ipairs(ent.positions.assignments) do if x.position_id == pos.id then asg = x end end
  if asg.histfig ~= -1 then return fail('already_assigned', 'manager already assigned (hf ' .. asg.histfig .. ')', 'administrators.MANAGER holds it; orders need no second manager') end
  local u
  if a[2] then u = df.unit.find(tonumber(a[2])) else
    for _, x in ipairs(df.global.world.units.active) do
      if dfhack.units.isCitizen(x) and not dfhack.units.getNoblePositions(x) then u = x break end
    end
  end
  if not u or not dfhack.units.isCitizen(u) then return fail('not_a_citizen', 'no citizen with id ' .. tostring(a[2]), 'use an id from dwarves.rows') end
  if dfhack.units.getNoblePositions(u) then return fail('already_assigned', 'that dwarf already holds a position', 'pick a dwarf without positions in dwarves.rows, or omit dwarf_id') end
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
  local cit = #dfhack.units.getCitizens()
  return out({ok = true, manager = dfhack.df2utf(dfhack.units.getReadableName(u)), manager_id = u.id,
              note = pos.required_office > 0 and cit >= 20
                and ('with ' .. cit .. ' citizens the manager validates orders only from an Office zone assigned to them with a built chair in it')
                or 'orders validate within about 1 day'})

elseif cmd == 'build_workshop' then
  -- WoodFurnace is building_type.Furnace in DF; everything else in harness2.WORKSHOPS is a Workshop
  local btype, typ = df.building_type.Workshop, df.workshop_type[a[2]]
  if not typ and df.furnace_type[a[2]] then btype, typ = df.building_type.Furnace, df.furnace_type[a[2]] end
  if not typ then return fail('bad_arguments', 'unknown workshop type ' .. tostring(a[2])) end
  local x, y, z = tonumber(a[3]), tonumber(a[4]), tonumber(a[5])
  local function blocked(cx, cy)
    for dx = -1, 1 do for dy = -1, 1 do
      if not revealed(cx + dx, cy + dy, z) then
        return ('tile %d,%d,%d is not a revealed tile'):format(cx + dx, cy + dy, z), 'tile_hidden' end
      local tt = dfhack.maps.getTileType(cx + dx, cy + dy, z)
      if not tt or df.tiletype.attrs[tt].shape ~= df.tiletype_shape.FLOOR or df.tiletype.attrs[tt].material == df.tiletype_material.TREE then
        return ('tile %d,%d,%d is not open floor'):format(cx + dx, cy + dy, z), 'not_open_floor' end
      if dfhack.buildings.findAtTile(xyz2pos(cx + dx, cy + dy, z)) then
        return ('tile %d,%d,%d already has a building'):format(cx + dx, cy + dy, z), 'tile_occupied' end
    end end
  end
  local why, code = blocked(x, y)
  if why then
    local best
    for r = 1, 12 do for dx = -r, r do for dy = -r, r do
      if not best and math.max(math.abs(dx), math.abs(dy)) == r and not blocked(x + dx, y + dy) then best = {x = x + dx, y = y + dy, z = z} end
    end end end
    return fail(code, why, 'a workshop needs a free 3x3 floor centred on the site: use a W site', {nearest_free_centre = best})
  end
  -- same usability rule as observe2.lua stocks.logs_usable / boulders_usable (revealed items only)
  local function usable(v) local n = 0 for _, it in ipairs(v) do if seen(it) and not (it.flags.in_building or it.flags.forbid or it.flags.in_job) then n = n + 1 end end return n end
  if btype == df.building_type.Furnace and usable(df.global.world.items.other.BOULDER) == 0 then
    return fail('needs_stone', 'a furnace needs fire-safe material (a stone boulder), and there are 0 usable boulders', 'logs are refused; mine stone first (dig_room/dig_stairs into rock), then build')
  end
  if usable(df.global.world.items.other.WOOD) == 0 and usable(df.global.world.items.other.BOULDER) == 0 then
    return fail('no_material', 'no usable building material (0 usable logs, 0 boulders)', 'a workshop planned now is cancelled for good: enable autochop and advance until stocks.logs_usable > 0')
  end
  local b, err = dfhack.buildings.constructBuilding{type = btype, subtype = typ, pos = xyz2pos(x - 1, y - 1, z)}  -- pos is the top-left corner; x,y given as centre
  if not b then return fail('game_refused', 'the game refused the placement: ' .. tostring(err), 'use another W site') end
  return out({ok = true, id = b.id, note = 'planned; a dwarf will haul one building material (log for Carpenters/Still/Kitchen etc.) and build it, usually within ~1 day if usable logs exist'})

elseif cmd == 'build_farm' then
  local x, y, z, w, h = tonumber(a[2]), tonumber(a[3]), tonumber(a[4]), tonumber(a[5]), tonumber(a[6])
  for dx = 0, w - 1 do for dy = 0, h - 1 do
    if not revealed(x + dx, y + dy, z) then
      return fail('tile_hidden', ('tile %d,%d,%d is not a revealed tile'):format(x + dx, y + dy, z), 'use an F site, or a dug R room listed with soil') end
    local tt = dfhack.maps.getTileType(x + dx, y + dy, z)
    local at = tt and df.tiletype.attrs[tt]
    local soil = at and (at.material == df.tiletype_material.SOIL or at.material == df.tiletype_material.GRASS_LIGHT or at.material == df.tiletype_material.GRASS_DARK or at.material == df.tiletype_material.GRASS_DRY or at.material == df.tiletype_material.GRASS_DEAD)
    if not at or at.shape ~= df.tiletype_shape.FLOOR or not soil then return fail('not_soil_floor', ('tile %d,%d,%d is not soil floor'):format(x + dx, y + dy, z), 'farm plots need soil: use an F site, or a dug R room listed with soil') end
    if dfhack.buildings.findAtTile(xyz2pos(x + dx, y + dy, z)) then return fail('tile_occupied', ('tile %d,%d,%d has a building'):format(x + dx, y + dy, z), 'use another F site') end
  end end
  local b, err = dfhack.buildings.constructBuilding{type = df.building_type.FarmPlot, pos = xyz2pos(x, y, z), width = w, height = h}
  if not b then return fail('game_refused', 'the game refused the farm plot: ' .. tostring(err), 'use another F site') end
  return out({ok = true, id = b.id, note = 'farm plot placed; autofarm chooses crops if enabled; planting needs seeds and a dwarf with the planting labor'})

elseif cmd == 'cancel_order' then
  local v = df.global.world.manager_orders.all
  for i = #v - 1, 0, -1 do if v[i].id == tonumber(a[2]) then v:erase(i) return out({ok = true}) end end
  return fail('no_such_order', 'no order with id ' .. tostring(a[2]), 'use an id from orders[]')
elseif cmd == 'create_squad' then
  -- military screen, "Create squad": the first squad is led by the militia commander position (the UI offers it
  -- first). Appointing the leader fills the position assignment exactly like the nobles screen (see assign_manager).
  local want = tonumber(a[2]) or 4
  local pos, asg
  for _, ps in ipairs(ent.positions.own) do if ps.code == 'MILITIA_COMMANDER' then pos = ps end end
  for _, x in ipairs(ent.positions.assignments) do if pos and x.position_id == pos.id then asg = x end end
  if not asg then return fail('no_position', 'no militia commander position in this fortress') end
  if asg.squad_id ~= -1 and df.squad.find(asg.squad_id) then
    return fail('squad_exists', 'the fortress already has its squad (id ' .. asg.squad_id .. '); one squad is supported', 'use military.squads[0]: equip_squad, then squad_order') end
  local function eligible(u)
    return u and dfhack.units.isCitizen(u) and dfhack.units.isAdult(u) and u.military.squad_id == -1
       and not dfhack.units.getNoblePositions(u)
  end
  local picked = {}
  if a[3] then
    for i = 3, #a do
      local u = df.unit.find(tonumber(a[i]))
      if not eligible(u) then return fail('not_eligible', 'unit ' .. a[i] .. ' is not an adult citizen without a position or squad', 'use ids from dwarves.rows without positions, or give size instead') end
      picked[#picked + 1] = u
    end
  else
    -- "N best": highest combat skills (weapon skills; mining counts because a pick is a weapon), then strength
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
    return fail('already_assigned', 'the militia commander is already someone else (hf ' .. asg.histfig .. ')', 'list the current commander first in dwarf_ids, or give size') end
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
  -- leader slot (addToSquad refuses slot 0 by design): the same three writes addToSquad does for other slots
  sq.positions[0].occupant = hf.id
  lead.military.squad_id = sq.id; lead.military.squad_position = 0
  hf.entity_links:insert('#', {new = df.histfig_entity_link_squadst, entity_id = sq.entity_id, squad_id = sq.id,
                               squad_position = 0, start_year = df.global.cur_year, link_strength = 100})
  local names = {dfhack.df2utf(dfhack.units.getReadableName(lead))}
  for i = 2, #picked do
    if dfhack.military.addToSquad(picked[i].id, sq.id, -1) then names[#names + 1] = dfhack.df2utf(dfhack.units.getReadableName(picked[i])) end
  end
  return out({ok = true, squad_id = sq.id, members = names,
              note = 'squad created off duty (members keep working). Give it equipment (equip_squad) and orders (squad_order).'})

elseif cmd == 'equip_squad' then
  local sq
  for _, s in ipairs(df.global.world.squads.all) do if s.entity_id == ent.id then sq = s break end end
  if not sq then return fail('no_squad', 'the fortress has no squad', 'create_squad first') end
  local tname = ({weapon_only = 'Melee, leather armor', leather = 'Melee, leather armor', metal = 'Melee, metal armor'})[a[2]]
  local tpl
  for _, t in ipairs(ent.uniforms) do if t.name == tname then tpl = t end end
  if not tpl then return fail('game_refused', 'the fortress has no uniform template ' .. tostring(tname), 'try another uniform') end
  -- squad equipment screen, "Assign uniform": copy the template's items into every position's uniform
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
  -- what the screen does on change: ask the game to re-run equipment assignment
  local up = df.global.plotinfo.equipment.update
  up.weapon = true; up.armor = true; up.shoes = true; up.shield = true; up.helm = true; up.gloves = true; up.pants = true
  local free = 0
  for _, it in ipairs(df.global.world.items.other.WEAPON) do
    if seen(it) and not (it.flags.forbid or it.flags.in_inventory or it.flags.in_job or it.flags.trader) then free = free + 1 end
  end
  return out({ok = true, template = a[2], weapons_not_carried = free,
              note = 'uniform set; members fetch the items when the squad is on duty (an order is active). '
                  .. 'Only weapons that exist can be issued; tools held for work (picks, axes) are shared with mining/woodcutting.'})

elseif cmd == 'squad_order' then
  local sq
  for _, s in ipairs(df.global.world.squads.all) do if s.entity_id == ent.id then sq = s break end end
  if not sq then return fail('no_squad', 'the fortress has no squad', 'create_squad first') end
  local function clear() for i = #sq.orders - 1, 0, -1 do sq.orders[i]:delete() sq.orders:erase(i) end end
  local kind = a[2]
  if kind == 'stand_down' then clear() return out({ok = true, note = 'orders cleared; the squad is off duty'}) end
  local o
  if kind == 'attack' then
    local targets = {}
    if a[3] then
      for i = 3, #a do
        local u = df.unit.find(tonumber(a[i]))
        if not u or dfhack.units.isDead(u) or not visible_unit(u) or not dfhack.units.isDanger(u) then
          return fail('not_a_hostile', 'unit ' .. a[i] .. ' is not a visible living hostile', 'use ids from threats.hostiles, or omit target_ids') end
        targets[#targets + 1] = u.id
      end
    else
      for _, u in ipairs(df.global.world.units.active) do
        if dfhack.units.isDanger(u) and visible_unit(u) and not dfhack.units.isDead(u) then targets[#targets + 1] = u.id end
      end
    end
    if #targets == 0 then return fail('no_hostiles', 'no visible hostiles to attack', 'threats has no hostiles: station the squad or stand_down') end
    o = df.squad_order_kill_listst:new()
    for _, id in ipairs(targets) do o.units:insert('#', id) end
    o.title = 'Kill hostiles'
  elseif kind == 'station' then
    local x, y, z = tonumber(a[3]), tonumber(a[4]), tonumber(a[5])
    local tt = dfhack.maps.getTileType(x, y, z)
    if not tt or not dfhack.maps.getTileFlags(x, y, z) or dfhack.maps.getTileFlags(x, y, z).hidden then
      return fail('tile_hidden', 'station tile is not a revealed map tile', 'station on a known tile, e.g. map.wagon or a site') end
    local sh = df.tiletype.attrs[tt].shape
    if not (sh == df.tiletype_shape.FLOOR or sh == df.tiletype_shape.STAIR_UP or sh == df.tiletype_shape.STAIR_DOWN
            or sh == df.tiletype_shape.STAIR_UPDOWN or sh == df.tiletype_shape.RAMP or sh == df.tiletype_shape.SHRUB
            or sh == df.tiletype_shape.SAPLING or sh == df.tiletype_shape.BOULDER or sh == df.tiletype_shape.PEBBLES) then
      return fail('not_walkable', 'station tile is not walkable', 'station on a floor or stair, e.g. map.wagon or a site') end
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
      return fail('no_burrow', 'there is no civilian-alert burrow', 'create_burrow on an A site first') end
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
  if not tt or dfhack.maps.getTileFlags(x, y, z).hidden then return fail('tile_hidden', 'not a revealed tile', 'use an E site') end
  local sh = df.tiletype.attrs[tt].shape
  if kind == 'hatch' and not (sh == df.tiletype_shape.STAIR_DOWN or sh == df.tiletype_shape.STAIR_UPDOWN
                              or sh == df.tiletype_shape.RAMP_TOP or sh == df.tiletype_shape.EMPTY) then
    return fail('wrong_tile_shape', 'a hatch cover goes over a down stair, up/down stair, ramp top or open space', 'use an E site (a stair down from the surface)') end
  if kind ~= 'hatch' and sh ~= df.tiletype_shape.FLOOR then return fail('wrong_tile_shape', 'a door needs an open floor tile', 'E sites are stairs: build a hatch there, or give a floor tile') end
  if dfhack.buildings.findAtTile(xyz2pos(x, y, z)) then return fail('tile_occupied', 'tile already has a building', 'doors.list shows what is built; use another E site') end
  local free = 0
  for _, it in ipairs(df.global.world.items.other[df.item_type[itype]]) do
    if seen(it) and not (it.flags.forbid or it.flags.in_building or it.flags.in_job or it.flags.in_inventory) then free = free + 1 end
  end
  if free == 0 then return fail('no_material', 'no free ' .. (kind == 'hatch' and 'hatch cover' or 'door') .. ' item',
                                 'add_order make_' .. (kind == 'hatch' and 'hatch_cover' or 'door') ..
                                 ' first; a placement without one is cancelled by the builder') end
  local b, err = dfhack.buildings.constructBuilding{type = btype, pos = xyz2pos(x, y, z)}
  if not b then return fail('game_refused', 'the game refused the placement: ' .. tostring(err), 'use another E site') end
  return out({ok = true, id = b.id, note = 'planned; a dwarf hauls the item and builds it (usually within a day). Lock it with lock_door once built.'})

elseif cmd == 'lock_door' then
  local lock = a[2] == 'on'
  local want = a[3] and tonumber(a[3])
  local n, ids = 0, {}
  for _, b in ipairs(df.global.world.buildings.all) do
    if (df.building_doorst:is_instance(b) or df.building_hatchst:is_instance(b)) and (not want or b.id == want) then
      b.door_flags.forbidden = lock   -- the door sheet's Lock/Unlock toggle
      n = n + 1; ids[#ids + 1] = b.id
    end
  end
  if n == 0 then
    if want then return fail('no_such_door', 'no door or hatch with id ' .. want, 'use an id from doors.list') end
    return fail('no_doors', 'the fortress has no doors or hatches', 'build_door on an E site first')
  end
  return out({ok = true, locked = lock, doors = ids, note = 'unbuilt doors lock once built only if you call this again'})

elseif cmd == 'build_wall' then
  local x, y, z = tonumber(a[2]), tonumber(a[3]), tonumber(a[4])
  local tt = dfhack.maps.getTileType(x, y, z)
  local fl = dfhack.maps.getTileFlags(x, y, z)
  if not tt or fl.hidden then return fail('tile_hidden', 'not a revealed tile', 'use a D site') end
  if df.tiletype.attrs[tt].shape ~= df.tiletype_shape.FLOOR then
    return fail('wrong_tile_shape', 'a wall goes on an open floor tile', 'use a D site (a doorway)') end
  if dfhack.buildings.findAtTile(xyz2pos(x, y, z)) then return fail('tile_occupied', 'tile already has a building', 'use another D site') end
  local function usable(v) local n = 0 for _, it in ipairs(v) do if seen(it) and not (it.flags.in_building or it.flags.forbid or it.flags.in_job) then n = n + 1 end end return n end
  if usable(df.global.world.items.other.WOOD) == 0 and usable(df.global.world.items.other.BOULDER) == 0 then
    return fail('no_material', 'no usable building material (0 usable logs, 0 boulders)', 'enable autochop, or mine stone, then build')
  end
  local b, err = dfhack.buildings.constructBuilding{type = df.building_type.Construction,
                                                    subtype = df.construction_type.Wall, pos = xyz2pos(x, y, z)}
  if not b then return fail('game_refused', 'the game refused the wall: ' .. tostring(err), 'use another D site') end
  return out({ok = true, id = b.id, note = 'planned; a dwarf brings a log or boulder and builds it (usually within a day). It is permanent.'})

elseif cmd == 'assign_zone' then
  local zid, uid = tonumber(a[2]), tonumber(a[3])
  local z = zid and df.building.find(zid)
  if not z or not df.building_civzonest:is_instance(z) then
    return fail('no_such_zone', 'no zone with id ' .. tostring(a[2]), 'use an id from zones[]') end
  local kind = df.civzone_type[z.type]
  if kind ~= 'Office' and kind ~= 'Bedroom' then
    return fail('not_assignable', kind .. ' zones are shared, not assigned', 'only office and bedroom zones have an owner') end
  local u = uid and df.unit.find(uid)
  if not u or not dfhack.units.isCitizen(u) then return fail('not_a_citizen', 'no citizen with id ' .. tostring(a[3]), 'use an id from dwarves.rows') end
  if z.assigned_unit_id == u.id then return out({ok = true, zone_id = z.id, owner = u.id, note = 'already assigned to this dwarf; no change'}) end
  if not dfhack.buildings.setOwner(z, u) then return fail('game_refused', 'the game refused the assignment', 'use another zone') end
  local chair = false
  for _, b in ipairs(z.contained_buildings) do
    if df.building_chairst:is_instance(b) and b:getBuildStage() >= b:getMaxBuildStage() then chair = true end
  end
  return out({ok = true, zone_id = z.id, kind = kind:lower(), owner = u.id,
              owner_name = dfhack.df2utf(dfhack.units.getReadableName(u)),
              note = kind == 'Office' and (chair and 'the office has a built chair' or 'the office has no built chair yet') or nil})

elseif cmd == 'zone_at' then
  local x, y, z = tonumber(a[2]), tonumber(a[3]), tonumber(a[4])
  local best
  for _, zn in ipairs(df.global.world.buildings.other.ACTIVITY_ZONE) do
    if zn.x1 == x and zn.y1 == y and zn.z == z and (not best or zn.id > best.id) then best = zn end
  end
  if not best then return fail('no_such_zone', 'no zone at ' .. x .. ',' .. y .. ',' .. z) end
  return out({ok = true, zone_id = best.id, kind = df.civzone_type[best.type]})
else
  fail('internal_error', 'unknown command')
end
