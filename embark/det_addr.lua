-- det_addr.lua: heap addresses of game objects, to test whether anything could iterate in address order differently
-- between replays (research/determinism.md). Prints JSON {units, items, buildings, jobs: fnv of sorted "id:address"},
-- plus the first few unit addresses and whether units sorted by address keep id order.
local function fnv(list)
  local h = 0xcbf29ce484222325
  for _, s in ipairs(list) do for i = 1, #s do h = (h ~ s:byte(i)) * 0x100000001b3 end end
  return string.format('%016x', h)
end
local function addrs(vec, idf)
  local l, pairs_ = {}, {}
  for _, o in ipairs(vec) do
    local _, a = df.sizeof(o)
    l[#l + 1] = ('%d:%x'):format(idf(o), a)
    pairs_[#pairs_ + 1] = {idf(o), a}
  end
  table.sort(l)
  table.sort(pairs_, function(x, y) return x[2] < y[2] end)
  local monotone = true
  for i = 2, #pairs_ do if pairs_[i][1] < pairs_[i - 1][1] then monotone = false end end
  return fnv(l), l, monotone
end
local w = df.global.world
local u, ul, umono = addrs(w.units.active, function(o) return o.id end)
local it, _, imono = addrs(w.items.all, function(o) return o.id end)
local b, _, bmono = addrs(w.buildings.all, function(o) return o.id end)
print(require('json').encode({units = u, items = it, buildings = b, units_head = {ul[1], ul[2], ul[3]},
                              id_order_is_address_order = {units = umono, items = imono, buildings = bmono}}))
