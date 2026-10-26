-- common.lua: shared helpers for the facts layer's probes (loaded with dofile by observe/query/act/events.lua).
-- Hidden-information rules (#85, obs schema 5, kept for every fact and query):
--   * an item on an unrevealed tile is not known (items in containers or carried use their holder's tile);
--   * a unit is known when it is on a revealed tile and not sneaking/ambushing (isVisible and not isHidden);
--   * a report about something on an unrevealed tile is not known, unless DF put it in the announcement list;
--   * a tile's shape/material is not known while the tile is hidden.
local C = {}

C.TICKS_PER_DAY, C.TICKS_PER_YEAR = 1200, 403200

function C.now() return df.global.cur_year * C.TICKS_PER_YEAR + df.global.cur_year_tick end

function C.revealed(x, y, z)
  local fl = dfhack.maps.getTileFlags(x, y, z)
  return fl ~= nil and not fl.hidden
end

function C.seen(it)
  local x, y, z = dfhack.items.getPosition(it)
  if not x then return true end
  local fl = dfhack.maps.getTileFlags(x, y, z)
  return not (fl and fl.hidden)
end

function C.visible_unit(u) return dfhack.units.isVisible(u) and not dfhack.units.isHidden(u) end

function C.report_seen(rp)
  local ok, keep = pcall(function()
    if rp.flags.announcement then return true end
    local p = rp.pos
    if not p or p.x < 0 then return true end
    local fl = dfhack.maps.getTileFlags(p.x, p.y, p.z)
    return not (fl and fl.hidden)
  end)
  return not ok or keep
end

function C.report_tick(rp) return rp.year * C.TICKS_PER_YEAR + rp.time end

function C.built(b) return b:getBuildStage() >= b:getMaxBuildStage() end

function C.name(u) return (dfhack.df2utf(dfhack.units.getReadableName(u)):gsub(' ".-"', '')) end

function C.citizens()
  local r = {}
  for _, u in ipairs(df.global.world.units.active) do if dfhack.units.isCitizen(u) then r[#r + 1] = u end end
  return r
end

-- names of the bits set in a DF bitfield (unnamed and UNUSED bits left out)
function C.bits(bf)
  local out = {}
  if bf == nil or type(bf) == 'number' then return out end
  for k, v in pairs(bf) do
    if v == true and type(k) == 'string' and not k:find('^UNUSED') then out[#out + 1] = k end
  end
  table.sort(out)
  return out
end

-- the flags of a job_item / manager_order_condition_item (flags1..flags3), as one sorted list of names
function C.item_flags(x)
  local out = {}
  for _, f in ipairs({'flags1', 'flags2', 'flags3'}) do
    local ok, bits = pcall(function() return x[f] end)
    if ok and bits then for _, n in ipairs(C.bits(bits)) do out[#out + 1] = n end end
  end
  table.sort(out)
  return out
end

function C.mat_string(mat_type, mat_index)
  if mat_type == nil or mat_type < 0 then return nil end
  local mi = dfhack.matinfo.decode(mat_type, mat_index)
  return mi and mi:getToken() or nil
end

-- item subtype id (e.g. ITEM_WEAPON_AXE_BATTLE) for an item type + subtype index, or nil
function C.subtype_id(item_type, subtype)
  if subtype == nil or subtype < 0 or item_type == nil or item_type < 0 then return nil end
  local ok, id = pcall(function()
    local def = dfhack.items.getSubtypeDef(item_type, subtype)
    return def and def.id
  end)
  return ok and id or nil
end

function C.item_type_name(t) if t == nil or t < 0 then return nil end return df.item_type[t] end

function C.wagon()
  for _, b in ipairs(df.global.world.buildings.all) do if df.building_wagonst:is_instance(b) then return b end end
end

function C.building_kind(b)
  local t = df.building_type[b:getType()]
  local st
  local ok = pcall(function()
    if df.building_workshopst:is_instance(b) then
      st = df.workshop_type[b.type]
      if b.type == df.workshop_type.Custom and b.custom_type >= 0 then
        local def = df.global.world.raws.buildings.all[b.custom_type]
        st = def and def.code or st
      end
    elseif df.building_furnacest:is_instance(b) then
      st = df.furnace_type[b.type]
      if b.type == df.furnace_type.Custom and b.custom_type >= 0 then
        local def = df.global.world.raws.buildings.all[b.custom_type]
        st = def and def.code or st
      end
    elseif df.building_civzonest:is_instance(b) then
      st = df.civzone_type[b.type]
    end
  end)
  return t, ok and st or nil
end

-- zone ids a building lies in (DF's own building.relations: the activity zones containing it)
function C.zone_ids(b)
  local r = {}
  pcall(function() for _, z in ipairs(b.relations) do r[#r + 1] = z.id end end)
  return r
end

-- read a JSON argument (or nil)
function C.json_arg(s)
  if not s or s == '' then return nil end
  local json = require('json')
  local ok, v = pcall(json.decode, s)
  if ok then return v end
  return nil
end

return C
