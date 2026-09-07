import type {
  Allocation,
  AgentRun,
  AutomationStatus,
  EtaEvent,
  ResourceType,
  ScheduleChange,
  ScheduleOption,
  VesselState,
} from "../types";

/* ------------------------------------------------------------
   Deterministic PRNG — the demo must look identical every run.
   ------------------------------------------------------------ */
function mulberry32(seed: number) {
  return function () {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const rand = mulberry32(20260907);
const pick = <T>(xs: readonly T[]) => xs[Math.floor(rand() * xs.length)];
const between = (lo: number, hi: number) => lo + rand() * (hi - lo);
const intBetween = (lo: number, hi: number) => Math.floor(between(lo, hi + 1));

/* ------------------------------------------------------------
   The operating day. Singapore runs the clock, so the whole
   dataset is anchored to today's 00:00 SGT boundary — matching
   the backend's Asia/Singapore lifecycle jobs.
   ------------------------------------------------------------ */
const ymd = new Intl.DateTimeFormat("en-CA", {
  timeZone: "Asia/Singapore",
}).format(new Date());

export const OPERATING_DAY = ymd;
export const DAY_START = new Date(`${ymd}T00:00:00+08:00`);
export const DAY_END = new Date(DAY_START.getTime() + 24 * 3600_000);

const at = (hours: number) =>
  new Date(DAY_START.getTime() + hours * 3600_000).toISOString();

const shift = (iso: string, minutes: number) =>
  new Date(new Date(iso).getTime() + minutes * 60_000).toISOString();

/** Observations always happened; anchor them behind the wall clock. */
const minutesAgo = (minutes: number) =>
  new Date(Date.now() - minutes * 60_000).toISOString();

/* ------------------------------------------------------------
   Resource pools
   ------------------------------------------------------------ */
export const BERTHS = [
  "TUAS-B1",
  "TUAS-B2",
  "TUAS-B3",
  "TUAS-B4",
  "PPT-C1",
  "PPT-C2",
  "PPT-C3",
  "BRANI-A1",
  "BRANI-A2",
  "KEPPEL-D1",
];

export const PILOTS = Array.from({ length: 12 }, (_, i) =>
  `PLT-${String(i + 1).padStart(2, "0")}`,
);

export const TUGS = Array.from({ length: 10 }, (_, i) =>
  `TUG-${String(i + 1).padStart(2, "0")}`,
);

export const POOL: Record<ResourceType, string[]> = {
  berth: BERTHS,
  pilot: PILOTS,
  tug: TUGS,
};

/* ------------------------------------------------------------
   Fleet
   ------------------------------------------------------------ */
const FLEET_SEED: [name: string, imo: string, type: string, from: string, flag: string][] =
  [
    ["EVER LINDEN", "9863297", "Container", "Shanghai", "Panama"],
    ["MAERSK SENTOSA", "9778315", "Container", "Rotterdam", "Denmark"],
    ["CMA CGM JAKARTA", "9704114", "Container", "Port Klang", "France"],
    ["ONE MERIDIAN", "9741330", "Container", "Busan", "Japan"],
    ["PACIFIC HORIZON", "9532817", "Bulk Carrier", "Fremantle", "Marshall Is."],
    ["STAR OF MALACCA", "9412773", "Chemical Tanker", "Jubail", "Singapore"],
    ["HAFNIA VICTORIA", "9689261", "Product Tanker", "Fujairah", "Singapore"],
    ["OOCL KAOHSIUNG", "9622559", "Container", "Kaohsiung", "Hong Kong"],
    ["BW ORION", "9411080", "LPG Carrier", "Ras Laffan", "Isle of Man"],
    ["NYK ATLAS", "9337638", "Vehicle Carrier", "Yokohama", "Panama"],
    ["MSC ANTONIA", "9839933", "Container", "Colombo", "Liberia"],
    ["TIGER SPIRIT", "9299901", "General Cargo", "Ho Chi Minh", "Vietnam"],
    ["ARCTIC BLUE", "9598214", "Reefer", "Valparaíso", "Bahamas"],
    ["EAGLE MELBOURNE", "9412447", "Crude Tanker", "Basrah", "Marshall Is."],
    ["KOTA SEJATI", "9767330", "Container", "Jakarta", "Singapore"],
    ["SEASPAN GUARDIAN", "9629181", "Container", "Ningbo", "Hong Kong"],
    ["GOLDEN STRAIT", "9256179", "Bulk Carrier", "Newcastle", "Panama"],
    ["ORIENT VENTURE", "9702815", "Container", "Chennai", "India"],
    ["SIN CHENG 8", "9188619", "Bunker Tanker", "Singapore OPL", "Singapore"],
    ["APL TEMASEK", "9631596", "Container", "Yantian", "Singapore"],
    ["NORDIC AURORA", "9455644", "Chemical Tanker", "Ulsan", "Norway"],
    ["MERATUS SPIRIT", "9345623", "General Cargo", "Surabaya", "Indonesia"],
  ];

const callSign = (i: number) => `9V${String(2100 + i * 37).slice(0, 4)}`;

function windowFor(type: ResourceType, eta: string): [string, string] {
  if (type === "pilot") {
    const lead = intBetween(35, 110);
    return [shift(eta, -lead), eta];
  }
  if (type === "tug") {
    return [eta, shift(eta, intBetween(30, 60))];
  }
  return [eta, shift(eta, intBetween(300, 700))];
}

/** Vessels whose story the demo tells; the rest are ambient traffic. */
const PENDING_REVIEW = new Set(["EAGLE MELBOURNE", "TIGER SPIRIT"]);
const ETA_CHANGED = new Set([
  "EVER LINDEN",
  "HAFNIA VICTORIA",
  "MSC ANTONIA",
  "GOLDEN STRAIT",
  "SEASPAN GUARDIAN",
  ...PENDING_REVIEW,
]);
const UNCONFIRMED = new Set(["ORIENT VENTURE", "NORDIC AURORA"]);
const STAGED = new Set(["MERATUS SPIRIT", "SIN CHENG 8"]);

export const VESSELS: VesselState[] = FLEET_SEED.map(
  (
    [vessel_name, imo_number, vessel_type, location_from, flag],
    i,
  ): VesselState => {
    const originalEta = at(between(1.5, 23));
    const changed = ETA_CHANGED.has(vessel_name);
    const drift = changed ? intBetween(-95, 220) : 0;
    const current_eta = changed ? shift(originalEta, drift) : originalEta;

    const allocations = {} as Record<ResourceType, Allocation | null>;
    (["berth", "pilot", "tug"] as ResourceType[]).forEach((type, k) => {
      const [start_time, end_time] = windowFor(type, current_eta);
      const status: Allocation["status"] = PENDING_REVIEW.has(vessel_name)
        ? k === 0
          ? "pending_review"
          : "confirmed"
        : UNCONFIRMED.has(vessel_name) && k !== 2
          ? "unconfirmed"
          : "confirmed";
      allocations[type] = {
        resource_type: type,
        resource_id: POOL[type][(i * 3 + k) % POOL[type].length],
        start_time,
        end_time,
        buffer_minutes: 15,
        status,
      };
    });

    return {
      vessel_name,
      imo_number,
      call_sign: callSign(i),
      flag,
      location_from,
      location_to: "SGSIN",
      vessel_type,
      loa_m: intBetween(120, 400),
      original_eta: originalEta,
      previous_eta: changed ? originalEta : null,
      current_eta,
      eta_source: "oceans_x",
      eta_confidence: Number(between(0.72, 0.99).toFixed(2)),
      status: STAGED.has(vessel_name) ? "staged" : "active",
      last_updated: minutesAgo(intBetween(6, 260)),
      allocations,
    };
  },
).sort(
  (a, b) => new Date(a.current_eta).getTime() - new Date(b.current_eta).getTime(),
);

export const vesselByImo = (imo: string) =>
  VESSELS.find((v) => v.imo_number === imo);

/* ------------------------------------------------------------
   ETA history — append-only, exactly like eta_history
   ------------------------------------------------------------ */
export const ETA_HISTORY: EtaEvent[] = VESSELS.flatMap((v, i) => {
  const rows: EtaEvent[] = [
    {
      eta_event_id: i * 10 + 1,
      vessel_name: v.vessel_name,
      imo_number: v.imo_number,
      previous_eta: null,
      reported_eta: v.original_eta,
      source: "oceans_x",
      confidence: 0.94,
      received_at: minutesAgo(intBetween(300, 900)),
    },
  ];
  if (v.previous_eta) {
    rows.push({
      eta_event_id: i * 10 + 2,
      vessel_name: v.vessel_name,
      imo_number: v.imo_number,
      previous_eta: v.previous_eta,
      reported_eta: v.current_eta,
      source: "oceans_x",
      confidence: v.eta_confidence,
      received_at: v.last_updated,
    });
  }
  return rows;
}).sort(
  (a, b) => new Date(b.received_at).getTime() - new Date(a.received_at).getTime(),
);

/* ------------------------------------------------------------
   Agent runs — the decision trace judges actually want to see
   ------------------------------------------------------------ */
function buildOptions(
  v: VesselState,
  shiftMin: number,
  blocked: boolean,
): ScheduleOption[] {
  const berth = v.allocations.berth!;
  const base = new Date(berth.start_time);
  const raw: ScheduleOption[] = [];

  const templates = [
    { keepBerth: true, delta: shiftMin, displaced: [] as string[] },
    { keepBerth: true, delta: shiftMin + 45, displaced: [] },
    { keepBerth: false, delta: shiftMin, displaced: [] },
    { keepBerth: false, delta: shiftMin - 30, displaced: ["KOTA SEJATI"] },
    { keepBerth: true, delta: shiftMin - 90, displaced: ["OOCL KAOHSIUNG"] },
    { keepBerth: false, delta: shiftMin + 180, displaced: [] },
  ];

  templates.forEach((t, idx) => {
    const to_resource = t.keepBerth
      ? berth.resource_id
      : BERTHS[(BERTHS.indexOf(berth.resource_id) + idx + 1) % BERTHS.length];
    const to_start = shift(berth.start_time, t.delta);
    const to_end = shift(berth.end_time, t.delta);

    let invalid_reason: string | null = null;
    if (t.delta < 0 && idx === 4)
      invalid_reason = "berth window opens before the vessel's current ETA";
    if (idx === 5)
      invalid_reason =
        "berth allocation exceeds the 15-minute turnaround buffer for TUG-04";

    // A run that ends in pending_review is one where nothing survived the
    // hard constraints — every option must carry the reason it failed.
    if (blocked && invalid_reason === null) {
      invalid_reason = t.displaced.length
        ? `would displace confirmed vessel ${t.displaced[0]}`
        : t.keepBerth
          ? `${berth.resource_id} is occupied for the whole shifted window`
          : `no ${
              idx % 2 ? "pilot" : "tug"
            } is free across the shifted window`;
    }

    raw.push({
      option_id: `OPT-${idx + 1}`,
      rank: null,
      valid: invalid_reason === null,
      invalid_reason,
      score: 0,
      moves: [
        {
          resource_type: "berth",
          from_resource: berth.resource_id,
          to_resource,
          from_start: berth.start_time,
          to_start,
          to_end,
        },
        {
          resource_type: "pilot",
          from_resource: v.allocations.pilot!.resource_id,
          to_resource: v.allocations.pilot!.resource_id,
          from_start: v.allocations.pilot!.start_time,
          to_start: shift(v.allocations.pilot!.start_time, t.delta),
          to_end: shift(v.allocations.pilot!.end_time, t.delta),
        },
      ],
      displaced_vessels: t.displaced,
      total_shift_minutes: Math.abs(t.delta),
    });
  });

  // Deterministic ranking: fewest displacements, then smallest shift, then
  // berth continuity — the same ordering rank_options() applies server-side.
  const valid = raw.filter((o) => o.valid);
  valid
    .map((o) => ({
      o,
      cost:
        o.displaced_vessels.length * 1000 +
        o.total_shift_minutes +
        (o.moves[0].from_resource === o.moves[0].to_resource ? 0 : 120),
    }))
    .sort((a, b) => a.cost - b.cost)
    .forEach(({ o, cost }, i) => {
      o.rank = i + 1;
      o.score = Number((100 - cost / 12).toFixed(1));
    });

  void base;
  return raw;
}

function buildRun(v: VesselState, index: number): AgentRun {
  const delta = Math.round(
    (new Date(v.current_eta).getTime() -
      new Date(v.previous_eta ?? v.current_eta).getTime()) /
      60000,
  );
  const blocked = PENDING_REVIEW.has(v.vessel_name);
  const options = buildOptions(v, delta, blocked);
  const validOptions = options.filter((o) => o.valid);
  const best = validOptions.find((o) => o.rank === 1) ?? null;

  const steps = [
    {
      key: "detect",
      title: "ETA change detected",
      detail: `OCEANS-X reported ${delta > 0 ? "a delay of" : "an advance of"} ${Math.abs(delta)} minutes against the stored ETA.`,
      actor: "monitor" as const,
      status: "done" as const,
      ms: 118,
    },
    {
      key: "inspect",
      title: "Agent inspected the current schedule",
      detail: `Read berth ${v.allocations.berth?.resource_id}, pilot ${v.allocations.pilot?.resource_id} and tug ${v.allocations.tug?.resource_id} plus every booking that overlaps the ±2 h conflict window.`,
      actor: "agent" as const,
      status: "done" as const,
      ms: 1420,
    },
    {
      key: "generate",
      title: "Deterministic options generated",
      detail: `${options.length} candidate reschedules produced from the active resource pool.`,
      actor: "rules" as const,
      status: "done" as const,
      ms: 96,
    },
    {
      key: "validate",
      title: "Hard constraints applied",
      detail: `${validOptions.length} of ${options.length} survived buffer, ETA-ordering and pool-availability checks.`,
      actor: "rules" as const,
      status: blocked ? ("blocked" as const) : ("done" as const),
      ms: 74,
    },
    {
      key: "rank",
      title: "Options ranked",
      detail: blocked
        ? "No option cleared the constraints — the allocation is escalated instead of guessed."
        : `Rank 1 = ${best?.option_id}: ${best?.displaced_vessels.length ?? 0} vessels displaced, ${best?.total_shift_minutes ?? 0} min total shift.`,
      actor: "rules" as const,
      status: blocked ? ("blocked" as const) : ("done" as const),
      ms: 41,
    },
    {
      key: "apply",
      title: blocked ? "Escalated to pending review" : "Change applied and verified",
      detail: blocked
        ? "Berth allocation flagged pending_review for a human controller. No write to the allocation tables."
        : `Wrote the new window under a row-level lock and re-read it to confirm; logged to schedule_changes.`,
      actor: blocked ? ("agent" as const) : ("database" as const),
      status: blocked ? ("blocked" as const) : ("done" as const),
      ms: blocked ? 33 : 260,
    },
  ];

  return {
    run_id: `RUN-${String(index + 1).padStart(4, "0")}`,
    vessel_name: v.vessel_name,
    imo_number: v.imo_number,
    trigger: "ETA_CHANGED",
    started_at: v.last_updated,
    duration_ms: steps.reduce((a, s) => a + s.ms, 0),
    previous_eta: v.previous_eta,
    new_eta: v.current_eta,
    options_generated: options.length,
    options_valid: validOptions.length,
    outcome: blocked ? "pending_review" : "resources_allocated",
    selected_option: blocked ? null : (best?.option_id ?? null),
    rationale: blocked
      ? `Every generated option either broke the turnaround buffer on ${v.allocations.tug?.resource_id} or pushed a confirmed vessel off its berth. Escalating rather than displacing confirmed traffic.`
      : `Held ${v.vessel_name} on ${best?.moves[0].to_resource} and shifted the window by ${best?.total_shift_minutes} minutes. This absorbs the ETA change without displacing any confirmed vessel, and keeps the pilot pairing intact.`,
    steps,
    options,
  };
}

export const AGENT_RUNS: AgentRun[] = VESSELS.filter(
  (v) => ETA_CHANGED.has(v.vessel_name) || PENDING_REVIEW.has(v.vessel_name),
)
  .map(buildRun)
  .sort(
    (a, b) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime(),
  );

/* ------------------------------------------------------------
   Applied changes ledger
   ------------------------------------------------------------ */
export const SCHEDULE_CHANGES: ScheduleChange[] = AGENT_RUNS.filter(
  (r) => r.outcome === "resources_allocated",
).flatMap((run, i) => {
  const option = run.options.find((o) => o.option_id === run.selected_option)!;
  return option.moves.map((m, k) => ({
    change_id: 4200 + i * 10 + k,
    vessel_name: run.vessel_name,
    imo_number: run.imo_number,
    resource_type: m.resource_type,
    resource_id: m.to_resource,
    old_start_time: m.from_start,
    old_end_time: null,
    new_start_time: m.to_start,
    new_end_time: m.to_end,
    reason: run.rationale,
    decision_score: option.rank ?? 1,
    execution_mode: "autonomous" as const,
    changed_at: run.started_at,
  }));
});

/* ------------------------------------------------------------
   Automation lifecycle (mirrors AutomationScheduler.status)
   ------------------------------------------------------------ */
const NOW_MINUTES = (Date.now() - DAY_START.getTime()) / 60_000;
const atMinutes = (m: number) =>
  new Date(DAY_START.getTime() + m * 60_000).toISOString();

// Hourly monitoring fires at minute 05 of every hour.
const LAST_HOURLY = Math.floor((NOW_MINUTES - 5) / 60) * 60 + 5;

export const AUTOMATION: AutomationStatus = {
  running: true,
  timezone: "Asia/Singapore",
  jobs: [
    {
      name: "stage_next_day",
      schedule: "21:00 daily",
      last_run: atMinutes(21 * 60 - 24 * 60),
      next_run: atMinutes(NOW_MINUTES < 21 * 60 ? 21 * 60 : 45 * 60),
      status: "ok",
      summary: `${STAGED.size} vessels staged for the next operating day.`,
    },
    {
      name: "initialize_current_day",
      schedule: "00:00 daily",
      last_run: at(0),
      next_run: at(24),
      status: "ok",
      summary: `Activated ${VESSELS.filter((v) => v.status === "active").length} vessels, refreshed the arrival feed, opened the resource pools.`,
    },
    {
      name: "hourly_update",
      schedule: "minute 05 of every hour",
      last_run: LAST_HOURLY >= 0 ? atMinutes(LAST_HOURLY) : null,
      next_run: atMinutes(LAST_HOURLY + 60),
      status: "ok",
      summary: `${AGENT_RUNS.length} vessels processed, ${AGENT_RUNS.filter((r) => r.outcome === "resources_allocated").length} rescheduled autonomously.`,
    },
    {
      name: "startup_catchup",
      schedule: "on process start",
      last_run: at(0.4),
      next_run: at(24.4),
      status: "idle",
      summary: "Reconciled the current operating day after the last restart.",
    },
  ],
};

/* ------------------------------------------------------------
   Live-looking event feed
   ------------------------------------------------------------ */
export interface FeedItem {
  id: string;
  at: string;
  kind: "eta" | "agent" | "vessel" | "compliance" | "job" | "alert";
  vessel?: string;
  text: string;
}

export const FEED: FeedItem[] = ([
  ...AGENT_RUNS.map((r, i) => ({
    id: `f-agent-${i}`,
    at: r.started_at,
    kind: (r.outcome === "pending_review" ? "alert" : "agent") as FeedItem["kind"],
    vessel: r.vessel_name,
    text:
      r.outcome === "pending_review"
        ? `No valid reschedule for ${r.vessel_name} — berth flagged pending_review.`
        : `Rescheduled ${r.vessel_name} → ${r.options.find((o) => o.option_id === r.selected_option)?.moves[0].to_resource} (${r.selected_option}, rank 1).`,
  })),
  ...ETA_HISTORY.filter((e) => e.previous_eta).map((e, i) => ({
    id: `f-eta-${i}`,
    at: e.received_at,
    kind: "eta" as const,
    vessel: e.vessel_name,
    text: `ETA revision received from OCEANS-X (confidence ${(e.confidence * 100).toFixed(0)}%).`,
  })),
  ...VESSELS.slice(0, 6).map((v, i) => ({
    id: `f-new-${i}`,
    at: shift(v.last_updated, -intBetween(30, 240)),
    kind: "vessel" as const,
    vessel: v.vessel_name,
    text: `Discovered inbound from ${v.location_from}; berth, pilot and tug assigned on first sight.`,
  })),
  {
    id: "f-job-1",
    at: at(0),
    kind: "job",
    text: "Operating day initialised — expired records purged, staged vessels activated, resource pools opened.",
  },
  {
    id: "f-comp-1",
    at: minutesAgo(78),
    kind: "compliance",
    vessel: "EAGLE MELBOURNE",
    text: "Physical inspection required — risk 95 (radioactive material declared, first Singapore call).",
  },
  {
    id: "f-comp-2",
    at: minutesAgo(146),
    kind: "compliance",
    vessel: "STAR OF MALACCA",
    text: "Call-sign mismatch between certificate of registry and arrival declaration.",
  },
] as FeedItem[]).sort(
  (a, b) => new Date(b.at).getTime() - new Date(a.at).getTime(),
);

/* ------------------------------------------------------------
   Rollups
   ------------------------------------------------------------ */
export const fleetStats = () => {
  const active = VESSELS.filter((v) => v.status === "active");
  const allAllocs = active.flatMap((v) => Object.values(v.allocations));
  return {
    arrivals: active.length,
    staged: VESSELS.length - active.length,
    etaChanges: ETA_HISTORY.filter((e) => e.previous_eta).length,
    autoResolved: AGENT_RUNS.filter((r) => r.outcome === "resources_allocated")
      .length,
    pendingReview: allAllocs.filter((a) => a?.status === "pending_review").length,
    unconfirmed: allAllocs.filter((a) => a?.status === "unconfirmed").length,
    // Occupied berth-minutes as a share of the whole pool's operating day.
    berthUtilisation: Math.round(
      (active.reduce((sum, v) => {
        const a = v.allocations.berth;
        if (!a) return sum;
        return (
          sum +
          (new Date(a.end_time).getTime() - new Date(a.start_time).getTime()) /
            60000
        );
      }, 0) /
        (BERTHS.length * 24 * 60)) *
        100,
    ),
  };
};
