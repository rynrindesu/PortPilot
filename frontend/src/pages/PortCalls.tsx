import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, Biohazard, Flame, Star } from "lucide-react";

import { Chip, Metric, Panel, PanelHead, StatusChip } from "../components/ui";
import { hhmm } from "../lib/format";
import { useComplianceStats, useData } from "../lib/store";
import type { PortCallPhase, PortCallState } from "../lib/types";

const PHASES: PortCallPhase[] = ["arrival", "operations", "departure"];

function PhaseTrack({ call }: { call: PortCallState }) {
  const idx = PHASES.indexOf(call.phase);
  const blocked = ["correction_required", "human_review", "inspection_required", "inspection_in_progress", "inspection_rejected"].includes(
    call.status,
  );
  return (
    <div className="flex items-center gap-1">
      {PHASES.map((p, i) => (
        <div key={p} className="flex items-center gap-1">
          <div
            className="h-[3px] w-9 rounded-full transition-colors"
            style={{
              background:
                i < idx
                  ? "var(--color-starboard)"
                  : i === idx
                    ? blocked
                      ? "var(--color-port)"
                      : "var(--color-signal)"
                    : "var(--color-rail)",
            }}
            title={p}
          />
        </div>
      ))}
    </div>
  );
}

function Flags({ call }: { call: PortCallState }) {
  return (
    <div className="flex items-center gap-1.5">
      {call.carrying_dangerous_goods && (
        <span
          title="Dangerous goods declared"
          className="text-[var(--color-signal)]"
        >
          <Flame size={13} />
        </span>
      )}
      {call.radioactive_material && (
        <span title="Radioactive material" className="text-[var(--color-port)]">
          <Biohazard size={13} />
        </span>
      )}
      {call.first_singapore_call && (
        <span title="First Singapore call" className="text-[var(--color-beacon)]">
          <Star size={13} />
        </span>
      )}
    </div>
  );
}

