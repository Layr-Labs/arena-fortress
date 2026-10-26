-- det_state.lua: one JSON line of game-state fingerprints, for replay-divergence checks (research/determinism.md).
-- Each field is an FNV-1a hash over a sorted, canonical list, so two replays match field by field only if that
-- part of the state is identical: units (id, position, current job type, mood), items (id, type, position, flags),
-- jobs (id, type, position, worker), plus counts.
local function fnv(list)
  local h = 0xcbf29ce484222325
  for _, s in ipairs(list) do
    for i = 1, #s do h = (h ~ s:byte(i)) * 0x100000001b3 end
    h = (h ~ 10) * 0x100000001b3
  end
  return string.format('%016x', h)
end

local units, citizens = {}, 0
local caches, ncache = {}, {nerves = 0, bodyparts = 0, insulation = 0, inventory = 0}
for _, u in ipairs(df.global.world.units.active) do
  local f = u.flags2
  caches[#caches + 1] = ('%d:%d%d%d%d'):format(u.id, f.calculated_nerves and 1 or 0, f.calculated_bodyparts and 1 or 0,
                                               f.calculated_insulation and 1 or 0, f.calculated_inventory and 1 or 0)
  for k in pairs(ncache) do if f['calculated_' .. k] then ncache[k] = ncache[k] + 1 end end
end
table.sort(caches)
for _, u in ipairs(df.global.world.units.active) do
  local job = u.job.current_job and df.job_type[u.job.current_job.job_type] or '-'
  units[#units + 1] = ('%d:%d,%d,%d:%s:%d:%s'):format(u.id, u.pos.x, u.pos.y, u.pos.z, job, u.mood,
                                                      dfhack.units.isDead(u) and 'd' or 'a')
  if dfhack.units.isCitizen(u) then citizens = citizens + 1 end
end
table.sort(units)

local items = {}
for _, it in ipairs(df.global.world.items.all) do
  local x, y, z = dfhack.items.getPosition(it)
  items[#items + 1] = ('%d:%s:%s,%s,%s:%d'):format(it.id, df.item_type[it:getType()], x or '-', y or '-', z or '-',
                                                    it.flags.whole & 0xffffffff)
end
table.sort(items)

local jobs = {}
local link = df.global.world.jobs.list.next
while link do
  local j = link.item
  if j then
    local w = dfhack.job.getWorker(j)
    jobs[#jobs + 1] = ('%d:%s:%d,%d,%d:%s'):format(j.id, df.job_type[j.job_type], j.pos.x, j.pos.y, j.pos.z, w and w.id or '-')
  end
  link = link.next
end
table.sort(jobs)

print(require('json').encode({
  abs_tick = df.global.cur_year * 403200 + df.global.cur_year_tick,
  units_n = #units, citizens = citizens, items_n = #items, jobs_n = #jobs,
  reports_n = #df.global.world.status.reports, item_next_id = df.global.item_next_id,
  unit_next_id = df.global.unit_next_id, job_next_id = df.global.job_next_id,
  units = fnv(units), items = fnv(items), jobs = fnv(jobs),
  caches = fnv(caches), cache_counts = ncache,   -- lazily computed unit caches (research/determinism.md)
}))
