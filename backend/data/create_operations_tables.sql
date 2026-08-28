-- Run once in the Supabase SQL editor.

CREATE TABLE IF NOT EXISTS pilot_assignments (
    assignment_id SERIAL PRIMARY KEY,
    vessel_name TEXT NOT NULL,
    imo_number TEXT NOT NULL,
    pilot_id TEXT NOT NULL,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'confirmed',
    CONSTRAINT pilot_assignments_vessel_fk FOREIGN KEY (vessel_name, imo_number)
        REFERENCES vessel_state (vessel_name, imo_number)
);

CREATE TABLE IF NOT EXISTS tug_assignments (
    assignment_id SERIAL PRIMARY KEY,
    vessel_name TEXT NOT NULL,
    imo_number TEXT NOT NULL,
    tug_id TEXT NOT NULL,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'confirmed',
    CONSTRAINT tug_assignments_vessel_fk FOREIGN KEY (vessel_name, imo_number)
        REFERENCES vessel_state (vessel_name, imo_number)
);

CREATE TABLE IF NOT EXISTS berth_allocations (
    allocation_id SERIAL PRIMARY KEY,
    vessel_name TEXT NOT NULL,
    imo_number TEXT NOT NULL,
    berth_id TEXT NOT NULL,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'confirmed',
    CONSTRAINT berth_allocations_vessel_fk FOREIGN KEY (vessel_name, imo_number)
        REFERENCES vessel_state (vessel_name, imo_number)
);

-- Audit log: one row per reschedule, so a disruption's before/after and the
-- agent's rationale are visible and verifiable, not just the final state.
CREATE TABLE IF NOT EXISTS schedule_changes (
    change_id SERIAL PRIMARY KEY,
    vessel_name TEXT NOT NULL,
    imo_number TEXT NOT NULL,
    resource_type TEXT NOT NULL,  -- 'pilot' | 'tug' | 'berth'
    resource_id TEXT NOT NULL,
    old_start_time TIMESTAMPTZ,
    old_end_time TIMESTAMPTZ,
    new_start_time TIMESTAMPTZ,
    new_end_time TIMESTAMPTZ,
    reason TEXT,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT schedule_changes_vessel_fk FOREIGN KEY (vessel_name, imo_number)
        REFERENCES vessel_state (vessel_name, imo_number)
);
