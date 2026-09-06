-- Add staged/active daily lifecycle support to an existing PortPilot database.
-- Run once in the Supabase SQL editor before enabling backend automation.

alter table vessel_state
add column if not exists operational_date date;

update vessel_state
set operational_date = (current_eta at time zone 'Asia/Singapore')::date
where operational_date is null;

alter table vessel_state
alter column operational_date set not null;

alter table vessel_state
add column if not exists lifecycle_status text not null default 'active';

alter table vessel_state
drop constraint if exists vessel_state_lifecycle_status_check;

alter table vessel_state
add constraint vessel_state_lifecycle_status_check
check (lifecycle_status in ('staged', 'active'));

create index if not exists vessel_state_operational_lifecycle_idx
on vessel_state (operational_date, lifecycle_status);

-- Remove the old half-hourly ETA-based cleanup. The application scheduler
-- now performs operating-day cleanup at midnight Singapore time.
select cron.unschedule(jobid)
from cron.job
where jobname = 'portpilot-cleanup-expired-vessels';
