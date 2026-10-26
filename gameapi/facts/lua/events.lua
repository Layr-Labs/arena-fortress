-- events.lua SINCE_TICK [LIMIT] [SINCE_ID]: DF's reports (the announcement/report log) after a tick, oldest first.
-- Each: {id, tick, type (df.announcement_type), text, announcement (DF put it in the announcement list),
-- repeat_count, x, y, z (revealed tiles only)}. Continuation lines are joined to their report. Hidden-information
-- rule as #85's report_seen: reports about unrevealed tiles stay out unless they are announcements.
-- At most LIMIT (default 200, max 1000): when more match, the newest LIMIT are returned and `dropped` counts the rest.
local here = debug.getinfo(1, 'S').source:sub(2):match('(.*/)') or './'
local C = dofile(here .. 'common.lua')
local json = require('json')
local a = {...}
local since = tonumber(a[1]) or 0
local limit = math.max(1, math.min(1000, tonumber(a[2]) or 200))
local since_id = tonumber(a[3]) or -1
local rep = df.global.world.status.reports
local picked = {}
local i = #rep - 1
while i >= 0 do
  local rp = rep[i]
  local t = C.report_tick(rp)
  if t <= since or rp.id <= since_id then break end
  picked[#picked + 1] = i
  i = i - 1
end
-- picked is newest first; walk oldest first, joining continuations onto the report they continue
local evs = {}
for k = #picked, 1, -1 do
  local rp = rep[picked[k]]
  local text = dfhack.df2utf(rp.text):gsub('%[[^%]]*%]', '')
  if rp.flags.continuation and #evs > 0 then
    evs[#evs].text = evs[#evs].text .. ' ' .. text
  elseif C.report_seen(rp) then
    local e = {id = rp.id, tick = C.report_tick(rp), type = df.announcement_type[rp.type] or tostring(rp.type), text = text,
               announcement = rp.flags.announcement, repeat_count = rp.repeat_count > 1 and rp.repeat_count or nil}
    local p = rp.pos
    if p and p.x >= 0 and C.revealed(p.x, p.y, p.z) then e.x, e.y, e.z = p.x, p.y, p.z end
    evs[#evs + 1] = e
  else
    evs[#evs + 1] = {skip = true, text = ''}   -- placeholder so a hidden report's continuation lines are dropped too
  end
end
local r = {}
for _, e in ipairs(evs) do if not e.skip then r[#r + 1] = e end end
local dropped = 0
if #r > limit then
  dropped = #r - limit
  local cut = {}
  for k = dropped + 1, #r do cut[#cut + 1] = r[k] end
  r = cut
end
print(json.encode({ok = true, events = r, dropped = dropped, now = C.now()}, {pretty = false}))
