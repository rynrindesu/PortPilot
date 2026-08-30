-- Run once in the Supabase SQL editor before deploying the ETA-state code.
-- It preserves the old live ETA as both the original and current ETA.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'vessel_state' AND column_name = 'eta'
    ) AND NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'vessel_state' AND column_name = 'current_eta'
    ) THEN
        ALTER TABLE vessel_state RENAME COLUMN eta TO current_eta;
    END IF;
END $$;

ALTER TABLE vessel_state
    ADD COLUMN IF NOT EXISTS original_eta TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS previous_eta TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS eta_source TEXT,
    ADD COLUMN IF NOT EXISTS last_eta_received_at TIMESTAMPTZ;

UPDATE vessel_state
SET original_eta = current_eta
WHERE original_eta IS NULL;

ALTER TABLE vessel_state
    ALTER COLUMN vessel_name SET NOT NULL,
    ALTER COLUMN imo_number SET NOT NULL,
    ALTER COLUMN original_eta SET NOT NULL,
    ALTER COLUMN current_eta SET NOT NULL;

-- All tables identify a vessel with this pair. Replace the old single-column
-- primary key with the composite identity used by every foreign key.
DO $$
DECLARE
    existing_primary_key TEXT;
BEGIN
    SELECT conname
    INTO existing_primary_key
    FROM pg_constraint
    WHERE conrelid = 'vessel_state'::regclass
      AND contype = 'p';

    IF existing_primary_key IS NOT NULL THEN
        EXECUTE format(
            'ALTER TABLE vessel_state DROP CONSTRAINT %I',
            existing_primary_key
        );
    END IF;

    ALTER TABLE vessel_state
        ADD CONSTRAINT vessel_state_pkey
        PRIMARY KEY (vessel_name, imo_number);
END $$;

CREATE TABLE IF NOT EXISTS eta_history (
    eta_event_id BIGSERIAL PRIMARY KEY,
    vessel_name TEXT NOT NULL,
    imo_number TEXT NOT NULL,
    previous_eta TIMESTAMPTZ NOT NULL,
    reported_eta TIMESTAMPTZ NOT NULL,
    source TEXT NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT eta_history_vessel_fk FOREIGN KEY (vessel_name, imo_number)
        REFERENCES vessel_state (vessel_name, imo_number)
);

CREATE INDEX IF NOT EXISTS eta_history_vessel_received_idx
    ON eta_history (vessel_name, imo_number, received_at DESC);
