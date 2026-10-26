-- wo_lib.lua: helpers for the work-order root-cause tests. Usage: lua -f wo_lib.lua <action> [args]
local a = {...}
local act = a[1]
local ent = df.historical_entity.find(df.global.plotinfo.group_id)
local function citizens() local t={} for _,u in ipairs(df.global.world.units.active) do if dfhack.units.isCitizen(u) then t[#t+1]=u end end return t end

if act == 'assign_manager' then
  -- put the first non-leader citizen into the MANAGER position (what the nobles screen does)
  local pos_id
  for _, ps in ipairs(ent.positions.own) do if ps.code == 'MANAGER' then pos_id = ps.id end end
  for _, asg in ipairs(ent.positions.assignments) do
    if asg.position_id == pos_id then
      local u = citizens()[1]
      local hf = df.historical_figure.find(u.hist_figure_id)
      asg.histfig = hf.id; asg.histfig2 = hf.id
      local link = df.histfig_entity_link_positionst:new()
      link.entity_id = ent.id; link.assignment_id = asg.id; link.start_year = df.global.cur_year; link.link_strength = 100
      hf.entity_links:insert('#', link)
      print('manager <-', dfhack.units.getReadableName(u))
    end
  end
elseif act == 'workshop' then
  -- place + instantly finish a workshop of given type at x,y,z (build-now completes construction)
  local typ, x, y, z = df.workshop_type[a[2]], tonumber(a[3]), tonumber(a[4]), tonumber(a[5])
  local bld, err = dfhack.buildings.constructBuilding{type=df.building_type.Workshop, subtype=typ, pos=xyz2pos(x,y,z)}
  print('construct', a[2], bld and bld.id or ('FAIL '..tostring(err)))
elseif act == 'orders' then
  for _, o in ipairs(df.global.world.manager_orders.all) do
    print(df.job_type[o.job_type], o.reaction_name ~= '' and o.reaction_name or '', 'left', o.amount_left, '/', o.amount_total, 'validated', o.status.validated, 'active', o.status.active)
  end
  local n = 0 local l = df.global.world.jobs.list.next
  while l do local j=l.item if j.flags.by_manager then n=n+1 end l=l.next end
  print('jobs spawned by manager:', n)
elseif act == 'counts' then
  local d=0 for _,it in ipairs(df.global.world.items.other.DRINK) do d=d+it.stack_size end
  local beds=#df.global.world.items.other.BED
  print('drink', d, 'beds', beds, 'barrels', #df.global.world.items.other.BARREL)
end
