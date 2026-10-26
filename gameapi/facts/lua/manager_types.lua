-- manager_types.lua: what add_order accepts (shared by act.lua and query.lua's manager_order_types).
-- DF has no list of "manager order jobs" a script can read outside the work-order screen, so the set is DF's own job
-- classes: every job type of class Manufacture or Improvement, plus CustomReaction (reactions this fortress's
-- civilisation may use, from its entity raws) and the gathering/misc jobs the work-order screen offers
-- (MilkCreature, ShearCreature, SpinThread, CollectSand, CollectClay).
local M = {}
local EXTRA = {CustomReaction = true, MilkCreature = true, ShearCreature = true, SpinThread = true,
               CollectSand = true, CollectClay = true}

function M.is_order_job(jt)
  local a = df.job_type.attrs[jt]
  if not a then return false end
  return a.type == df.job_type_class.Manufacture or a.type == df.job_type_class.Improvement or EXTRA[df.job_type[jt]] == true
end

function M.job_types()
  local r = {}
  for jt, name in ipairs(df.job_type) do
    if M.is_order_job(jt) then
      local a = df.job_type.attrs[jt]
      r[#r + 1] = {job = name, caption = a.caption, class = df.job_type_class[a.type],
                   item_type = a.item >= 0 and df.item_type[a.item] or nil,
                   skill = a.skill >= 0 and df.job_skill[a.skill] or nil,
                   labor = a.labor >= 0 and df.unit_labor[a.labor] or nil}
    end
  end
  return r
end

function M.permitted_reactions()
  local ent = df.historical_entity.find(df.global.plotinfo.group_id)
  local r = {}
  for _, id in ipairs(ent.entity_raw.workshops.permitted_reaction_id) do
    local rx = df.global.world.raws.reactions.reactions[id]
    if rx then r[rx.code] = rx end
  end
  return r
end

-- where a reaction can run: building type plus workshop/furnace subtype or custom workshop code
function M.reaction_buildings(rx)
  local out = {}
  pcall(function()
    local b = rx.building
    for i = 0, #b.type - 1 do
      local bt = b.type[i]
      local name = df.building_type[bt]
      local st = b.subtype[i]
      local cu = b.custom[i]
      if cu and cu >= 0 then
        local def = df.global.world.raws.buildings.all[cu]
        name = def and def.code or name
      elseif bt == df.building_type.Workshop then name = df.workshop_type[st] or name
      elseif bt == df.building_type.Furnace then name = df.furnace_type[st] or name end
      out[#out + 1] = name
    end
  end)
  return out
end

return M
