import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft,
  Biohazard,
  Check,
  ChevronRight,
  CircleAlert,
  FileText,
  Flame,
  ScanLine,
  Star,
  TriangleAlert,
} from "lucide-react";

import {
  Button,
  Chip,
  ConfidenceBar,
  KeyVal,
  Panel,
  PanelHead,
  RiskMeter,
  StatusChip,
} from "../components/ui";
import { relative, stamp, titleCase } from "../lib/format";
import { DOCUMENT_LABELS } from "../lib/mock/portops";
import { useData } from "../lib/store";
import type { PortCallEvent, PortCallPhase, PortCallStatus } from "../lib/types";

const PHASES: { key: PortCallPhase; label: string; note: string }[] = [
  { key: "arrival", label: "Arrival", note: "Declarations, identity, health" },
  { key: "operations", label: "Operations", note: "Alongside, cargo working" },
  { key: "departure", label: "Departure", note: "Clearance to sail" },
];

const FACTOR_WEIGHT: Record<string, number> = {
  "Compliance issues detected.": 30,
  "Human compliance review required.": 20,
  "Dangerous goods declared.": 25,
  "Radioactive material declared.": 40,
  "First Singapore port call.": 10,
  "Inconsistencies detected across documents.": 30,
};

const SEVERITY_ICON: Record<string, typeof CircleAlert> = {
  error: CircleAlert,
  warning: TriangleAlert,
  info: FileText,
};

/** The compliance engine emits ERROR/WARNING; the demo set emits lowercase. */
const severityIcon = (severity: string) =>
  SEVERITY_ICON[String(severity).toLowerCase()] ?? FileText;

const isError = (severity: string) =>
  String(severity).toLowerCase() === "error";

