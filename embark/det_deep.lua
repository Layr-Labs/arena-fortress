-- det_deep.lua: deep fingerprint of hidden unit state (research/determinism.md). For every active unit, walk its fields
-- (DFHack reflection) to a fixed depth and hash every number, boolean and string; pointers are followed only as
-- substructures, never hashed as addresses. Prints JSON {units: {id: hash}, fields: {id: {top-level field: hash}}} so
-- two replays' day-0 states can be compared field by field.
local MAXD, MAXV = 3, 128

local function fnv_str(h, s)
  for i = 1, #s do h = (h ~ s:byte(i)) * 0x100000001b3 end
  return h
end

local function walk(h, v, d)
  local t = type(v)
  if t == 'number' or t == 'boolean' then return fnv_str(h, tostring(v)) end
  if t == 'string' then return fnv_str(h, v) end
  if t ~= 'userdata' or d > MAXD then return h end
  local ok, kind = pcall(function() return v._kind end)
  if not ok or not kind then return h end
  if kind == 'container' then
    local n = #v
    h = fnv_str(h, 'n' .. n)
    for i = 0, math.min(n, MAXV) - 1 do
      local okv, e = pcall(function() return v[i] end)
      if okv then h = walk(h, e, d + 1) end
    end
    return h
  end
  if kind == 'struct' or kind == 'bitfield' then
    for k, e in pairs(v) do h = walk(fnv_str(h, tostring(k)), e, d + 1) end
  end
  return h
end

local units, fields = {}, {}
for _, u in ipairs(df.global.world.units.active) do
  local per = {}
  local hu = 0xcbf29ce484222325
  for k, e in pairs(u) do
    local ok, hk = pcall(walk, 0xcbf29ce484222325, e, 1)
    if ok then per[k] = string.format('%016x', hk); hu = fnv_str(hu, k .. per[k]) end
  end
  units[tostring(u.id)] = string.format('%016x', hu)
  fields[tostring(u.id)] = per
end
-- raw values of the fields that differed at load in the first test (unit 87: enemy, flags2), for every unit
local detail = {}
for _, u in ipairs(df.global.world.units.active) do
  local e = {}
  for k, v in pairs(u.enemy) do
    if type(v) == 'number' or type(v) == 'boolean' then e[k] = v
    elseif type(v) == 'userdata' then
      local ok, n = pcall(function() return #v end)
      if ok then e[k .. '#'] = n end
      local okw, w = pcall(function() return v.whole end)
      if okw and type(w) == 'number' then e[k .. '.whole'] = w end
    end
  end
  detail[tostring(u.id)] = {flags2 = u.flags2.whole, race = df.creature_raw.find(u.race).creature_id,
                            civ = u.civ_id, enemy = e}
end
print(require('json').encode({units = units, fields = fields, detail = detail}))
