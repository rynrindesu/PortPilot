-- PortPilot: remove vessel records from earlier Singapore operating days.
--
-- Run this file once in the Supabase SQL Editor after enabling pg_cron under
-- Integrations -> Cron. It creates a database-resident job; it does not make
-- any calls to OCEANS-X or to the PortPilot backend.
--
-- The application scheduler is now the primary owner of this lifecycle.
-- This optional database job is a midnight-Singapore fallback (16:00 UTC).

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
    where operational_date < (now() at time zone 'Asia/Singapore')::date
  );

  delete from pilot_assignments
  where (vessel_name, imo_number) in (
    select vessel_name, imo_number
    from vessel_state
    where operational_date < (now() at time zone 'Asia/Singapore')::date
  );

  delete from tug_assignments
  where (vessel_name, imo_number) in (
    select vessel_name, imo_number
    from vessel_state
    where operational_date < (now() at time zone 'Asia/Singapore')::date
  );

  delete from berth_allocations
  where (vessel_name, imo_number) in (
    select vessel_name, imo_number
    from vessel_state
    where operational_date < (now() at time zone 'Asia/Singapore')::date
  );

  -- Remove the legacy mirror where it exists; fresh schemas do not create it.
  if to_regclass('public.operations_vessels') is not null then
    execute $cleanup$
      delete from operations_vessels
      where (vessel_name, imo_number) in (
        select vessel_name, imo_number
        from vessel_state
        where operational_date < (now() at time zone 'Asia/Singapore')::date
      )
    $cleanup$;
  end if;

  delete from eta_history
  where (vessel_name, imo_number) in (
    select vessel_name, imo_number
    from vessel_state
    where operational_date < (now() at time zone 'Asia/Singapore')::date
  );

  delete from vessel_state
  where operational_date < (now() at time zone 'Asia/Singapore')::date;

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
  '0 16 * * *',
  $$select public.cleanup_expired_vessels();$$
);
