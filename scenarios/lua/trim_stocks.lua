-- trim_stocks.lua <days> [drink_per_dwarf_day] [food_per_dwarf_day] : MY1's lean hand-over (docs/HARNESS-CHALLENGE.md
-- §4.1; pool/README.md "MY1"). Run after handover.lua. Cuts drink and food down to about <days> days of consumption for
-- the fort's current citizens, so an unmanaged fort runs dry around day <days> instead of carrying itself to year end.
--
--   target_drink = ceil(days * citizens * drink_rate)      default drink_rate 0.07 per dwarf-day
--   target_food  = ceil(days * citizens * food_rate)       default food_rate  0.10 per dwarf-day
--
-- ASSUMPTION (the rates): measured on the noop arm of runs/local-my1-handover-2026-10-22 (4 games, day 120 -> 336 on
-- automation-made forts, 7-23 citizens): drink fell 0.055-0.074 per citizen-day, food 0.073-0.123 (food includes
-- spoilage). The defaults are the upper end, so the stock lasts about <days> days or a little less. Migrants who arrive
-- later shorten it further; that is intended (the agent has to manage supply). Pass other rates as arguments.
--
-- Only trims, never adds: a fort already below a target keeps what it has. Counts as score.lua does (DRINK stack
-- sizes; food = the edible items of ANY_GOOD_FOOD, score_version 6: no seeds, bags or raw fish). Items in a job or built into something are never touched. Deterministic given the fort:
-- removal order is fixed (food: everything but raw plants first, so brewable plants go last; within a class, the
-- highest item id first, as embark/fort_stock.lua removes), and the last item's stack is shrunk to hit the target
-- exactly. Prints TRIM citizens=<n> drink <before>-><after> (target <t>) food <before>-><after> (target <t>).
local args = {...}
local days = tonumber(args[1])
if not days or days < 0 then qerror('usage: trim_stocks.lua <days> [drink_per_dwarf_day] [food_per_dwarf_day]') end
local drink_rate, food_rate = tonumber(args[2]) or 0.07, tonumber(args[3]) or 0.10

local cit = 0
for _, u in ipairs(df.global.world.units.active) do if dfhack.units.isCitizen(u) then cit = cit + 1 end end
local other = df.global.world.items.other
-- score_version 6: food = edible items only. ANY_GOOD_FOOD also holds seeds (including seeds planted in farm plots) and
-- empty cloth bags, about 20 of 66 "food" on MY1 fort 2001 (runs/s0-compute-2026-10-23), so recorded food never reached
-- 0 while dwarves starved. Raw fish (FISH_RAW) needs a fishery before anyone can eat it.
local EDIBLE = {}
for _, t in ipairs({'FOOD', 'MEAT', 'FISH', 'CHEESE', 'EGG', 'PLANT', 'PLANT_GROWTH'}) do EDIBLE[df.item_type[t]] = true end
local function edible(it) return EDIBLE[it:getType()] and not it.flags.rotten end
local function sum(v, keep) local n = 0 for _, it in ipairs(v) do if not keep or keep(it) then n = n + it.stack_size end end return n end
local function movable(it)
  local f = it.flags
  return not (f.in_job or f.in_building or f.construction or f.garbage_collect)
end
local function ordered(v, pred, keep)   -- removal order: class rank first (lower goes first), then highest id first
  local xs = {}
  for _, it in ipairs(v) do if movable(it) and (not keep or keep(it)) then xs[#xs + 1] = it end end
  table.sort(xs, function(p, q)
    local rp, rq = pred and pred(p) or 0, pred and pred(q) or 0
    if rp ~= rq then return rp < rq end
    return p.id > q.id
  end)
  return xs
end
local function trim(v, target, pred, keep)
  local before = sum(v, keep)
  local excess = before - target
  if excess > 0 then
    for _, it in ipairs(ordered(v, pred, keep)) do
      if excess <= 0 then break end
      if it.stack_size <= excess then excess = excess - it.stack_size; dfhack.items.remove(it)
      else it.stack_size = it.stack_size - excess; excess = 0 end
    end
  end
  return before, sum(v, keep)
end
local td = math.ceil(days * cit * drink_rate - 1e-9)   -- 1e-9: 60 * 5 * 0.07 is 21.000000000000004
local tf = math.ceil(days * cit * food_rate - 1e-9)
local d0, d1 = trim(other.DRINK, td)
-- raw plants (PLANT) are food in ANY_GOOD_FOOD and also what the still brews from: remove them last
local f0, f1 = trim(other.ANY_GOOD_FOOD, tf, function(it) return df.item_plantst:is_instance(it) and 1 or 0 end, edible)
print(('TRIM citizens=%d drink %d->%d (target %d) food %d->%d (target %d) days=%s rates=%s,%s'):format(
  cit, d0, d1, td, f0, f1, tf, tostring(days), tostring(drink_rate), tostring(food_rate)))
