# PortPilot

PortPilot is an agentic AI prototype for maritime port-call operations in Singapore.

The system continuously monitors vessel arrival information and identifies operational changes that may require action. An AI agent can then investigate the impact, formulate a plan, and execute appropriate actions through available tools.

## Current Prototype

The current prototype connects to the OCEANS-X API to retrieve vessels due to arrive at the Port of Singapore on a specified date.

Current flow:

OCEANS-X API
↓
Python API Client
↓
Clean Vessel Data

Future flow:

OCEANS-X API
↓
Monitoring
↓
Change Detection
↓
AI Agent
↓
Reasoning & Planning
↓
Tool Execution
↓
Verification

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
        ├── test_monitoring.py
        ├── test_oceans.py
        └── test_postgres.py
```
