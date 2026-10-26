-- stress.lua <N> <stress> <longterm_stress> [seed] : LT04 setup. Sets N citizens' personality.stress and
-- .longterm_stress (BENCHMARK-v1 §LT04). The N are drawn with `seed` (default: the N with the lowest unit ids,
-- i.e. the founders), so a seeded run picks the same dwarves every time. Prints the chosen ids and their stress
-- category before and after.
-- Stress in DF 53: personality.stress is the short-term level (category 0 = "haggard" at >= 100000 or so,
-- positive is bad); longterm_stress builds slowly from it and sets how fast it decays.
local n, s, l, seed = tonumber(({...})[1]) or 5, tonumber(({...})[2]) or 60000, tonumber(({...})[3]) or 100000,
                      tonumber(({...})[4])
local cit = {}
for _, u in ipairs(df.global.world.units.active) do
  if dfhack.units.isCitizen(u) and dfhack.units.isAdult(u) and u.status.current_soul then cit[#cit + 1] = u end
end
table.sort(cit, function(a, b) return a.id < b.id end)
if seed then   -- Fisher-Yates with a small LCG, so the pick doesn't depend on Lua's math.random state
  local x = seed % 2147483647
  local function rnd(k) x = (x * 48271) % 2147483647; return x % k + 1 end
  for i = #cit, 2, -1 do local j = rnd(i); cit[i], cit[j] = cit[j], cit[i] end
end
local ids = {}
for i = 1, math.min(n, #cit) do
  local u = cit[i]
  local p = u.status.current_soul.personality
  local before = dfhack.units.getStressCategory(u)
  p.stress, p.longterm_stress = s, l
  ids[#ids + 1] = ('%d:%d->%d'):format(u.id, before, dfhack.units.getStressCategory(u))
end
print('STRESSED ' .. table.concat(ids, ' '))
