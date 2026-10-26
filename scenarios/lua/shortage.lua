-- shortage.lua <food_fraction_to_keep> <drink_fraction_to_keep>
-- Remove each food / drink item (whole stack) with probability 1 - keep; items in a job are spared.
-- ANY_GOOD_FOOD includes raw plants, so cutting food also cuts brewables. From research/scenario-toolkit.md
-- (verified: `0.1 0` took food 101 -> 10 and drink 60 -> 0 in the start fort).
local kf, kd = tonumber(({...})[1]) or 0, tonumber(({...})[2]) or 0
local function count(v) local n=0 for _,it in ipairs(v) do n=n+it.stack_size end return n end
local o = df.global.world.items.other
print('before food', count(o.ANY_GOOD_FOOD), 'drink', count(o.DRINK))
local function cut(vec, keep)
  local items = {}
  for _,it in ipairs(vec) do items[#items+1] = it end
  for _,it in ipairs(items) do
    if not it.flags.in_job and math.random() >= keep then dfhack.items.remove(it) end
  end
end
cut(o.ANY_GOOD_FOOD, kf); cut(o.DRINK, kd)
print('after  food', count(o.ANY_GOOD_FOOD), 'drink', count(o.DRINK))
