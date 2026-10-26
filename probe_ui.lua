-- print current viewscreen chain + focus strings
local gui = require('gui')
local s = dfhack.gui.getDFViewscreen(true)
print('focus:', table.concat(dfhack.gui.getCurFocus(true), ','))
local v = df.global.gview.view.child
while v do print('  vs:', df._G and tostring(v._type) or v) v = v.child end
local t = dfhack.gui.getViewscreenByType(df.viewscreen_titlest, 0)
if t then
  print('title mode:', t.mode, 'sel_subpage:', t.selected_subpage or 'n/a')
  for k, _ in pairs({menu_line_id=1, sel_menu_line=1}) do pcall(function() print(k, t[k]) end) end
end
