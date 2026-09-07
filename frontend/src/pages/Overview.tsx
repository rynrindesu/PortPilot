import { Link } from "react-router-dom";
import {
  ArrowUpRight,
  Bot,
  ClipboardCheck,
  Ship,
  TriangleAlert,
  Waves,
  Clock,
} from "lucide-react";

import { BerthTimeline } from "../components/BerthTimeline";
import { Chip, Metric, Panel, PanelHead, StatusChip } from "../components/ui";
import { useData, useComplianceStats, useFleetStats } from "../lib/store";
import { deltaMinutes, hhmm, humanDelta, relative, stamp } from "../lib/format";


/* ------------------------------------------------------------
   Arrivals per hour — the shape of the day
   ------------------------------------------------------------ */
function ArrivalCurve() {
  const { vessels: VESSELS, dayStart: DAY_START } = useData();
  const buckets = Array.from({ length: 24 }, () => 0);
  VESSELS.filter((v) => v.status === "active").forEach((v) => {
    const h = Math.floor(
      (new Date(v.current_eta).getTime() - DAY_START.getTime()) / 3600_000,
    );
    if (h >= 0 && h < 24) buckets[h] += 1;
  });
  const peak = Math.max(...buckets, 1);
  const peakHour = buckets.indexOf(peak);
  const nowHour = Math.floor(
    (Date.now() - DAY_START.getTime()) / 3600_000,
  );

  return (
    <div className="flex h-full flex-col justify-end">
      <div className="mb-3 flex items-baseline justify-between">
        <span className="label">Arrivals per hour · SGT</span>
        <span className="mono text-[10.5px] text-[var(--color-signal)]">
          peak {String(peakHour).padStart(2, "0")}:00 · {peak} vessels
        </span>
      </div>
      <div className="flex h-[104px] items-end gap-[3px]">
        {buckets.map((n, h) => {
          const isNow = h === nowHour;
          const past = h < nowHour;
          return (
            <div key={h} className="group relative flex-1">
              <div
                className="w-full rounded-[1px] transition-all duration-300"
                style={{
                  height: `${Math.max(2, (n / peak) * 96)}px`,
                  background: isNow
                    ? "var(--color-signal)"
                    : past
                      ? "color-mix(in srgb, var(--color-beacon) 42%, transparent)"
                      : "color-mix(in srgb, var(--color-mist) 85%, transparent)",
                  boxShadow: isNow
                    ? "0 0 14px color-mix(in srgb, var(--color-signal) 55%, transparent)"
                    : "none",
                  animation: `rise .5s cubic-bezier(.16,1,.3,1) ${h * 18}ms both`,
                }}
              />
              <span className="mono pointer-events-none absolute -top-5 left-1/2 -translate-x-1/2 text-[9px] text-[var(--color-chalk)] opacity-0 transition-opacity group-hover:opacity-100">
                {n}
              </span>
            </div>
          );
        })}
      </div>
      <div className="mono mt-1.5 flex justify-between text-[9px] text-[var(--color-slate-ink)]">
        <span>00</span>
        <span>06</span>
        <span>12</span>
        <span>18</span>
        <span>24</span>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------
   Feed
   ------------------------------------------------------------ */
const FEED_ICON = {
  agent: Bot,
  eta: Clock,
  vessel: Ship,
  compliance: ClipboardCheck,
  job: Waves,
  alert: TriangleAlert,
} as const;

const FEED_TONE = {
  agent: "text-[var(--color-beacon)]",
  eta: "text-[var(--color-fog)]",
  vessel: "text-[var(--color-chalk)]",
  compliance: "text-[var(--color-signal)]",
  job: "text-[var(--color-slate-ink)]",
  alert: "text-[var(--color-port)]",
} as const;

function Feed() {
  const { feed: FEED } = useData();

  return (
    <ol className="scroll-thin max-h-[430px] overflow-y-auto">
      {FEED.slice(0, 24).map((item, i) => {
        const Icon = FEED_ICON[item.kind];
        return (
          <li
            key={item.id}
            className="rise group relative flex gap-3 border-b border-dashed border-[var(--color-rail)] px-5 py-3 last:border-0 hover:bg-[color-mix(in_srgb,var(--color-plate)_60%,transparent)]"
            style={{ animationDelay: `${Math.min(i, 12) * 35}ms` }}
          >
            <Icon
              size={14}
              strokeWidth={1.8}
              className={`mt-[3px] shrink-0 ${FEED_TONE[item.kind]}`}
            />
            <div className="min-w-0 flex-1">
              {item.vessel && (
                <div className="mono text-[10.5px] tracking-[0.08em] text-[var(--color-chalk)] uppercase">
                  {item.vessel}
                </div>
              )}
              <p className="mt-0.5 text-[12px] leading-relaxed text-[var(--color-fog)]">
                {item.text}
              </p>
            </div>
            <span className="mono shrink-0 text-[9.5px] text-[var(--color-slate-ink)]">
              {relative(item.at)}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

/* ------------------------------------------------------------
   Page
   ------------------------------------------------------------ */
export default function Overview() {
  const { vessels: VESSELS, portCalls: PORT_CALLS, agentRuns: AGENT_RUNS, operatingDay: OPERATING_DAY } = useData();
  const fleet = useFleetStats();
  const comp = useComplianceStats();
  const S = { ...fleet, ...comp };
  const upcoming = VESSELS.filter((v) => v.status === "active").slice(0, 9);

  const escalations = [
    ...VESSELS.flatMap((v) =>
      Object.values(v.allocations)
        .filter((a) => a && a.status !== "confirmed")
        .map((a) => ({
          id: `${v.vessel_name}-${v.imo_number}-${a!.resource_type}`,
          title: v.vessel_name,
          detail: `${a!.resource_type} ${a!.resource_id} · ${a!.status.replace("_", " ")}`,
          status: a!.status,
          to: "/agent",
        })),
    ),
    ...PORT_CALLS.filter((p) => p.escalation.action !== "NONE").map((p) => ({
      id: p.port_call_id,
      title: p.vessel_name,
      detail: p.escalation.message,
      status: p.status,
      to: `/port-calls/${p.port_call_id}`,
    })),
  ].slice(0, 8);

  return (
    <div className="mx-auto max-w-[1560px] space-y-5 pb-10">
      {/* ---------------- hero ---------------- */}
      <Panel ticked className="rise">
        <div className="grid gap-px bg-[var(--color-rail)] lg:grid-cols-[1.35fr_1fr]">
          <div className="bg-[var(--color-hull)] px-8 py-8">
            <div className="flex items-center gap-2.5">
              <span className="pulse-dot inline-block h-1.5 w-1.5 rounded-full bg-[var(--color-starboard)] text-[var(--color-starboard)]" />
              <span className="label">
                Port of Singapore · operating day {OPERATING_DAY}
              </span>
            </div>

            <h2 className="display-tight mt-5 text-[52px] leading-[0.9] text-[var(--color-chalk)]">
              {S.arrivals} vessels
              <br />
              <span className="text-[var(--color-signal)]">under agent control</span>
            </h2>

            <p className="mt-5 max-w-[54ch] text-[13px] leading-relaxed text-[var(--color-fog)]">
              PortPilot watched the OCEANS-X arrival feed all day, absorbed{" "}
              <strong className="font-semibold text-[var(--color-chalk)]">
                {S.etaChanges} ETA revisions
              </strong>
              , rescheduled{" "}
              <strong className="font-semibold text-[var(--color-starboard)]">
                {S.autoResolved} vessels autonomously
              </strong>
              , and escalated{" "}
              <strong className="font-semibold text-[var(--color-port)]">
                {S.pendingReview + S.correction + S.inspection}
              </strong>{" "}
              cases it refused to decide alone.
            </p>

            <div className="mt-7 flex flex-wrap items-center gap-2.5">
              <Link to="/agent">
                <span className="mono inline-flex items-center gap-2 rounded-[3px] border border-[color-mix(in_srgb,var(--color-signal)_55%,transparent)] bg-[color-mix(in_srgb,var(--color-signal)_10%,transparent)] px-3.5 py-2 text-[10.5px] tracking-[0.12em] text-[var(--color-signal)] uppercase transition-colors hover:bg-[color-mix(in_srgb,var(--color-signal)_20%,transparent)]">
                  Open decision trace <ArrowUpRight size={12} />
                </span>
              </Link>
              <Link to="/port-calls">
                <span className="mono inline-flex items-center gap-2 rounded-[3px] border border-[var(--color-rail)] px-3.5 py-2 text-[10.5px] tracking-[0.12em] text-[var(--color-fog)] uppercase transition-colors hover:border-[var(--color-mist)] hover:text-[var(--color-chalk)]">
                  Compliance queue <ArrowUpRight size={12} />
                </span>
              </Link>
            </div>
          </div>

          <div className="bg-[var(--color-hull)] px-7 py-7">
            <ArrivalCurve />
          </div>
        </div>
      </Panel>

      {/* ---------------- metric plate ---------------- */}
      <Panel className="rise" ticked>
        <div className="grid grid-cols-2 gap-px bg-[var(--color-rail)] md:grid-cols-3 xl:grid-cols-6">
          {[
            { label: "ETA revisions", value: S.etaChanges, hint: "received from OCEANS-X today", tone: "mute" as const },
            { label: "Auto-rescheduled", value: S.autoResolved, hint: "no human in the loop", tone: "clear" as const },
            { label: "Pending review", value: S.pendingReview, hint: "no valid option existed", tone: "blocked" as const },
            { label: "Unconfirmed", value: S.unconfirmed, hint: "awaiting retry pass", tone: "hold" as const },
            {
              label: "Berth demand",
              value: S.berthUtilisation,
              unit: "%",
              hint:
                S.berthUtilisation > 100
                  ? "of berth-hours available — demand exceeds the pool"
                  : "of berth-hours available across the pool",
              tone: S.berthUtilisation > 100 ? ("blocked" as const) : ("mute" as const),
            },
            { label: "Docs extracted", value: S.documents, hint: `${S.fieldsExtracted} fields · ${(S.avgConfidence * 100).toFixed(0)}% mean confidence`, tone: "agent" as const },
          ].map((m, i) => (
            <div key={m.label} className="bg-[var(--color-hull)]">
              <Metric {...m} delay={i * 60} />
            </div>
          ))}
        </div>
      </Panel>

      {/* ---------------- main grid ---------------- */}
      <div className="grid gap-5 xl:grid-cols-[1.45fr_1fr]">
        <div className="space-y-5">
          <Panel className="rise" ticked>
            <PanelHead
              title="Arrival board"
              sub="Next inbound movements, sorted by current ETA"
              right={
                <Link
                  to="/arrivals"
                  className="mono text-[10px] tracking-[0.12em] text-[var(--color-slate-ink)] uppercase transition-colors hover:text-[var(--color-signal)]"
                >
                  all {S.arrivals} →
                </Link>
              }
            />
            <table className="w-full">
              <thead>
                <tr className="border-b border-[var(--color-rail)]">
                  {["Vessel", "IMO", "From", "ETA", "Δ", "Berth", "Status"].map(
                    (h) => (
                      <th
                        key={h}
                        className="label px-5 py-2 text-left first:pl-5 last:pr-5"
                      >
                        {h}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody>
                {upcoming.map((v, i) => {
                  const d = v.previous_eta
                    ? deltaMinutes(v.previous_eta, v.current_eta)
                    : 0;
                  return (
                    <tr
                      key={`${v.vessel_name}-${v.imo_number}`}
                      className="rise group border-b border-dashed border-[var(--color-rail)] transition-colors last:border-0 hover:bg-[color-mix(in_srgb,var(--color-plate)_70%,transparent)]"
                      style={{ animationDelay: `${i * 40}ms` }}
                    >
                      <td className="px-5 py-2.5">
                        <div className="text-[12.5px] font-medium text-[var(--color-chalk)]">
                          {v.vessel_name}
                        </div>
                        <div className="mono text-[9.5px] tracking-[0.06em] text-[var(--color-slate-ink)] uppercase">
                          {v.vessel_type ?? v.flag}
                        </div>
                      </td>
                      <td className="mono px-5 py-2.5 text-[11px] text-[var(--color-fog)]">
                        {v.imo_number}
                      </td>
                      <td className="px-5 py-2.5 text-[11.5px] text-[var(--color-fog)]">
                        {v.location_from}
                      </td>
                      <td className="mono px-5 py-2.5 text-[12.5px] text-[var(--color-chalk)]">
                        {hhmm(v.current_eta)}
                      </td>
                      <td className="px-5 py-2.5">
                        {d === 0 ? (
                          <span className="mono text-[11px] text-[var(--color-slate-ink)]">
                            —
                          </span>
                        ) : (
                          <span
                            className={`mono text-[11px] ${
                              d > 0
                                ? "text-[var(--color-port)]"
                                : "text-[var(--color-starboard)]"
                            }`}
                          >
                            {humanDelta(d)}
                          </span>
                        )}
                      </td>
                      <td className="mono px-5 py-2.5 text-[11px] text-[var(--color-fog)]">
                        {v.allocations.berth?.resource_id}
                      </td>
                      <td className="px-5 py-2.5">
                        <StatusChip status={v.allocations.berth?.status ?? "—"} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </Panel>

          <Panel className="rise" ticked>
            <PanelHead
              title="Berth occupancy"
              sub="Allocated windows across the active berth pool"
              accent="var(--color-beacon)"
              right={
                <Link
                  to="/berths"
                  className="mono text-[10px] tracking-[0.12em] text-[var(--color-slate-ink)] uppercase transition-colors hover:text-[var(--color-signal)]"
                >
                  full plan →
                </Link>
              }
            />
            <div className="px-5 py-4">
              <BerthTimeline vessels={VESSELS} resource="berth" maxRows={7} compact />
            </div>
          </Panel>
        </div>

        <div className="space-y-5">
          <Panel className="rise" ticked live>
            <PanelHead
              title="Activity"
              sub="Every autonomous action, in order"
              accent="var(--color-starboard)"
              right={
                <Chip tone="clear" dot>
                  streaming
                </Chip>
              }
            />
            <Feed />
          </Panel>

          <Panel className="rise" ticked>
            <PanelHead
              title="Needs a human"
              sub="Cases the agents deliberately refused to decide"
              accent="var(--color-port)"
            />
            <ul>
              {escalations.map((e, i) => (
                <li
                  key={e.id}
                  className="rise border-b border-dashed border-[var(--color-rail)] last:border-0"
                  style={{ animationDelay: `${i * 45}ms` }}
                >
                  <Link
                    to={e.to}
                    className="flex items-start justify-between gap-3 px-5 py-3 transition-colors hover:bg-[color-mix(in_srgb,var(--color-plate)_70%,transparent)]"
                  >
                    <div className="min-w-0">
                      <div className="mono text-[10.5px] tracking-[0.08em] text-[var(--color-chalk)] uppercase">
                        {e.title}
                      </div>
                      <p className="mt-1 text-[11.5px] leading-snug text-[var(--color-slate-ink)]">
                        {e.detail}
                      </p>
                    </div>
                    <StatusChip status={e.status} />
                  </Link>
                </li>
              ))}
            </ul>
          </Panel>

          <Panel className="rise" ticked>
            <PanelHead
              title="Last agent run"
              sub={AGENT_RUNS[0] ? stamp(AGENT_RUNS[0].started_at) : ""}
              accent="var(--color-beacon)"
            />
            {AGENT_RUNS[0] && (
              <div className="px-5 py-4">
                <div className="flex items-center justify-between">
                  <span className="display text-[13px] text-[var(--color-chalk)]">
                    {AGENT_RUNS[0].vessel_name}
                  </span>
                  <StatusChip status={AGENT_RUNS[0].outcome} />
                </div>
                <p className="mt-3 border-l-2 border-[var(--color-beacon)] pl-3 text-[12px] leading-relaxed text-[var(--color-fog)] italic">
                  “{AGENT_RUNS[0].rationale}”
                </p>
                <div className="mono mt-4 flex flex-wrap gap-x-5 gap-y-1 text-[10px] text-[var(--color-slate-ink)]">
                  <span>
                    {AGENT_RUNS[0].options_generated} options generated
                  </span>
                  <span>{AGENT_RUNS[0].options_valid} valid</span>
                  <span>{AGENT_RUNS[0].duration_ms} ms</span>
                </div>
                <Link
                  to="/agent"
                  className="mono mt-4 inline-flex items-center gap-1.5 text-[10px] tracking-[0.12em] text-[var(--color-beacon)] uppercase hover:underline"
                >
                  Inspect full trace <ArrowUpRight size={11} />
                </Link>
              </div>
            )}
          </Panel>
        </div>
      </div>
    </div>
  );
}
