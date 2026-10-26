-- migrant_surge.lua <reported_wealth> : make the fort attract migrants, then force a wave (LT08 setup).
-- After the two hardcoded waves, DF sizes migrant waves by the fortress wealth that the last dwarven caravan
-- reported home (the civ entity's activity_stats, "lastreport"), not by live wealth. scripted-y1's report says
-- 3,330, so `force Migrants` alone does nothing there ("The fortress attracted no migrants this season" at load,
-- and forced events are consumed silently; checked 2026-10-10). This raises the reported wealth (total and
-- `other`) and queues a Migrants timed event (as `force Migrants` does). Run it while paused, right after load:
-- the snapshot's own spring Migrants event (season tick 4087, about day 19) then also sees the raised report.
-- Measured on scripted-y1 with 100000: 19 -> 36 citizens on day 1, -> 45 by day 14.
local w = tonumber(({...})[1]) or 100000
local civ = df.historical_entity.find(df.global.plotinfo.civ_id)
if not civ or not civ.activity_stats then qerror('no civ report to raise (no caravan has reported yet)') end
local rw = civ.activity_stats.wealth
print('reported wealth before', rw.total, 'citizens', df.global.plotinfo.tasks.population)
rw.other, rw.total = rw.other + (w - rw.total), w   -- the raise goes into `other`, so the parts still sum
df.global.timed_events:insert('#', {new = true, type = df.timed_event_type.Migrants, season = df.global.cur_season,
                                    season_ticks = df.global.cur_season_tick, entity = civ, feature_ind = -1})
local pending = 0
for _, e in ipairs(df.global.timed_events) do if e.type == df.timed_event_type.Migrants then pending = pending + 1 end end
print('reported wealth after', rw.total, 'migrant events pending', pending)
