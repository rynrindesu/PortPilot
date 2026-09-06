```md
# Scheduling Pipeline Overview

## `initialize_database.py`

`initialize_database.py` calls the OCEANS-X API and saves the first batch of vessel observations into `vessel_state`.

Run this script on an empty database at the start of a daily test cycle. These initial vessel states become the live baseline used by later monitoring polls.

After saving vessel states, the script generates and saves simulated operational schedules for each vessel. It populates:

- `berth_allocations`
- `tug_assignments`
- `pilot_assignments`
- `resources`

The `resources` table is the master list of active berth, tug, and pilot resources available for that day.

## `monitoring_pipeline.py`

`monitoring_pipeline.py` calls the OCEANS-X API to simulate a recurring monitoring poll, such as one executed every hour.

It compares each received ETA with the vessel's current stored ETA. When an ETA change is detected, the pipeline generates schedule options and validates them against the scheduling rules.

For each affected vessel, it considers:

- Retaining the existing schedule without changes.
- Shifting the vessel’s current berth, pilot, and tug assignments to match the revised ETA.
- Using alternative resource combinations at the revised ETA.
- Where permitted, reallocating one conflicting vessel that is outside the two-hour freeze window.

Each generated option is validated using `scheduling_rules.py`, including resource-conflict checks, freeze-window rules, internal candidate conflicts, and FCFS priority rules.

The output contains valid and invalid schedule options. Invalid options include a reason explaining why they cannot be used. The pipeline does not apply any schedule change to the database.

# Run Instructions 
Activate your Python virtual environment from `PortPilot` and run these commands from the `backend` directory.

```bash
python tests/scheduling_pipeline_tests/initialize_database.py <date in YYYY-MM-DD>
```
This initialises an empty database with OCEANS-X vessel states, resource master data, and simulated operational allocations.

```bash
python tests/scheduling_pipeline_tests/monitoring_pipeline.py <n> <date in YYYY-MM-DD> 
```
n is a positive integer identifying the pipeline run. 
The script appends its report to: run_output_n.txt 
```