export default function PortCallDetail() {
  const { id = "" } = useParams();
  const { portCalls } = useData();
  const base = portCalls.find((p) => p.port_call_id === id);
  const [status, setStatus] = useState<PortCallStatus | null>(null);
  const [openDoc, setOpenDoc] = useState<string | null>(null);

  const call = useMemo(
    () => (base ? { ...base, status: status ?? base.status } : null),
    [base, status],
  );

  const localEvents = useMemo<PortCallEvent[]>(() => {
    if (!call || !status) return call?.events ?? [];
    const extra: PortCallEvent[] = [];
    if (status === "inspection_in_progress")
      extra.push({
        event: "INSPECTION_STARTED",
        description: "Boarding officer dispatched from this console.",
        source: "port_officer",
        at: new Date().toISOString(),
      });
    if (status === "inspection_cleared")
      extra.push({
        event: "INSPECTION_COMPLETED",
        description: "Inspection cleared with no findings. Phase may advance.",
        source: "port_officer",
        at: new Date().toISOString(),
      });
    if (status === "inspection_rejected")
      extra.push({
        event: "INSPECTION_REJECTED",
        description: "Findings recorded. The vessel cannot clear this phase.",
        source: "port_officer",
        at: new Date().toISOString(),
      });
    return [...extra, ...call.events];
  }, [call, status]);

  if (!call)
    return (
      <div className="mx-auto max-w-[900px] py-20 text-center">
        <p className="text-[13px] text-[var(--color-fog)]">
          Port call <span className="mono">{id}</span> not found.
        </p>
        <Link
          to="/port-calls"
          className="mono mt-4 inline-block text-[11px] tracking-[0.12em] text-[var(--color-signal)] uppercase hover:underline"
        >
          ← back to the queue
        </Link>
      </div>
    );

  const phaseIdx = PHASES.findIndex((p) => p.key === call.phase);
  const halted = [
    "correction_required",
    "human_review",
    "inspection_required",
    "inspection_in_progress",
    "inspection_rejected",
  ].includes(call.status);

  return (
    <div className="mx-auto max-w-[1560px] space-y-5 pb-10">
      <Link
        to="/port-calls"
        className="mono inline-flex items-center gap-1.5 text-[10px] tracking-[0.12em] text-[var(--color-slate-ink)] uppercase transition-colors hover:text-[var(--color-signal)]"
      >
        <ArrowLeft size={11} /> compliance queue
      </Link>

      {/* ---------------- header ---------------- */}
      <Panel className="rise" ticked>
        <div className="grid gap-px bg-[var(--color-rail)] lg:grid-cols-[1.4fr_1fr]">
          <div className="bg-[var(--color-hull)] px-7 py-6">
            <div className="flex items-center gap-2.5">
              <span className="label">{call.port_call_id}</span>
              <StatusChip status={call.status} dot />
            </div>
            <h2 className="display-tight mt-3 text-[38px] leading-none text-[var(--color-chalk)]">
              {call.vessel_name}
            </h2>
            <div className="mono mt-3 flex flex-wrap items-center gap-x-5 gap-y-1.5 text-[11px] text-[var(--color-fog)]">
              <span>IMO {call.imo_number}</span>
              <span>{call.call_sign}</span>
              <span>{call.flag}</span>
              <span>berth {call.berth}</span>
              <span>ETA {stamp(call.eta)}</span>
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-2">
              {call.carrying_dangerous_goods && (
                <Chip tone="hold">
                  <Flame size={10} /> dangerous goods
                </Chip>
              )}
              {call.radioactive_material && (
                <Chip tone="blocked">
                  <Biohazard size={10} /> radioactive
                </Chip>
              )}
              {call.first_singapore_call && (
                <Chip tone="agent">
                  <Star size={10} /> first singapore call
                </Chip>
              )}
              <Chip tone="mute">{call.purpose_of_call}</Chip>
            </div>
          </div>

          {/* phase stepper */}
          <div className="bg-[var(--color-hull)] px-7 py-6">
            <div className="label mb-4">Workflow phase</div>
            <ol className="space-y-3.5">
              {PHASES.map((p, i) => {
                const done = i < phaseIdx;
                const current = i === phaseIdx;
                const color = done
                  ? "var(--color-starboard)"
                  : current
                    ? halted
                      ? "var(--color-port)"
                      : "var(--color-signal)"
                    : "var(--color-rail)";
                return (
                  <li key={p.key} className="flex items-center gap-3.5">
                    <span
                      className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-[10px]"
                      style={{ borderColor: color, color }}
                    >
                      {done ? <Check size={11} /> : i + 1}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div
                        className="text-[12.5px] font-semibold"
                        style={{
                          color: done || current ? "var(--color-chalk)" : "var(--color-slate-ink)",
                        }}
                      >
                        {p.label}
                      </div>
                      <div className="text-[10.5px] text-[var(--color-slate-ink)]">
                        {p.note}
                      </div>
                    </div>
                    <div
                      className="h-[3px] w-16 rounded-full"
                      style={{ background: color }}
                    />
                  </li>
                );
              })}
            </ol>
          </div>
        </div>
      </Panel>

      <div className="grid gap-5 xl:grid-cols-[1.5fr_1fr]">
        {/* ================= left ================= */}
        <div className="space-y-5">
          <Panel className="rise" ticked>
            <PanelHead
              title="Agent decision"
              sub={`Compliance ${call.compliance.status} · escalation ${call.escalation.action}`}
              accent="var(--color-beacon)"
              right={
                <Chip tone={call.agent_action === "PROCEED" ? "clear" : "hold"}>
                  {call.agent_action.replace(/_/g, " ")}
                </Chip>
              }
            />
            <div className="px-6 py-5">
              <blockquote className="border-l-2 border-[var(--color-beacon)] pl-4 text-[13px] leading-relaxed text-[var(--color-chalk)] italic">
                {call.agent_reasoning}
              </blockquote>
              <p className="mt-4 text-[12px] leading-relaxed text-[var(--color-fog)]">
                {call.escalation.message}
              </p>
            </div>
          </Panel>

          <Panel className="rise" ticked>
            <PanelHead
              title="Compliance findings"
              sub={
                call.compliance.issues.length
                  ? `${call.compliance.issues.length} issue(s) raised by the deterministic rule engine`
                  : "Every required document present and internally consistent"
              }
              accent={
                call.compliance.issues.length
                  ? "var(--color-port)"
                  : "var(--color-starboard)"
              }
            />
            {call.compliance.issues.length === 0 ? (
              <div className="flex items-center gap-3 px-6 py-6">
                <span className="flex h-7 w-7 items-center justify-center rounded-full border border-[color-mix(in_srgb,var(--color-starboard)_45%,transparent)] text-[var(--color-starboard)]">
                  <Check size={13} />
                </span>
                <p className="text-[12.5px] text-[var(--color-fog)]">
                  No findings. Cross-document identity fields agree and every
                  document required for this phase was submitted.
                </p>
              </div>
            ) : (
              <ul>
                {call.compliance.issues.map((issue, i) => {
                  const Icon = severityIcon(issue.severity);
                  const tone = isError(issue.severity)
                    ? "var(--color-port)"
                    : "var(--color-signal)";
                  return (
                    <li
                      key={issue.code + i}
                      className="rise flex gap-3.5 border-b border-dashed border-[var(--color-rail)] px-6 py-4 last:border-0"
                      style={{ animationDelay: `${i * 60}ms` }}
                    >
                      <Icon size={15} style={{ color: tone }} className="mt-0.5 shrink-0" />
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="mono text-[10.5px] tracking-[0.1em]" style={{ color: tone }}>
                            {issue.code}
                          </span>
                          {issue.document_type && (
                            <Chip tone="mute">
                              {DOCUMENT_LABELS[issue.document_type] ??
                                titleCase(issue.document_type)}
                            </Chip>
                          )}
                          {issue.field && (
                            <span className="mono text-[10px] text-[var(--color-slate-ink)]">
                              field: {issue.field}
                            </span>
                          )}
                        </div>
                        <p className="mt-1.5 text-[12.5px] leading-relaxed text-[var(--color-fog)]">
                          {issue.message}
                        </p>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </Panel>

          <Panel className="rise" ticked>
            <PanelHead
              title="Extracted documents"
              sub={`${call.documents.length} submitted · click to inspect the extracted fields`}
            />
            <ul>
              {call.documents.map((d, i) => {
                const fields = Object.entries(d.fields);
                const mean =
                  fields.reduce((a, [, f]) => a + f.confidence, 0) /
                  Math.max(1, fields.length);
                const open = openDoc === d.document_id;
                return (
                  <li
                    key={d.document_id}
                    className="rise border-b border-dashed border-[var(--color-rail)] last:border-0"
                    style={{ animationDelay: `${i * 40}ms` }}
                  >
                    <button
                      onClick={() => setOpenDoc(open ? null : d.document_id)}
                      className="flex w-full cursor-pointer items-center gap-3 px-6 py-3.5 text-left transition-colors hover:bg-[color-mix(in_srgb,var(--color-plate)_70%,transparent)]"
                    >
                      <ChevronRight
                        size={13}
                        className={`shrink-0 text-[var(--color-slate-ink)] transition-transform ${open ? "rotate-90" : ""}`}
                      />
                      {d.extraction_method === "textract_ocr" ? (
                        <ScanLine size={14} className="shrink-0 text-[var(--color-signal)]" />
                      ) : (
                        <FileText size={14} className="shrink-0 text-[var(--color-slate-ink)]" />
                      )}
                      <div className="min-w-0 flex-1">
                        <div className="text-[12.5px] font-medium text-[var(--color-chalk)]">
                          {DOCUMENT_LABELS[d.document_type] ?? titleCase(d.document_type)}
                        </div>
                        <div className="mono text-[10px] text-[var(--color-slate-ink)]">
                          {d.document_id} · {d.pages} pp ·{" "}
                          {d.extraction_method === "textract_ocr"
                            ? "Textract OCR"
                            : "PDF text layer"}{" "}
                          · {fields.length} fields
                        </div>
                      </div>
                      <ConfidenceBar value={mean} />
                    </button>

                    {open && (
                      <div className="grid gap-x-8 gap-y-0 border-t border-[var(--color-rail)] bg-[color-mix(in_srgb,var(--color-abyss)_55%,transparent)] px-6 py-3 md:grid-cols-2">
                        {fields.map(([k, f]) => (
                          <div
                            key={k}
                            className="flex items-center justify-between gap-4 border-b border-dashed border-[var(--color-rail)] py-2 last:border-0"
                          >
                            <span className="label shrink-0">{k}</span>
                            <div className="flex items-center gap-3">
                              <span
                                className={`mono text-[12px] ${
                                  f.value === null
                                    ? "text-[var(--color-port)] italic"
                                    : "text-[var(--color-chalk)]"
                                }`}
                              >
                                {f.value === null ? "not found" : String(f.value)}
                              </span>
                              <ConfidenceBar value={f.confidence} />
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          </Panel>
        </div>

        {/* ================= right ================= */}
        <div className="space-y-5">
          <Panel className="rise" ticked>
            <PanelHead
              title="Risk assessment"
              sub="Rule-based and fully explainable — no model in this path"
              accent={
                call.risk.risk_level === "high"
                  ? "var(--color-port)"
                  : call.risk.risk_level === "medium"
                    ? "var(--color-signal)"
                    : "var(--color-starboard)"
              }
            />
            <div className="flex items-center gap-6 px-6 py-5">
              <RiskMeter score={call.risk.risk_score} level={call.risk.risk_level} />
              <div className="min-w-0 flex-1 space-y-2.5">
                {call.risk.risk_factors.length === 0 && (
                  <p className="text-[12px] text-[var(--color-slate-ink)]">
                    No risk factor applies to this port call.
                  </p>
                )}
                {call.risk.risk_factors.map((f) => {
                  const w = FACTOR_WEIGHT[f] ?? 0;
                  return (
                    <div key={f}>
                      <div className="flex items-baseline justify-between gap-3">
                        <span className="text-[11.5px] text-[var(--color-fog)]">
                          {f}
                        </span>
                        <span className="mono text-[11px] text-[var(--color-signal)]">
                          +{w}
                        </span>
                      </div>
                      <div className="mt-1 h-[3px] overflow-hidden rounded-full bg-[var(--color-rail)]">
                        <div
                          className="h-full rounded-full bg-[var(--color-signal)]"
                          style={{ width: `${(w / 40) * 100}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
            <div className="border-t border-[var(--color-rail)] px-6 py-4">
              <KeyVal
                k="Inspection"
                v={call.inspection.decision.replace(/_/g, " ")}
              />
              {call.inspection.reasons.map((r) => (
                <p
                  key={r}
                  className="mt-2 text-[11.5px] leading-relaxed text-[var(--color-slate-ink)]"
                >
                  · {r}
                </p>
              ))}
            </div>
          </Panel>

          {call.inspection.decision === "inspection_required" && (
            <Panel className="rise" ticked>
              <PanelHead
                title="Physical inspection"
                sub="The agent never decides whether a boarding passed — a human does"
                accent="var(--color-port)"
              />
              <div className="px-6 py-5">
                <div className="mb-4 flex items-center gap-2">
                  <span className="label">Current</span>
                  <StatusChip status={call.status} dot />
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    variant="signal"
                    disabled={call.status !== "inspection_required"}
                    onClick={() => setStatus("inspection_in_progress")}
                  >
                    start inspection
                  </Button>
                  <Button
                    variant="ghost"
                    disabled={call.status !== "inspection_in_progress"}
                    onClick={() => setStatus("inspection_cleared")}
                  >
                    complete · cleared
                  </Button>
                  <Button
                    variant="danger"
                    disabled={call.status !== "inspection_in_progress"}
                    onClick={() => setStatus("inspection_rejected")}
                  >
                    complete · findings
                  </Button>
                </div>
                <p className="mt-4 text-[11.5px] leading-relaxed text-[var(--color-slate-ink)]">
                  Maps to <span className="mono">POST /agent/port-calls/{call.port_call_id}/inspection/start</span>{" "}
                  and <span className="mono">…/inspection/complete</span>.
                </p>
              </div>
            </Panel>
          )}

          <Panel className="rise" ticked>
            <PanelHead title="Event log" sub="Append-only, newest first" />
            <ol className="relative px-6 py-4">
              <div className="absolute top-7 bottom-7 left-[31px] w-px bg-[var(--color-rail)]" />
              {localEvents.map((e, i) => (
                <li key={`${e.event}-${i}`} className="relative flex gap-3.5 pb-4 last:pb-0">
                  <span
                    className={`relative z-10 mt-1 h-2 w-2 shrink-0 rounded-full ${
                      i === 0 ? "bg-[var(--color-signal)]" : "bg-[var(--color-mist)]"
                    }`}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline justify-between gap-3">
                      <span className="mono text-[10.5px] tracking-[0.08em] text-[var(--color-chalk)]">
                        {e.event}
                      </span>
                      <span className="mono shrink-0 text-[9.5px] text-[var(--color-slate-ink)]">
                        {relative(e.at)}
                      </span>
                    </div>
                    <p className="mt-1 text-[11.5px] leading-relaxed text-[var(--color-fog)]">
                      {e.description}
                    </p>
                    <span className="mono text-[9.5px] text-[var(--color-slate-ink)]">
                      {e.source}
                    </span>
                  </div>
                </li>
              ))}
            </ol>
          </Panel>
        </div>
      </div>
    </div>
  );
}
