-- observe(): compact JSON-ish snapshot of fortress state (read-only)
local json = require('json')
local o = {}
local ok = function(name, fn) local s, v = pcall(fn) o[name] = s and v or ('ERR: ' .. tostring(v)) end
ok('year', function() return df.global.cur_year end)
ok('tick', function() return df.global.cur_year_tick end)
ok('paused', function() return df.global.pause_state end)
ok('citizens', function() local n=0 for _,u in ipairs(df.global.world.units.active) do if dfhack.units.isCitizen(u) then n=n+1 end end return n end)
ok('idle', function() local n=0 for _,u in ipairs(df.global.world.units.active) do if dfhack.units.isCitizen(u) and not u.job.current_job then n=n+1 end end return n end)
ok('jobs_open', function() local n=0 local l=df.global.world.jobs.list.next while l do n=n+1 l=l.next end return n end)
ok('manager_orders', function() return #df.global.world.manager_orders.all end)
ok('wealth_total', function() return df.global.plotinfo.tasks.wealth.total end)
ok('wealth_created', function() local w=df.global.plotinfo.tasks.wealth return w.weapons+w.armor+w.furniture+w.other+w.architecture+w.displayed end)
ok('food_count', function() local n=0 for _,it in ipairs(df.global.world.items.other.ANY_GOOD_FOOD) do n=n+it.stack_size end return n end)
ok('drink_count', function() local n=0 for _,it in ipairs(df.global.world.items.other.DRINK) do n=n+it.stack_size end return n end)
ok('announcements_last5', function()
  local r, rep = {}, df.global.world.status.reports
  for i = math.max(0, #rep-5), #rep-1 do r[#r+1] = dfhack.df2utf(rep[i].text) end
  return r end)
ok('map_dims', function() local x,y,z = dfhack.maps.getSize() return {x,y,z} end)
ok('hostiles_visible', function() local n=0 for _,u in ipairs(df.global.world.units.active) do if dfhack.units.isDanger(u) and not dfhack.units.isHidden(u) then n=n+1 end end return n end)
print(json.encode(o))
