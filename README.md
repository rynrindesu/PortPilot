# PortPilot

PortPilot is an agentic AI prototype for maritime port-call operations in Singapore.

## Services

PortPilot is being organised as two independent services. They have separate
Python environments, configuration files, dependencies, and deployment
boundaries. They will communicate through explicit APIs or events—not by
importing Python code from one another.

| Service | Status | Responsibility |
| --- | --- | --- |
| `rescheduling_agent/` | Available | Monitors vessel arrivals, detects ETA changes, and manages berth, pilot, and tug rescheduling. |
| `ocr_agent/` | Planned | Extracts maritime documents and supports port-call compliance and inspection workflows. |

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

### Configure the service

Create `rescheduling_agent/.env` and provide the credentials supplied by the
project owner. Keep this file private; it is excluded from version control.

```dotenv
# OCEANS-X
OCEANX_VESSELS_DUE_TO_ARRIVE_API_KEY=

# Supabase/PostgreSQL
SUPABASE_DB_URL=
SUPABASE_DB_PASSWORD=

# Automation: true by default
PORTPILOT_AUTOMATION_ENABLED=true

# LLM provider: groq or bedrock
LLM_PROVIDER=groq
GROQ_API_KEY=
GROQ_MODEL=openai/gpt-oss-20b

# Required when LLM_PROVIDER=bedrock
BEDROCK_MODEL=us.anthropic.claude-haiku-4-5-20251001-v1:0
AWS_DEFAULT_REGION=us-east-1
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_SESSION_TOKEN=
```

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
`rescheduling_agent/.env` for local API work or maintenance.

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

## OCR and Port-Call Agent (planned)

`ocr_agent/` will be a sibling service with its own `.venv` and `.env`. It is
not included in this branch yet, so there is no installation or run command
for it today.

When it is added, the service will handle:

- PDF text extraction and maritime-document classification;
- structured field extraction and validation;
- port-call compliance, risk, and escalation checks; and
- human inspection workflow support.

Its expected prerequisites are Python 3.13 or later, PDF-processing
dependencies, and an OpenAI API key for document classification and extraction.
Its configuration will live in `ocr_agent/.env`, separately from the
rescheduling credentials.

## Repository structure

```text
PortPilot/
├── README.md
├── .gitignore
├── rescheduling_agent/       # Current runnable service
│   ├── .env                  # Local only; not committed
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
└── ocr_agent/                # Planned service; not yet added
    ├── .env
    ├── .venv/
    ├── src/
    └── tests/
```
