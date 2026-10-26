-- invade.lua RACE N X Y Z [CIV_CODE|-] [WEAPON_SUBTYPE_ID|-] [MARK_DAYS] [WAIT_DAYS] [LEAVE_DAY]
-- Spawn N hostile RACE units at X,Y,Z (a walkable surface tile) that seek out citizens. Use as scenario setup:
-- the hostility marks live in a dfhack.timeout that is NOT saved, so inject on load rather than snapshotting
-- a spawned attack. MARK_DAYS (default 8) is how long marks/targets are re-applied; set it >= the horizon.
-- WAIT_DAYS (default 0): the party stands at the spawn point (visible, isDanger/isInvader true) and only starts
-- seeking victims after this many days, like a 53.x siege mustering at the map edge. Units are placed on
-- X, X+1, ... along row Y, skipping tiles that are not in the same walkable group as X,Y,Z. Pick X,Y,Z in the
-- fort's walkable group (block.walkable): on the scripted-y1 map the east edge is cut off by a river.
-- LEAVE_DAY (v2, LT05): on that day after the spawn the party withdraws, as a native raid does when it gives up:
-- hostility marks stop and every live raider leaves the map.
-- From research/scenario-toolkit.md (verified on DF 53.16 / DFHack 53.16-r2: 6 spear goblins killed 7 dwarves
-- in ~1100 ticks; 3 unarmed goblins died in <200). Not a native siege: no historical figures, no army.
local a = {...}
local race_id
for i,r in ipairs(df.global.world.raws.creatures.all) do if r.creature_id == a[1] then race_id = i break end end
assert(race_id, 'no race '..tostring(a[1]))
local n, x, y, z = tonumber(a[2]) or 1, tonumber(a[3]), tonumber(a[4]), tonumber(a[5])
local civ = -1
if a[6] and a[6] ~= '-' then
  for _,en in ipairs(df.global.world.entities.all) do if en.type==0 and en.entity_raw.code==a[6] then civ=en.id break end end
  local me = df.historical_entity.find(df.global.plotinfo.civ_id)
  local them = df.historical_entity.find(civ)
  for _,p in ipairs({{me, civ}, {them, me.id}}) do        -- relation 1 = war (not sufficient on its own)
    for _,st in ipairs(p[1].relations.diplomacy.state) do if st.group_id == p[2] then st.relation = 1 end end
  end
end
local wsub
if a[7] and a[7] ~= '-' then
  for i,w in ipairs(df.global.world.raws.itemdefs.weapons) do if w.id == a[7] then wsub = w.subtype end end
  assert(wsub, 'no weapon '..a[7])
