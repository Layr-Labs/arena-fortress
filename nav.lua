-- drive title -> Start -> pick world -> Fortress mode, one stage per call.
-- usage: lua -f nav.lua [stage]
local gui = require('gui')
local stage = ({...})[1] or 'show'
local function focus() return table.concat(dfhack.gui.getCurFocus(true), ',') end
local function dump(scr, pat)
  for k, v in pairs(scr) do
    if type(v) ~= 'userdata' and (not pat or tostring(k):find(pat)) then print('  ', k, v) end
  end
end
local scr = dfhack.gui.getDFViewscreen(true)
print('before:', focus(), tostring(scr._type))
if stage == 'start' then
  local t = dfhack.gui.getViewscreenByType(df.viewscreen_titlest, 0)
  for i, o in ipairs(t.menu_line_id) do
    if o == df.main_choice_type.Start then t.selected = i end
  end
  gui.simulateInput(t, 'SELECT')
elseif stage == 'key' then
  for i = 2, select('#', ...) do gui.simulateInput(scr, select(i, ...)) end
elseif stage == 'dump' then
  dump(scr, select(2, ...))
end
print('after:', focus())
