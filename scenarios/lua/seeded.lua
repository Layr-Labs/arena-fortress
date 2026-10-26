-- seeded.lua SEED SCRIPT [ARGS...]
-- Run a setup script with math.random seeded (BENCHMARK-v1 §2.1 setup seeding). Train-split scenarios use it as
-- ["lua", "-f", "scenarios/lua/seeded.lua", "{seed}", "scenarios/lua/<script>.lua", ...]; smoke.py fills in {seed}
-- (setup_seed + k). The scripts themselves are unchanged, so test-split task hashes stay as they were.
-- Prints "setup_seed N" last, so the seed is in the summary row's scenario_setup (its last 200 characters).
local a = {...}
local seed = assert(tonumber(a[1]), 'seeded.lua: SEED must be a number, got '..tostring(a[1]))
local script = assert(a[2], 'seeded.lua: no SCRIPT')
math.randomseed(seed)
local f = assert(loadfile(script))
f(table.unpack(a, 3))
print('setup_seed '..seed)
