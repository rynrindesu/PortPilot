# PortPilot Console — "Harbour Control"

Operations front end for the two PortPilot services: the **rescheduling agent**
(vessel monitoring, ETA changes, berth/pilot/tug allocation) and the
**port-ops agent** (document extraction, compliance, risk, inspection).

## Run it

```bash
cd frontend
npm install
npm run dev
```

Opens on <http://localhost:5173>.

```bash
npm run build     # static bundle in dist/
npm run preview   # serve the built bundle on :4173
npm run typecheck
```

`dist/` is plain static output — deploy it to Vercel, Netlify, Cloudflare Pages,
S3 + CloudFront, or any web server. No Node runtime is required in production.

## Screens

| Route | What it shows |
| --- | --- |
| `/` | Harbour Watch — operating-day rollup, arrivals-per-hour curve, live activity feed, escalation queue |
| `/arrivals` | Full arrival board with ETA deltas, per-vessel drawer with ETA history and allocations |
| `/berths` | 24-hour resource plan for berths, pilots and tugs, with lane-packed bookings and a now-line |
| `/agent` | Rescheduling agent decision trace: every step, every generated option, why one was applied or none was |
| `/port-calls` | Compliance queue ordered by risk score |
| `/port-calls/:id` | Port-call detail — phase stepper, compliance findings, explainable risk breakdown, extracted document fields, inspection workflow, event log |
| `/documents` | Extraction pipeline (parse → classify → extract → validate) plus the document library |
| `/automation` | Lifecycle jobs, the Singapore-time day dial, and a manual monitoring pass |

## Data

Out of the box the console renders a bundled, deterministic operating-day
snapshot so it works on any machine with no database, no OCEANS-X credentials
and no LLM key. Everything is typed against the real FastAPI payload shapes
(`PortCallState`, `ExtractedDocument`, `ComplianceResult`, `vessel_state`,
`schedule_changes`, …) in `src/lib/types.ts`.

To read the live services instead, create `frontend/.env.local`:

```bash
VITE_RESCHEDULING_API=http://127.0.0.1:8000
VITE_PORT_OPS_API=http://127.0.0.1:8001
```

`src/lib/api.ts` is the only module that touches the network; each function
names the endpoint it maps to and falls back to the bundled snapshot if a
service is unreachable, so a demo never renders an empty screen.

Two things the backends need before live mode is fully wired:

1. **CORS.** Add `CORSMiddleware` to both FastAPI apps for the console's origin.
2. **Read endpoints.** `POST /monitor`, `GET /automation/status`,
   `GET /port-calls/{id}` and `POST /documents/upload` already exist. The board
   views additionally want list endpoints — `GET /vessels`, `GET /eta-history`,
   `GET /agent/runs`, `GET /schedule-changes`, `GET /port-calls` — which are
   thin wrappers over `get_all_vessel_states()`, `get_vessel_schedules_by_keys()`
   and the in-memory `PORT_CALLS` dict.

## Design

Dark nautical-chart console. Colour is semantic, not decorative — it follows
navigation-light convention:

| Colour | Meaning |
| --- | --- |
| starboard green | confirmed / cleared / passed |
| port red | blocked, rejected, pending human review |
| sodium amber | needs attention, unconfirmed, the now-line |
| beacon cyan | an autonomous agent action |

Type is Archivo (wide, signage) for display, IBM Plex Sans for prose and
IBM Plex Mono for every identifier, timestamp and measurement. Tokens live in
`src/index.css`; there is no per-component colour.

## Stack

Vite 8 · React 19 · TypeScript · Tailwind CSS v4 · Framer Motion · lucide-react.
