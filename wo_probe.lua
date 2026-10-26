-- wo_probe.lua: dump everything relevant to manager-order validation
local function p(...) print(...) end
p('== manager orders')
for i, o in ipairs(df.global.world.manager_orders.all) do
  p(i, o.id, df.job_type[o.job_type], 'left', o.amount_left, 'total', o.amount_total,
    'validated', o.status.validated, 'active', o.status.active, 'workshop_id', o.workshop_id)
end
p('== nobles / positions (fort entity)')
local ent = df.historical_entity.find(df.global.plotinfo.group_id)
local mgr_assigned, bkp_assigned = false, false
for _, asg in ipairs(ent.positions.assignments) do
  local pos
  for _, ps in ipairs(ent.positions.own) do if ps.id == asg.position_id then pos = ps end end
  local code = pos and pos.code or '?'
  local hf = asg.histfig ~= -1 and df.historical_figure.find(asg.histfig)
  local who = hf and (dfhack.translation and dfhack.translation.translateName(hf.name) or dfhack.TranslateName(hf.name)) or 'VACANT'
  local resp = {}
  if pos then for k, v in pairs(pos.responsibilities) do if v then resp[#resp + 1] = tostring(k) end end end
  p(code, who, table.concat(resp, ','))
  if pos and pos.responsibilities.MANAGE_PRODUCTION and hf then mgr_assigned = true end
  if pos and pos.responsibilities.ACCOUNTING and hf then bkp_assigned = true end
end
p('manager assigned:', mgr_assigned, ' bookkeeper assigned:', bkp_assigned)
p('== workshops')
local ws = {}
for _, b in ipairs(df.global.world.buildings.other.WORKSHOP_ANY) do
  ws[#ws + 1] = df.workshop_type[b.type] .. '#' .. b.id .. (b:getBuildStage() < b:getMaxBuildStage() and '(unbuilt)' or '')
end
p(#ws, table.concat(ws, ' '))
p('== offices (zones) count', (function() local n=0 for _,z in ipairs(df.global.world.buildings.other.ZONE_OFFICE or {}) do n=n+1 end return n end)())
p('== stock: barrels', #df.global.world.items.other.BARREL, 'plants', #df.global.world.items.other.PLANT, 'seeds', #df.global.world.items.other.SEEDS, 'drink', #df.global.world.items.other.DRINK)
