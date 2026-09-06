# PortPilot

PortPilot is an agentic AI prototype for maritime port-call operations in Singapore.

## Services

PortPilot is being organised as two independent services. They have separate
Python environments, dependencies, and deployment boundaries, while local
development uses one root-level `.env` file for shared configuration. They
will communicate through explicit APIs or events—not by importing Python code
from one another.

| Service | Status | Responsibility |
| --- | --- | --- |
| `rescheduling_agent/` | Available | Monitors vessel arrivals, detects ETA changes, and manages berth, pilot, and tug rescheduling. |
| `port_ops_agent/` | Available | Extracts maritime documents and supports port-call compliance and inspection workflows. |

## Rescheduling Agent

The rescheduling service connects to the OCEANS-X API and automatically
manages vessel arrivals and their berth, pilot, and tug assignments for the
Port of Singapore.

### How it works

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

### Prerequisites

- Python 3.13 or later
- Supabase/PostgreSQL connection details
- OCEANS-X API credentials
- One LLM provider:
  - Groq API credentials; or
  - AWS credentials and Amazon Bedrock access

### Install and run

Run these commands from the repository root:

```bash
cd rescheduling_agent
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
uvicorn PortPilot.main:app --app-dir src --reload
```

The local API is then available at:

- Interactive API documentation: `http://127.0.0.1:8000/docs`
- Manually run monitoring: `POST /monitor?arrival_date=YYYY-MM-DD`
- View scheduler status: `GET /automation/status`

To run without automatic reload, omit `--reload`.

### Test the service

From `rescheduling_agent/`, with its virtual environment activated:

```bash
PYTHONPATH=src python -m pytest
```

Some integration and scheduling-pipeline tests require a reachable,
configured PostgreSQL database. The service can still be import-checked with:

```bash
PYTHONPATH=src python -c "from PortPilot.main import app; print(app.title)"
```

### Automated operating-day lifecycle

When the FastAPI application is running, the rescheduling service schedules
recurring jobs using Singapore time (`Asia/Singapore`). Automation is enabled
by default. Set `PORTPILOT_AUTOMATION_ENABLED=false` in
the root `.env` file for local API work or maintenance.

#### 21:00 — Stage the next operating day

At 21:00 each day, the service fetches tomorrow's OCEANS-X arrival feed and
stores new vessels as `staged`. Staged vessels are not visible to normal
monitoring and do not receive berth, pilot, or tug assignments.

#### 00:00 — Initialize the new operating day

At midnight, the service removes earlier operating-day records, activates
today's staged vessels, refreshes the complete arrival feed, activates the
required resource pools, and creates missing initial assignments.

#### HH:05 — Monitor the current operating day

At five minutes past every hour, the service fetches today's feed, records new
vessels and ETA changes, and processes each vessel independently. ETA changes
go through the rescheduling agent. New incomplete assignments use the
deterministic scheduling pipeline and are marked for review if no valid option
exists.

### Startup recovery and concurrency

On startup, the rescheduling service performs a catch-up operation for the
current operating day. All lifecycle jobs share a PostgreSQL advisory lock, so
staging, initialization, hourly monitoring, and recovery cannot overlap.

Run one FastAPI worker for this prototype. The latest completed scheduler
results are held in process memory and are available at `GET /automation/status`.

## OCR Service and Port-Ops Agent

The OCR service processes uploaded vessel documents and converts their
contents into structured data for downstream validation and compliance
checks. It identifies document types, extracts relevant vessel and port-call
information, and prepares the results for use by the Port-Ops Agent.

The Port-Ops Agent manages vessel port-call compliance and operational
workflows for the Port of Singapore. It evaluates submitted documents,
performs compliance and risk checks, determines whether correction, human
review, or physical inspection is required, and manages the vessel's
progression through arrival, operations, and departure.

### Prerequisites

- Python 3.13 or later
- One LLM provider:
  - OpenAI API; or
  - Groq API credentials; or
  - AWS credentials and Amazon Bedrock access

### Install and run

Run these commands from the repository root:

```bash
cd port_ops_agent
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -e .
uvicorn PortPilot.main:app --app-dir src --reload
```

### Test the service

From `port_ops_agent/`, with its virtual environment activated:

```bash
python -m pytest -v
```


## Repository structure

```text
PortPilot/
├── README.md
├── .gitignore
├── .env                      # Shared local configuration; not committed
├── rescheduling_agent/       # Current runnable service
│   ├── .venv/                # Local only; not committed
│   ├── pyproject.toml
│   ├── requirements.txt
│   ├── src/PortPilot/
│   │   ├── agent/            # ETA-change scheduling agent
│   │   ├── api/
│   │   ├── database/
│   │   ├── integration/
│   │   └── monitoring/
│   └── tests/
│
└── port_ops_agent/                # OCR and port-call service
    ├── .venv/
    ├── src/
    └── tests/
```
