-- mood.lua <skill> <type> [seed] : LT03 setup. Strikes one citizen with a strange mood of the given type and skill
-- (DFHack `strangemood --force --id <id> --type <type> --skill <skill>`, e.g. `woodcrafter fey`). strangemood refuses
-- a unit that is doing a job, so candidates are tried in a seeded order (adults without a current job first) until one
-- takes the mood. Prints MOOD <unit id> <mood> <skill>, and the `showmood` text.
local skill, mtype, seed = ({...})[1] or 'woodcrafter', ({...})[2] or 'fey', tonumber(({...})[3]) or 0
local cand = {}
for _, u in ipairs(df.global.world.units.active) do
  if dfhack.units.isCitizen(u) and dfhack.units.isAdult(u) and u.mood == -1 then cand[#cand + 1] = u end
end
table.sort(cand, function(a, b)
  local ja, jb = a.job.current_job and 1 or 0, b.job.current_job and 1 or 0
  if ja ~= jb then return ja < jb end
  return a.id < b.id
end)
local x = (seed % 2147483646) + 1   -- rotate the order by seed (same LCG as stress.lua)
local function rnd(k) x = (x * 48271) % 2147483647; return x % k end
local off = #cand > 0 and rnd(#cand) or 0
for i = 0, #cand - 1 do
  local u = cand[(i + off) % #cand + 1]
  dfhack.run_command_silent('strangemood', '--force', '--id', tostring(u.id), '--type', mtype, '--skill', skill)
  if u.mood ~= -1 then
    print(('MOOD %d %s %s'):format(u.id, df.mood_type[u.mood], skill))
    print(dfhack.run_command_silent('showmood'))
    return
  end
end
qerror('no citizen took the mood')
