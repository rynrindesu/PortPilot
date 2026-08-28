-- Run once in the Supabase SQL editor.

CREATE TABLE IF NOT EXISTS operations_vessels (
    vessel_name TEXT NOT NULL,
    imo_number TEXT NOT NULL,
    current_eta TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (vessel_name, imo_number)
);

CREATE TABLE IF NOT EXISTS pilot_assignments (
    assignment_id SERIAL PRIMARY KEY,
    vessel_name TEXT NOT NULL,
    imo_number TEXT NOT NULL,
    pilot_id TEXT NOT NULL,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'confirmed',
    UNIQUE (vessel_name, imo_number),
    FOREIGN KEY (vessel_name, imo_number) REFERENCES operations_vessels (vessel_name, imo_number)
);

CREATE TABLE IF NOT EXISTS tug_assignments (
    assignment_id SERIAL PRIMARY KEY,
    vessel_name TEXT NOT NULL,
    imo_number TEXT NOT NULL,
    tug_id TEXT NOT NULL,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'confirmed',
    UNIQUE (vessel_name, imo_number),
    FOREIGN KEY (vessel_name, imo_number) REFERENCES operations_vessels (vessel_name, imo_number)
);

CREATE TABLE IF NOT EXISTS berth_allocations (
    allocation_id SERIAL PRIMARY KEY,
    vessel_name TEXT NOT NULL,
    imo_number TEXT NOT NULL,
    berth_id TEXT NOT NULL,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'confirmed',
    UNIQUE (vessel_name, imo_number),
    FOREIGN KEY (vessel_name, imo_number) REFERENCES operations_vessels (vessel_name, imo_number)
);