end
local iron = dfhack.matinfo.find('INORGANIC:IRON')
local raw = df.creature_raw.find(race_id)
local cits = dfhack.units.getCitizens()
local cache = df.global.world.enemy_status_cache
local R = df.unit_reaction_type.ENEMY_FIGHTER
local made = {}
local function wgroup(px, py, pz) local b = dfhack.maps.getTileBlock(px, py, pz) return b and b.walkable[px % 16][py % 16] or 0 end
local g0 = wgroup(x, y, z)
assert(g0 ~= 0, 'spawn tile is not walkable')
local wait = math.floor((tonumber(a[9]) or 0) * 1200)
local px = x
for k = 1, n do
  local u = dfhack.units.create(race_id, math.random(0, #raw.caste-1))
  while px < x + 3 * n and wgroup(px, y, z) ~= g0 do px = px + 1 end
  u.pos.x, u.pos.y, u.pos.z = (wgroup(px, y, z) == g0) and px or x, y, z
  px = px + 1
  u.civ_id = civ
  if civ ~= -1 then u.flags1.active_invader = true; u.flags1.invader_origin = true end
  df.global.world.units.active:insert('#', u)
  dfhack.maps.getTileBlock(u.pos).occupancy[u.pos.x % 16][u.pos.y % 16].unit = true
  if wsub then
    local hand = -1
    for i,bp in ipairs(u.body.body_plan.body_parts) do if bp.flags.GRASP then hand = i break end end
    local it = dfhack.items.createItem(u, df.item_type.WEAPON, wsub, iron.type, iron.index, false)
    local ok = it and it[1] and dfhack.items.moveToInventory(it[1], u, df.inv_item_role_type.Weapon, hand)
    print('weapon', it and #it, 'hand', hand, 'equipped', ok)
  end
  local best, bd = nil, 1e9
  for _,d in ipairs(cits) do
    local dist = math.abs(d.pos.x-u.pos.x) + math.abs(d.pos.y-u.pos.y)
    if dist < bd then best, bd = d, dist end
  end
  if best and wait == 0 then dfhack.units.setPathGoal(u, best.pos, df.unit_path_goal.SeekFellVictim) end
  made[#made+1] = u.id
end
-- enemy_status_slot is only assigned once the game ticks: mark hostility from a tick timer,
-- every 50 ticks for 200 rounds (covers later migrants; re-targets idle invaders)
local function mark(left)
  if rawget(_G, '__invade_left') then return end   -- the party has withdrawn (LEAVE_DAY)
  for _,id in ipairs(made) do
    local u = df.unit.find(id)
    if u and not dfhack.units.isDead(u) then
      local g = u.enemy.enemy_status_slot
      for _,d in ipairs(dfhack.units.getCitizens()) do
        local ds = d.enemy.enemy_status_slot
        if g >= 0 and ds >= 0 then cache.rel_map[g][ds].ur = R; cache.rel_map[ds][g].ur = R end
      end
      if u.path.goal == df.unit_path_goal.None then
        local best, bd = nil, 1e9
        for _,d in ipairs(dfhack.units.getCitizens()) do
          local dist = math.abs(d.pos.x-u.pos.x) + math.abs(d.pos.y-u.pos.y) + 3*math.abs(d.pos.z-u.pos.z)
          if dist < bd then best, bd = d, dist end
        end
        if best then dfhack.units.setPathGoal(u, best.pos, df.unit_path_goal.SeekFellVictim) end
      end
    end
  end
  if left > 0 then dfhack.timeout(50, 'ticks', function() mark(left - 1) end) end
end
local leave = tonumber(a[10])
rawset(_G, '__invade_left', false)   -- per spawn: DFHack's Lua state outlives a fort reload
if leave then
  -- withdraw: hostility marks stop and every live raider leaves the map at once (flags1.left, the flag
  -- fix/stuck-merchants sets to remove a departed unit). Walking them back to the edge first doesn't work:
  -- checked in game 2026-10-13, DF's AI overrides the path (SeekStation) and they loiter near the fort.
  -- A raider fighting at that moment can drop the flag (checked in game: 2 of 9 on scripted-2-y2 stayed, flags
  -- cleared), so it is re-applied every 50 ticks until every spawned raider is dead or off the map (up to 3 days).
  local function withdraw(left)
    local n = 0
    for _, id in ipairs(made) do
      local u = df.unit.find(id)
      if u and not dfhack.units.isDead(u) and dfhack.units.isActive(u) then
        u.flags1.active_invader = false
        u.flags1.invader_origin = true   -- scoring still counts it as a raider until it is gone
        u.flags1.left = true
        n = n + 1
      end
    end
    if n > 0 and left > 0 then dfhack.timeout(50, 'ticks', function() withdraw(left - 1) end) end
  end
  dfhack.timeout(math.floor(leave * 1200), 'ticks', function()
    rawset(_G, '__invade_left', true)
    withdraw(72)
  end)
end
local rounds = math.floor((tonumber(a[8]) or 8) * 1200 / 50)
dfhack.timeout(wait + 1, 'ticks', function() mark(rounds) end)
print('INVADERS '..table.concat(made, ' '))
