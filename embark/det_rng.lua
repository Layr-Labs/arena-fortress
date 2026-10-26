-- det_rng.lua read | seed N : DF's main Mersenne Twister state (g_src/random.cpp), for determinism experiments
-- (research/determinism.md).
--
-- DF 53.16 seeds buffer 0 from GetTickCount() (gettimeofday, ms) in mt_init() at startup, and a save doesn't restore
-- it, so every load plays with a different random stream. dwarfort is non-PIE and exports the state as dynamic
-- symbols (needed by libg_src_lib.so), so the addresses below are fixed for the 53.16 classic Linux binary:
--   mt_buffer  0x24d7560  uint32_t[10][624]     mt_index 0x24dd700  int32_t[10] (byte offset into the buffer)
--   mt_virtual_buffer 0x24dd6e0, mt_cur_buffer 0x24dd6e2  int16_t
-- (`nm -D dwarfort | grep mt_`). Not mapped by DFHack's df-structures, so this script uses raw pointers.
--   read    print the state's fingerprint as JSON
--   seed N  refill buffer 0 with mt_init's recurrence from seed N and reset its index (DF twists on the next draw),
--           then print the new fingerprint. Only call it while the game is paused at the top level (mt_cur_buffer 0).
local args = {...}
local MT_LEN, NBUF = 624, 10
local A_BUF, A_IDX, A_VIRT, A_CUR = 0x24d7560, 0x24dd700, 0x24dd6e0, 0x24dd6e2

local function u32(addr) return df.reinterpret_cast('uint32_t', addr) end
local function i32(addr) return df.reinterpret_cast('int32_t', addr) end
local function i16(addr) return df.reinterpret_cast('int16_t', addr) end

local function word(b, i) return u32(A_BUF + (b * MT_LEN + i) * 4) end

local function fingerprint()
  local h = 0xcbf29ce484222325
  for i = 0, MT_LEN - 1 do
    h = ((h ~ word(0, i).value) * 0x100000001b3) & 0xffffffffffffffff
  end
  local idx = {}
  for b = 0, NBUF - 1 do idx[#idx + 1] = i32(A_IDX + b * 4).value end
  local hall = 0xcbf29ce484222325   -- every buffer, for state outside buffer 0
  for b = 0, NBUF - 1 do for i = 0, MT_LEN - 1 do hall = (hall ~ word(b, i).value) * 0x100000001b3 end end
  return {cur = i16(A_CUR).value, virt = i16(A_VIRT).value, index0 = idx[1], indexes = idx,
          all_fnv = string.format('%016x', hall),
          buf0_fnv = string.format('%016x', h), buf0_head = {word(0, 0).value, word(0, 1).value, word(0, 2).value},
          abs_tick = df.global.cur_year * 403200 + df.global.cur_year_tick}
end

local cmd = args[1] or 'read'
if cmd == 'seed' then
  local seed = math.tointeger(tonumber(args[2])) or error('usage: det_rng.lua seed N')
  local cur = i16(A_CUR).value
  if cur ~= 0 then qerror('mt_cur_buffer is ' .. cur .. ', not 0: not at the top level') end
  local x = seed & 0xffffffff
  word(0, 0).value = x
  for i = 1, MT_LEN - 1 do
    x = (1812433253 * (x ~ (x >> 30)) + i) & 0xffffffff
    word(0, i).value = x
  end
  i32(A_IDX).value = MT_LEN * 4
end
local f = fingerprint()
assert(f.index0 >= 0 and f.index0 <= MT_LEN * 4 and f.index0 % 4 == 0, 'mt_index[0] out of range: wrong addresses?')
print(require('json').encode(f))
