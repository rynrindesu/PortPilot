# PortPilot

PortPilot is an agentic AI prototype for maritime port-call operations in Singapore.

The system continuously monitors vessel arrival information and identifies operational changes that may require action. An AI agent can then investigate the impact, formulate a plan, and execute appropriate actions through available tools.

## Current Prototype

PortPilot connects to the OCEANS-X API and automatically manages vessel arrivals and their berth, pilot, and tug assignments for the Port of Singapore.

The current operating flow is:

```text
OCEANS-X API
    ↓
Vessel monitoring and ETA-change detection
    ↓
Initial or existing assignment handling
    ├── ETA changed
    │       ↓
    │   AI agent investigates the current schedule
    │       ↓
    │   Deterministic scheduling options are generated,
    │   validated, and ranked
    │       ↓
    │   The agent selects an option
    │       ↓
    │   The change is applied and verified
    │
    └── New or incomplete assignment
            ↓
        Deterministic scheduling selects the
        highest-ranked valid option
            ↓
        Apply the option or mark it for review
```

## Automated operating-day lifecycle

When the FastAPI application is running and automation is enabled, PortPilot schedules its recurring jobs using Singapore time (`Asia/Singapore`).

Automation is enabled by default. Set `PORTPILOT_AUTOMATION_ENABLED=false` to disable it during maintenance or local API work.

### 21:00 — Stage the next operating day

At 21:00 each day, PortPilot:

1. Fetches the complete OCEANS-X arrival feed for tomorrow.
2. Stores new vessels with the `staged` lifecycle status.
3. Refreshes vessels that are already staged if the job runs again.

Staged vessels are not visible to normal monitoring and do not receive berth, pilot, or tug assignments. Existing active vessel records are not overwritten by staging.

### 00:00 — Initialize the new operating day

At midnight, PortPilot:

1. Deletes vessel records from earlier operating days, including their dependent history and assignment records.
2. Activates vessels that were staged for today.
3. Fetches today’s complete OCEANS-X arrival feed again.
4. Deactivates the previous resource pool.
5. Persists the complete vessel feed without assigning resources from the previous pool.
6. Runs `generate_operations()`.

The initializer creates operation windows, calculates peak concurrent demand, activates the required berth, pilot, and tug resource pools, and creates missing initial assignments.

Vessel and ETA differences detected while the midnight feed is persisted are reported in the job result, but they are not sent through the AI rescheduling agent during initialization.

The scheduler normally invokes this initializer at midnight. It may also invoke it during startup recovery if the midnight initialization appears to have been missed. Existing operation records are skipped rather than recreated by `generate_operations()`.

### HH:05 — Monitor the current operating day

At five minutes past every hour, PortPilot:

1. Fetches today’s OCEANS-X arrival feed.
2. Excludes feed entries whose ETA has already passed.
3. Compares the remaining arrivals with the active vessel state.
4. Records new vessels and ETA changes.
5. Processes each vessel independently so one failure does not stop the rest of the cycle.

ETA changes are handled by the AI rescheduling agent. The agent examines the current schedule, requests deterministic validated and ranked options, and selects an option by its ID. PortPilot retrieves the complete option, applies it, and verifies the resulting database state. The agent may retain the current schedule, apply a reschedule, or escalate unresolved allocations for review.

New vessels receive missing berth, pilot, and tug assignments from the existing active resource pools. If a conflict-free resource is unavailable, the assignment is initially marked `unconfirmed`.

Unconfirmed assignments do not use the AI agent. They are retried through the deterministic scheduling pipeline, which applies the highest-ranked valid option. If no valid option is available, the affected assignments are marked `pending_review`.

The unconfirmed-assignment recovery scan covers every active vessel with an `unconfirmed` assignment. It does not apply the hourly ETA cutoff, so an active vessel whose ETA has passed may still receive this recovery attempt.

Hourly jobs never call `generate_operations()` and never resize the active resource pools.

## Startup recovery

The scheduler performs one startup catch-up operation whenever the FastAPI application starts.

### Startup before 21:00

PortPilot checks whether today appears to have been initialized.

- If today is initialized, it deletes earlier operating-day records, activates any staged records for today, and immediately runs monitoring for today’s upcoming arrivals.
- If today is not initialized, it runs the midnight initialization as a catch-up.

### Startup at or after 21:00

PortPilot first stages tomorrow’s arrivals.

- If today is initialized, the startup catch-up ends after staging tomorrow. It does not run an immediate monitoring pass for today.
- If today is not initialized, it stages tomorrow and then runs the missed-midnight initialization for today.

Skipping an immediate startup monitoring pass after 21:00 does not stop regular monitoring. The hourly scheduler remains active and continues monitoring today at 21:05, 22:05, and 23:05, as applicable. At 00:00, it initializes the new operating day.

For startup recovery, PortPilot treats today as initialized when at least one active vessel has berth, pilot, and tug assignment records. This check does not guarantee that every vessel has a complete schedule; incomplete and unconfirmed assignments are handled by subsequent monitoring cycles.

## Concurrency and job status

Run one FastAPI worker for the prototype.

All lifecycle jobs share a PostgreSQL advisory lock. The lock prevents the staging, initialization, hourly monitoring, and startup jobs from making overlapping database changes. It also protects against duplicate execution if another worker is accidentally started.

If a job cannot acquire the lock because another lifecycle job is running, that execution is skipped rather than queued.

The latest completed scheduler results are available from:

```http
GET /automation/status
```

The endpoint reports:

- whether the in-process scheduler is running;
- the configured Singapore-time schedule; and
- the latest completed result for each job type.

These results exist only in the memory of the current FastAPI process. They are cleared when the application restarts, do not provide historical job records, and do not report live progress for a job that is still running.

## Prerequisites

Before setting up PortPilot, install:

- Python 3.13+
- Access to the team's OCEANS-X API credentials
- Access to the team's Supabase database credentials

Copy `.env.example` to `.env` and fill in the credentials provided securely by the project owner.

## Create Python environment and install required dependencies

python3 -m venv .venv
source .venv/bin/activate

cd backend
pip install -r requirements.txt
pip install -e .

## Project Structure

```text
PortPilot/
├── README.md
├── .env.example
├── .gitignore
│
└── backend/
    ├── pyproject.toml
    ├── requirements.txt
    │
    ├── src/
    │   └── portpilot/
    │       ├── __init__.py
    │       ├── main.py
    │       │
    │       ├── api/
    │       │   ├── __init__.py
    │       │   └── routes/
    │       │       ├── __init__.py
    │       │       └── monitoring.py
    │       │
    │       ├── integration/
    │       │   ├── __init__.py
    │       │   └── oceans.py
    │       │
    │       ├── database/
    │       │   ├── __init__.py
    │       │   └── postgres.py
    │       │
    │       ├── monitoring/
    │       │   ├── __init__.py
    │       │   ├── monitor_service.py
    │       │   ├── seed.py
    │       │   └── state.py
    │       │
    │       └── agent/
    │           ├── __init__.py
    │           ├── agent.py
    │           ├── graph.py
    │           └── tools.py
    │
    └── tests/
        ├── ...
```
