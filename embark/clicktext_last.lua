-- clicktext_last.lua TEXT: click the LAST on-screen occurrence of TEXT (bottom row first), e.g. the bottom-bar "Embark"
local gui = require('gui')
local needle = table.concat({...}, ' ')
local w, h = dfhack.screen.getWindowSize()
for y = h - 1, 0, -1 do
  local row = {}
  for x = 0, w - 1 do
    local p = dfhack.screen.readTile(x, y)
    local ch = p and p.ch or 32
    row[#row + 1] = (ch >= 32 and ch <= 126) and string.char(ch) or ' '
  end
  local s = table.concat(row)
  local i = s:find(needle, 1, true)
  if i then
    local x = i - 1 + math.floor(#needle / 2)
    df.global.gps.mouse_x, df.global.gps.mouse_y = x, y
    pcall(function() df.global.gps.precise_mouse_x = x * df.global.gps.tile_pixel_x + 4 end)
    pcall(function() df.global.gps.precise_mouse_y = y * df.global.gps.tile_pixel_y + 4 end)
    gui.simulateInput(dfhack.gui.getDFViewscreen(true), '_MOUSE_L')
    print('CLICKED', x, y)
    return
  end
end
print('NOTFOUND ' .. needle)
