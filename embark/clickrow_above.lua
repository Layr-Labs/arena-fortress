-- clickrow_above.lua TEXT : find TEXT on screen and left-click the middle of the row above it
local gui = require('gui')
local needle = table.concat({...}, ' ')
local w, h = dfhack.screen.getWindowSize()
for y = 1, h - 1 do
  local row = {}
  for x = 0, w - 1 do
    local p = dfhack.screen.readTile(x, y)
    local ch = p and p.ch or 32
    row[#row + 1] = (ch >= 32 and ch <= 126) and string.char(ch) or ' '
  end
  if table.concat(row):find(needle, 1, true) then
    local x = math.floor(w / 2)
    df.global.gps.mouse_x, df.global.gps.mouse_y = x, y - 1
    pcall(function() df.global.gps.precise_mouse_x = x * df.global.gps.tile_pixel_x + 4 end)
    pcall(function() df.global.gps.precise_mouse_y = (y - 1) * df.global.gps.tile_pixel_y + 4 end)
    gui.simulateInput(dfhack.gui.getDFViewscreen(true), '_MOUSE_L')
    print('CLICKED', x, y - 1) return
  end
end
print('NOTFOUND ' .. needle)
