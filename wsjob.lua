-- wsjob.lua <workshop_id> <job_type> [reaction] : queue a job directly at a workshop (what the
-- workshop "Add job" menu does), bypassing manager orders. Uses dfhack.job helpers.
local a = {...}
local b = df.building.find(tonumber(a[1]))
if not b then qerror('no building ' .. a[1]) end
local job = df.job:new()
job.job_type = df.job_type[a[2]]
if a[3] then job.reaction_name = a[3] end
job.pos = xyz2pos(b.centerx, b.centery, b.z)
job.mat_type = -1; job.mat_index = -1
job.flags.repeat_ = false
dfhack.job.linkIntoWorld(job, true)
local ref = df.general_ref_building_holderst:new(); ref.building_id = b.id
job.general_refs:insert('#', ref)
b.jobs:insert('#', job)
-- material requirements come from the job definition; let DF fill reagents
print('queued', a[2], a[3] or '', 'job id', job.id, 'ws jobs now', #b.jobs)
