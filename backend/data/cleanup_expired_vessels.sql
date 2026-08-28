-- PortPilot: remove vessel records after their live ETA has passed.
--
-- Run this file once in the Supabase SQL Editor after enabling pg_cron under
-- Integrations -> Cron. It creates a database-resident job; it does not make
-- any calls to OCEANS-X or to the PortPilot backend.
--
-- The job runs at minute 0 and minute 30 of every hour (UTC).

create or replace function public.cleanup_expired_vessels()
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
  deleted_vessel_count integer;
begin
  -- Delete dependent operational data first, then the live observation.
  -- schedule_changes is deliberately removed too: the project requirement is
  -- to retain no records for vessels whose ETA has passed.
  delete from schedule_changes
  where (vessel_name, imo_number) in (
    select vessel_name, imo_number
    from vessel_state
    where eta < now()
  );

  delete from pilot_assignments
  where (vessel_name, imo_number) in (
    select vessel_name, imo_number
    from vessel_state
    where eta < now()
  );

  delete from tug_assignments
  where (vessel_name, imo_number) in (
    select vessel_name, imo_number
    from vessel_state
    where eta < now()
  );

  delete from berth_allocations
  where (vessel_name, imo_number) in (
    select vessel_name, imo_number
    from vessel_state
    where eta < now()
  );

  delete from operations_vessels
  where (vessel_name, imo_number) in (
    select vessel_name, imo_number
    from vessel_state
    where eta < now()
  );

  delete from vessel_state
  where eta < now();

  get diagnostics deleted_vessel_count = row_count;
  return deleted_vessel_count;
end;
$$;

-- Re-running this file replaces the existing schedule cleanly.
select cron.unschedule(jobid)
from cron.job
where jobname = 'portpilot-cleanup-expired-vessels';

select cron.schedule(
  'portpilot-cleanup-expired-vessels',
  '0,30 * * * *',
  $$select public.cleanup_expired_vessels();$$
);