export default function PortCalls() {
  const { portCalls: PORT_CALLS } = useData();
  const C = useComplianceStats();
  const [phase, setPhase] = useState<"all" | PortCallPhase>("all");

  const rows = useMemo(
    () =>
      PORT_CALLS.filter((p) => phase === "all" || p.phase === phase).sort(
        (a, b) => b.risk.risk_score - a.risk.risk_score,
      ),
    [phase, PORT_CALLS],
  );

  return (
    <div className="mx-auto max-w-[1560px] space-y-5 pb-10">
      <Panel className="rise" ticked>
        <div className="grid grid-cols-2 gap-px bg-[var(--color-rail)] md:grid-cols-3 xl:grid-cols-6">
          <div className="bg-[var(--color-hull)]">
            <Metric label="Open port calls" value={C.total} hint="on the operating day" />
          </div>
          <div className="bg-[var(--color-hull)]">
            <Metric label="Cleared" value={C.cleared} tone="clear" hint="agent cleared without a human" />
          </div>
          <div className="bg-[var(--color-hull)]">
            <Metric label="Correction" value={C.correction} tone="blocked" hint="returned to the ship's agent" />
          </div>
          <div className="bg-[var(--color-hull)]">
            <Metric label="Inspection" value={C.inspection} tone="hold" hint="physical boarding required" />
          </div>
          <div className="bg-[var(--color-hull)]">
            <Metric label="Documents" value={C.documents} hint="parsed this day" tone="agent" />
          </div>
          <div className="bg-[var(--color-hull)]">
            <Metric
              label="Mean confidence"
              value={(C.avgConfidence * 100).toFixed(0)}
              unit="%"
              hint={`${C.fieldsExtracted} extracted fields`}
            />
          </div>
        </div>
      </Panel>

      <Panel className="rise" ticked>
        <PanelHead
          title="Compliance queue"
          sub="Ordered by risk score — the agent's own ranking"
          right={
            <div className="flex gap-1.5">
              {(["all", ...PHASES] as const).map((p) => (
                <button
                  key={p}
                  onClick={() => setPhase(p)}
                  className={`mono cursor-pointer rounded-[3px] border px-3 py-[6px] text-[10px] tracking-[0.12em] uppercase transition-colors ${
                    phase === p
                      ? "border-[color-mix(in_srgb,var(--color-signal)_55%,transparent)] bg-[color-mix(in_srgb,var(--color-signal)_12%,transparent)] text-[var(--color-signal)]"
                      : "border-[var(--color-rail)] text-[var(--color-slate-ink)] hover:text-[var(--color-fog)]"
                  }`}
                >
                  {p}
                </button>
              ))}
            </div>
          }
        />

        <div className="scroll-thin overflow-x-auto">
          <table className="w-full min-w-[1040px]">
            <thead>
              <tr className="border-b border-[var(--color-rail)]">
                {[
                  "Port call",
                  "Vessel",
                  "Phase",
                  "Status",
                  "Risk",
                  "Issues",
                  "Docs",
                  "Agent decision",
                  "",
                ].map((h) => (
                  <th key={h} className="label px-4 py-2.5 text-left">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((p, i) => (
                <tr
                  key={p.port_call_id}
                  className="rise group border-b border-dashed border-[var(--color-rail)] transition-colors last:border-0 hover:bg-[color-mix(in_srgb,var(--color-plate)_70%,transparent)]"
                  style={{ animationDelay: `${i * 45}ms` }}
                >
                  <td className="px-4 py-3">
                    <Link
                      to={`/port-calls/${p.port_call_id}`}
                      className="mono text-[11.5px] text-[var(--color-signal)] hover:underline"
                    >
                      {p.port_call_id}
                    </Link>
                    <div className="mono mt-1 text-[10px] text-[var(--color-slate-ink)]">
                      ETA {hhmm(p.eta)} · {p.berth}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <span className="text-[12.5px] font-medium text-[var(--color-chalk)]">
                        {p.vessel_name}
                      </span>
                      <Flags call={p} />
                    </div>
                    <div className="mono text-[10px] text-[var(--color-slate-ink)]">
                      {p.imo_number} · {p.purpose_of_call}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <PhaseTrack call={p} />
                    <div className="mono mt-1.5 text-[10px] tracking-[0.08em] text-[var(--color-slate-ink)] uppercase">
                      {p.phase}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <StatusChip status={p.status} />
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div className="relative h-[3px] w-14 overflow-hidden rounded-full bg-[var(--color-rail)]">
                        <div
                          className="absolute inset-y-0 left-0 rounded-full"
                          style={{
                            width: `${Math.min(100, (p.risk.risk_score / 120) * 100)}%`,
                            background:
                              p.risk.risk_level === "high"
                                ? "var(--color-port)"
                                : p.risk.risk_level === "medium"
                                  ? "var(--color-signal)"
                                  : "var(--color-starboard)",
                          }}
                        />
                      </div>
                      <span
                        className={`mono text-[12px] ${
                          p.risk.risk_level === "high"
                            ? "text-[var(--color-port)]"
                            : p.risk.risk_level === "medium"
                              ? "text-[var(--color-signal)]"
                              : "text-[var(--color-starboard)]"
                        }`}
                      >
                        {p.risk.risk_score}
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    {p.compliance.issues.length === 0 ? (
                      <span className="mono text-[11px] text-[var(--color-slate-ink)]">
                        none
                      </span>
                    ) : (
                      <span className="mono text-[11px] text-[var(--color-port)]">
                        {p.compliance.issues.length}
                      </span>
                    )}
                  </td>
                  <td className="mono px-4 py-3 text-[11px] text-[var(--color-fog)]">
                    {p.documents.length}
                  </td>
                  <td className="px-4 py-3">
                    <Chip tone={p.agent_action === "PROCEED" ? "clear" : "hold"}>
                      {p.agent_action.replace("REQUEST_", "").replace("_", " ")}
                    </Chip>
                  </td>
                  <td className="px-4 py-3">
                    <Link
                      to={`/port-calls/${p.port_call_id}`}
                      className="inline-flex text-[var(--color-slate-ink)] transition-colors group-hover:text-[var(--color-signal)]"
                      aria-label={`Open ${p.port_call_id}`}
                    >
                      <ArrowUpRight size={14} />
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
