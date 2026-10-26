-- dump the rendered text grid (works in PRINT_MODE:TEXT) to see what screen shows
local w, h = dfhack.screen.getWindowSize()
local out = {}
for y = 0, h - 1 do
  local row = {}
  for x = 0, w - 1 do
    local p = dfhack.screen.readTile(x, y)
    local ch = p and p.ch or 32
    if ch < 32 or ch > 126 then ch = 32 end
    row[#row + 1] = string.char(ch)
  end
  local s = table.concat(row):gsub('%s+$', '')
  if #s > 0 then out[#out + 1] = string.format('%02d|%s', y, s) end
end
print(w .. 'x' .. h)
print(table.concat(out, '\n'))
