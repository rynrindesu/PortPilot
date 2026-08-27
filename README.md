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
- An OCEANS-X account 
- Access to the required OCEANS-X API
- An xAI/Grok API key

## Project Structure

```text
PortPilot/
├── backend/
│   ├── oceans.py
│   └── test_oceans.py
│
├── frontend/
│
├── .env
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md