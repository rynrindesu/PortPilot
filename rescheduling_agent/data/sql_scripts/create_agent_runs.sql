-- Decision traces from the rescheduling agent.
--
-- Postgres already records the applied change in schedule_changes. It does not
-- record the options the agent generated and rejected, and those are the
-- evidence that a refusal was reasoned rather than a failure. The console
-- shows them, so they have to outlive the process that produced them.
--
-- The trace shape belongs to the pipeline, not the schema, so it is stored as
-- JSON. run_id is a per-process display label and restarts at RUN-0001, so the
-- primary key is a surrogate.

CREATE TABLE IF NOT EXISTS agent_runs (
    id            bigserial PRIMARY KEY,
    run_id        text        NOT NULL,
    vessel_name   text        NOT NULL,
    imo_number    text        NOT NULL,
    trigger       text        NOT NULL,
    outcome       text        NOT NULL,
    started_at    timestamptz NOT NULL,
    duration_ms   integer     NOT NULL DEFAULT 0,
    payload       jsonb       NOT NULL
);

CREATE INDEX IF NOT EXISTS agent_runs_started_at_idx ON agent_runs (started_at DESC);
CREATE INDEX IF NOT EXISTS agent_runs_vessel_idx     ON agent_runs (vessel_name, imo_number);
