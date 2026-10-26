-- legacy_events.lua SINCE_TICK [MAX] : DF's report stream (announcements and combat/job reports the player sees)
-- since an absolute tick, oldest first, at most MAX (default 200, the newest kept). Used by the legacy facts adapter
-- (gameapi/server/adapter.py) until gameapi/facts provides events(). Prints {"events": [...], "truncated": bool}.
local json = require('json')
local args = {...}
local since = tonumber(args[1]) or 0
local max = tonumber(args[2]) or 200
local rep = df.global.world.status.reports
local out, truncated = {}, false
for i = #rep - 1, 0, -1 do
  local r = rep[i]
  local t = r.year * 403200 + r.time
  if t < since then break end
  if #out >= max then truncated = true break end
  local ok, text = pcall(function() return dfhack.df2utf(r.text) end)
  table.insert(out, 1, {id = r.id, tick = t, type = df.announcement_type[r.type] or tostring(r.type),
                        text = ok and text:gsub('%[[^%]]*%]', '') or '?', continuation = r.flags.continuation or false})
end
print(json.encode({events = out, truncated = truncated}))
