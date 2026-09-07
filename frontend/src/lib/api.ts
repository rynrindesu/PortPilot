/**
 * Data access layer.
 *
 * The console reads through this module only. With the two base URLs set it
 * talks to the running FastAPI services; with them unset it renders a bundled
 * operating-day snapshot so the app still runs on a machine with no backend.
 *
 *   VITE_RESCHEDULING_API=http://127.0.0.1:8000
 *   VITE_PORT_OPS_API=http://127.0.0.1:8001
 *
 * When a base URL IS configured, a failed request throws rather than quietly
 * falling back to the snapshot: showing demo numbers under a "live" badge
 * would be worse than showing an error.
 */

import {
  AGENT_RUNS,
  AUTOMATION,
  ETA_HISTORY,
  OPERATING_DAY,
  POOL,
  SCHEDULE_CHANGES,
  VESSELS,
} from "./mock/fleet";
import { PORT_CALLS } from "./mock/portops";
import type {
  AgentRun,
  AutomationStatus,
  EtaEvent,
  PortCallState,
  ResourceType,
  ScheduleChange,
  VesselState,
} from "./types";

const env = import.meta.env as Record<string, string | undefined>;

export const RESCHEDULING_API = (env.VITE_RESCHEDULING_API ?? "").replace(/\/$/, "");
export const PORT_OPS_API = (env.VITE_PORT_OPS_API ?? "").replace(/\/$/, "");

/** True when the console is wired to running backends. */
export const LIVE = Boolean(RESCHEDULING_API || PORT_OPS_API);

export const DATA_SOURCE: "demo" | "live" = LIVE ? "live" : "demo";

/**
 * A public deployment serves the API read-only: CloudFront allows only
 * GET/HEAD/OPTIONS on /api/*, so a visitor can read the live operating day
 * but cannot start a monitoring cycle (minutes of LLM calls per press) or
 * upload documents. The console hides those controls rather than offering
 * buttons that would fail at the edge.
 */
export const READ_ONLY = (env.VITE_API_READ_ONLY ?? "") === "true";

async function get<T>(base: string, path: string, fallback: T): Promise<T> {
  if (!base) return fallback;

  const res = await fetch(`${base}${path}`, {
    headers: { accept: "application/json" },
  });
  if (!res.ok) {
    throw new Error(`GET ${path} failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as T;
}

/* ---------------- rescheduling_agent ---------------- */

/** GET /vessels */
export const getVessels = () =>
  get<VesselState[]>(RESCHEDULING_API, "/vessels", VESSELS);

/** GET /eta-history */
export const getEtaHistory = () =>
  get<EtaEvent[]>(RESCHEDULING_API, "/eta-history", ETA_HISTORY);

/** GET /agent/runs */
export const getAgentRuns = () =>
  get<AgentRun[]>(RESCHEDULING_API, "/agent/runs", AGENT_RUNS);

/** GET /schedule-changes */
export const getScheduleChanges = () =>
  get<ScheduleChange[]>(RESCHEDULING_API, "/schedule-changes", SCHEDULE_CHANGES);

/** GET /automation/status */
export async function getAutomationStatus(): Promise<AutomationStatus> {
  if (!RESCHEDULING_API) return AUTOMATION;

  const raw = await get<Record<string, unknown>>(
    RESCHEDULING_API,
    "/automation/status",
    {},
  );

  // The scheduler reports a schedule map and a last-result map; the console
  // renders one row per job.
  const schedule = (raw.schedule ?? {}) as Record<string, string>;
  const lastResults = (raw.last_results ?? {}) as Record<string, unknown>;

  return {
    running: Boolean(raw.running),
    timezone: String(raw.timezone ?? "Asia/Singapore"),
    jobs: Object.entries(schedule).map(([name, when]) => {
      const result = (lastResults[name] ?? {}) as Record<string, unknown>;
      return {
        name,
        schedule: when,
        last_run: (result.finished_at as string) ?? null,
        next_run: "",
        status: result.error ? ("error" as const) : ("ok" as const),
        summary: result.error
          ? String(result.error)
          : Object.keys(result).length
            ? JSON.stringify(result).slice(0, 160)
            : "Not run since the service started.",
      };
    }),
  };
}

/** GET /resources */
export const getResources = () =>
  get<Record<ResourceType, string[]>>(RESCHEDULING_API, "/resources", POOL);

/** POST /monitor/cycle — a real monitoring pass through the agent. */
export class ReadOnlyError extends Error {
  constructor() {
    super("This deployment is read-only.");
    this.name = "ReadOnlyError";
  }
}

export async function runMonitor(processUnconfirmed = false) {
  if (!RESCHEDULING_API) {
    await new Promise((r) => setTimeout(r, 900));
    return AGENT_RUNS.slice(0, 3).map((r) => ({
      event: "ETA_CHANGED" as const,
      vessel_name: r.vessel_name,
      imo_number: r.imo_number,
      previous_eta: r.previous_eta ?? undefined,
      new_eta: r.new_eta,
    }));
  }

  if (READ_ONLY) throw new ReadOnlyError();

  const res = await fetch(
    `${RESCHEDULING_API}/monitor/cycle?process_unconfirmed=${processUnconfirmed}`,
    { method: "POST" },
  );
  if (!res.ok) throw new Error(`monitor cycle failed: ${res.status}`);
  const body = await res.json();
  return (body.raw_changes ?? []) as unknown[];
}

/* ---------------- port_ops_agent ---------------- */

/** GET /port-calls */
export const getPortCalls = () =>
  get<PortCallState[]>(PORT_OPS_API, "/port-calls", PORT_CALLS);

/** POST /documents/upload (multipart) — the real extraction service. */
export async function uploadDocument(file: File) {
  if (!PORT_OPS_API) return null;
  if (READ_ONLY) throw new ReadOnlyError();
  const body = new FormData();
  body.append("file", file);
  const res = await fetch(`${PORT_OPS_API}/documents/upload`, {
    method: "POST",
    body,
  });
  if (!res.ok) throw new Error(`upload failed: ${res.status}`);
  return res.json();
}

/** POST /port-calls/{id}/inspection/start */
export async function startInspection(id: string) {
  if (!PORT_OPS_API) return null;
  const res = await fetch(`${PORT_OPS_API}/port-calls/${id}/inspection/start`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

/** POST /port-calls/{id}/inspection/complete */
export async function completeInspection(
  id: string,
  cleared: boolean,
  findings?: string,
) {
  if (!PORT_OPS_API) return null;
  const res = await fetch(
    `${PORT_OPS_API}/port-calls/${id}/inspection/complete`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ cleared, findings: findings ?? null }),
    },
  );
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export { OPERATING_DAY };
