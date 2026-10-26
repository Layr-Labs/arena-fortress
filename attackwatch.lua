-- attackwatch.lua [since_report_id] : read-only attack detector for capture_attack.py. Prints one JSON object:
--   hostiles     visible, living, dangerous non-citizens on the map
--   invasions    [{id, active, siege, size, civ_id}] from plotinfo.invasions (no announcement exists for sieges)
--   reports      [{id, type, text}] announcements with id > since_report_id
--   last_report  highest report id seen (pass it back next call)
--   abs_tick, paused
local json = require('json')
local since = tonumber(({...})[1]) or -1
local o = {abs_tick = df.global.cur_year * 403200 + df.global.cur_year_tick, paused = df.global.pause_state}
local h = 0
for _, u in ipairs(df.global.world.units.active) do
  if not dfhack.units.isCitizen(u) and dfhack.units.isDanger(u) and not dfhack.units.isHidden(u)
     and not dfhack.units.isDead(u) then h = h + 1 end
end
o.hostiles = h
o.invasions = {}
for _, inv in ipairs(df.global.plotinfo.invasions.list) do
  o.invasions[#o.invasions + 1] = {id = inv.id, active = inv.flags.active, siege = inv.flags.siege,
                                   size = inv.size, civ_id = inv.civ_id}
end
o.reports, o.last_report = {}, since
local rep = df.global.world.status.reports
for i = 0, #rep - 1 do
  local r = rep[i]
  if r.id > since then
    o.reports[#o.reports + 1] = {id = r.id, type = df.announcement_type[r.type] or tostring(r.type),
                                 text = dfhack.df2utf(r.text):gsub('%[[^%]]*%]', ''):sub(1, 200)}
    if r.id > o.last_report then o.last_report = r.id end
  end
end
print(json.encode(o))
