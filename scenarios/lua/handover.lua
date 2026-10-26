-- handover.lua : MY1 hand-over (docs/HARNESS-CHALLENGE.md §4.1). Before the agent's first turn, turns off what kept
-- the inherited fort running by itself, so the task tests whether the agent re-establishes management:
--   * every gui/control-panel automation entry the automation arm enables (automation/commands.py CONTROL_PANEL,
--     toggles only), plus autolabor in case a player enabled it, is disabled;
--   * every repeating manager order is cancelled, the same way cancel_order removes one (act2.lua); one-shot orders,
--     buildings, stocks, farms and zones stay.
-- Prints HANDOVER disabled=<n> cancelled=<n> left=<n>.
local entries = {'autobutcher', 'autochop', 'autoclothing', 'autofarm', 'autofish', 'automilk', 'autonestbox',
                 'autoshear', 'autoslab', 'cleanowned', 'nestboxes', 'orders-sort', 'prioritize', 'seedwatch',
                 'suspendmanager', 'tailor', 'autolabor'}
local disabled = 0
for _, e in ipairs(entries) do
  local ok = pcall(dfhack.run_command_silent, 'control-panel', 'disable', e)
  if ok then disabled = disabled + 1 end
  pcall(dfhack.run_command_silent, 'disable', e)   -- plugins also answer `disable`; scripts ignore it
end
local v, cancelled = df.global.world.manager_orders.all, 0
for i = #v - 1, 0, -1 do
  if v[i].frequency ~= df.workquota_frequency_type.OneTime then v:erase(i) cancelled = cancelled + 1 end
end
print(('HANDOVER disabled=%d cancelled=%d left=%d'):format(disabled, cancelled, #v))
