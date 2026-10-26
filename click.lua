-- click a tile: lua -f click.lua X Y   (moves mouse, sends _MOUSE_L)
local gui = require('gui')
local x, y = tonumber(({...})[1]), tonumber(({...})[2])
df.global.gps.mouse_x = x
df.global.gps.mouse_y = y
pcall(function() df.global.gps.precise_mouse_x = x * df.global.gps.tile_pixel_x + 4 end)
pcall(function() df.global.gps.precise_mouse_y = y * df.global.gps.tile_pixel_y + 4 end)
local scr = dfhack.gui.getDFViewscreen(true)
gui.simulateInput(scr, '_MOUSE_L')
print('clicked', x, y, 'focus now', table.concat(dfhack.gui.getCurFocus(true), ','))
