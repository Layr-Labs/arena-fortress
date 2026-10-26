-- step the title menu: usage  lua -f step.lua KEY [KEY...]
local gui = require('gui')
local args = {...}
for _, k in ipairs(args) do
  local s = dfhack.gui.getDFViewscreen(true)
  gui.simulateInput(s, k)
end
print('focus:', table.concat(dfhack.gui.getCurFocus(true), ','))
