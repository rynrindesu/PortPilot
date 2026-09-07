import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import {
  DATA_SOURCE,
  getAgentRuns,
  getAutomationStatus,
  getEtaHistory,
  getPortCalls,
  getResources,
  getScheduleChanges,
  getVessels,
} from "./api";
import type {
  AgentRun,
  AutomationStatus,
  EtaEvent,
  PortCallState,
  ResourceType,
  ScheduleChange,
  VesselState,
} from "./types";

export interface FeedItem {
  id: string;
  at: string;
  kind: "eta" | "agent" | "vessel" | "compliance" | "job" | "alert";
  vessel?: string;
  text: string;
}

interface Data {
  vessels: VesselState[];
  etaHistory: EtaEvent[];
  agentRuns: AgentRun[];
  scheduleChanges: ScheduleChange[];
  automation: AutomationStatus;
  portCalls: PortCallState[];
  pools: Record<ResourceType, string[]>;
  feed: FeedItem[];
  operatingDay: string;
  dayStart: Date;
  source: "live" | "demo";
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

const DataContext = createContext<Data | null>(null);

const EMPTY_AUTOMATION: AutomationStatus = {
  running: false,
  timezone: "Asia/Singapore",
  jobs: [],
};

/** Today's 00:00 in Singapore — the operating-day boundary the backend uses. */
function singaporeDayStart() {
  const ymd = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Singapore",
  }).format(new Date());
  return { ymd, start: new Date(`${ymd}T00:00:00+08:00`) };
}

/** One activity stream, newest first, from what the services actually did. */
function buildFeed(
  runs: AgentRun[],
  history: EtaEvent[],
  portCalls: PortCallState[],
): FeedItem[] {
  const items: FeedItem[] = [];

  runs.forEach((r, i) => {
    const escalated = r.outcome !== "resources_allocated";
    items.push({
      id: `agent-${r.run_id}-${i}`,
      at: r.started_at,
      kind: escalated ? "alert" : "agent",
      vessel: r.vessel_name,
      text: escalated
        ? `No valid reschedule for ${r.vessel_name} — allocation flagged for review.`
        : `Rescheduled ${r.vessel_name} (${r.selected_option ?? "rank 1"}).`,
    });
  });

  history.forEach((e, i) => {
    if (!e.previous_eta) return;
    items.push({
      id: `eta-${e.eta_event_id}-${i}`,
      at: e.received_at,
      kind: "eta",
      vessel: e.vessel_name,
      text: `ETA revision received from ${e.source.toUpperCase()}.`,
    });
  });

  portCalls.forEach((p) => {
    if (p.escalation.action === "NONE") return;
    items.push({
      id: `comp-${p.port_call_id}`,
      at: p.events[0]?.at ?? new Date().toISOString(),
      kind: "compliance",
      vessel: p.vessel_name,
      text: `${p.escalation.action.replace(/_/g, " ")} — risk ${p.risk.risk_score} (${p.risk.risk_level}).`,
    });
  });

  return items.sort(
    (a, b) => new Date(b.at).getTime() - new Date(a.at).getTime(),
  );
}

export function DataProvider({ children }: { children: ReactNode }) {
  const [vessels, setVessels] = useState<VesselState[]>([]);
  const [etaHistory, setEtaHistory] = useState<EtaEvent[]>([]);
  const [agentRuns, setAgentRuns] = useState<AgentRun[]>([]);
  const [scheduleChanges, setScheduleChanges] = useState<ScheduleChange[]>([]);
  const [automation, setAutomation] = useState<AutomationStatus>(EMPTY_AUTOMATION);
  const [portCalls, setPortCalls] = useState<PortCallState[]>([]);
  const [pools, setPools] = useState<Record<ResourceType, string[]>>({
    berth: [],
    pilot: [],
    tug: [],
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  const refresh = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      setLoading(true);
      setError(null);
      try {
        const [v, h, r, c, a, p, res] = await Promise.all([
          getVessels(),
          getEtaHistory(),
          getAgentRuns(),
          getScheduleChanges(),
          getAutomationStatus(),
          getPortCalls(),
          getResources(),
        ]);
        if (cancelled) return;
        setVessels(v);
        setEtaHistory(h);
        setAgentRuns(r);
        setScheduleChanges(c);
        setAutomation(a);
        setPortCalls(p);
        setPools(res);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [tick]);

  const value = useMemo<Data>(() => {
    const { ymd, start } = singaporeDayStart();
    return {
      vessels,
      etaHistory,
      agentRuns,
      scheduleChanges,
      automation,
      portCalls,
      pools,
      feed: buildFeed(agentRuns, etaHistory, portCalls),
      operatingDay: ymd,
      dayStart: start,
      source: DATA_SOURCE,
      loading,
      error,
      refresh,
    };
  }, [
    vessels,
    etaHistory,
    agentRuns,
    scheduleChanges,
    automation,
    portCalls,
    pools,
    loading,
    error,
    refresh,
  ]);

  return <DataContext.Provider value={value}>{children}</DataContext.Provider>;
}

export function useData(): Data {
  const ctx = useContext(DataContext);
  if (!ctx) throw new Error("useData must be used inside <DataProvider>");
  return ctx;
}

/* ------------------------------------------------------------
   Rollups, computed from whatever the services returned.
   ------------------------------------------------------------ */
export function useFleetStats() {
  const { vessels, etaHistory, agentRuns, pools } = useData();

  return useMemo(() => {
    const active = vessels.filter((v) => v.status === "active");
    const allocations = active.flatMap((v) => Object.values(v.allocations));
    const berthMinutes = active.reduce((sum, v) => {
      const a = v.allocations.berth;
      if (!a) return sum;
      return (
        sum +
        (new Date(a.end_time).getTime() - new Date(a.start_time).getTime()) /
          60000
      );
    }, 0);
    const berthPool = Math.max(1, pools.berth.length);

    return {
      arrivals: active.length,
      staged: vessels.length - active.length,
      etaChanges: etaHistory.filter((e) => e.previous_eta).length,
      autoResolved: agentRuns.filter((r) => r.outcome === "resources_allocated")
        .length,
      pendingReview: allocations.filter((a) => a?.status === "pending_review")
        .length,
      unconfirmed: allocations.filter((a) => a?.status === "unconfirmed").length,
      berthUtilisation: Math.round(
        (berthMinutes / (berthPool * 24 * 60)) * 100,
      ),
    };
  }, [vessels, etaHistory, agentRuns, pools]);
}

export function useComplianceStats() {
  const { portCalls } = useData();

  return useMemo(() => {
    const fields = portCalls.flatMap((p) =>
      p.documents.flatMap((d) => Object.values(d.fields)),
    );
    return {
      total: portCalls.length,
      cleared: portCalls.filter((p) =>
        [
          "arrival_cleared",
          "operations",
          "departure_cleared",
          "inspection_cleared",
          "completed",
        ].includes(p.status),
      ).length,
      correction: portCalls.filter((p) => p.status === "correction_required")
        .length,
      review: portCalls.filter((p) => p.status === "human_review").length,
      inspection: portCalls.filter((p) =>
        ["inspection_required", "inspection_in_progress"].includes(p.status),
      ).length,
      documents: portCalls.reduce((a, p) => a + p.documents.length, 0),
      fieldsExtracted: fields.length,
      avgConfidence: fields.length
        ? fields.reduce((a, f) => a + f.confidence, 0) / fields.length
        : 0,
    };
  }, [portCalls]);
}
