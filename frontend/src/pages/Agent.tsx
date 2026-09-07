import { useEffect, useMemo, useState } from "react";
import {
  Check,
  Cpu,
  Database,
  Lock,
  Play,
  Radar,
  Ruler,
  TriangleAlert,
} from "lucide-react";

import { Button, Chip, Panel, PanelHead, StatusChip } from "../components/ui";
import { hhmm, humanDelta, deltaMinutes, relative, stamp } from "../lib/format";
import { useData } from "../lib/store";
import type { AgentRun, ScheduleOption } from "../lib/types";

const ACTOR = {
  monitor: { icon: Radar, label: "monitor", color: "var(--color-fog)" },
  agent: { icon: Cpu, label: "llm agent", color: "var(--color-beacon)" },
  rules: { icon: Ruler, label: "deterministic rules", color: "var(--color-signal)" },
  database: { icon: Database, label: "postgres", color: "var(--color-starboard)" },
} as const;

/* ------------------------------------------------------------
   Before / after window strip
   ------------------------------------------------------------ */
function MoveStrip({ option }: { option: ScheduleOption }) {
  const move = option.moves[0];
  if (!move) return null;
  const shift = deltaMinutes(move.from_start, move.to_start);
  return (
    <div className="rounded-[3px] border border-[var(--color-rail)] bg-[color-mix(in_srgb,var(--color-abyss)_60%,transparent)] px-4 py-3.5">
      <div className="flex items-center justify-between">
        <span className="label">Applied move · berth</span>
        <span
          className={`mono text-[11px] ${
            shift > 0 ? "text-[var(--color-port)]" : "text-[var(--color-starboard)]"
          }`}
        >
          {humanDelta(shift)}
        </span>
      </div>
      <div className="mt-3 space-y-2">
        {[
          { tag: "before", res: move.from_resource, start: move.from_start, dim: true },
          { tag: "after", res: move.to_resource, start: move.to_start, dim: false },
        ].map((row) => (
          <div key={row.tag} className="flex items-center gap-3">
            <span className="label w-12 shrink-0">{row.tag}</span>
            <span
              className={`mono w-[86px] shrink-0 text-[11px] ${
                row.dim
                  ? "text-[var(--color-slate-ink)] line-through"
                  : "text-[var(--color-chalk)]"
              }`}
            >
              {row.res}
            </span>
            <div className="relative h-[7px] flex-1 overflow-hidden rounded-full bg-[var(--color-rail)]">
              <div
                className="absolute inset-y-0 rounded-full transition-all duration-700"
                style={{
                  left: `${((new Date(row.start).getHours() * 60 + new Date(row.start).getMinutes()) / 1440) * 100}%`,
                  width: "22%",
                  background: row.dim
                    ? "var(--color-mist)"
                    : "linear-gradient(90deg, var(--color-starboard), color-mix(in srgb, var(--color-starboard) 40%, transparent))",
                }}
              />
            </div>
            <span
              className={`mono w-[46px] shrink-0 text-right text-[11px] ${
                row.dim ? "text-[var(--color-slate-ink)]" : "text-[var(--color-chalk)]"
              }`}
            >
              {hhmm(row.start)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------
   Run detail
   ------------------------------------------------------------ */
function RunDetail({ run }: { run: AgentRun }) {
  const { scheduleChanges: SCHEDULE_CHANGES } = useData();
  const [revealed, setRevealed] = useState(run.steps.length);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    setRevealed(run.steps.length);
    setPlaying(false);
  }, [run.run_id, run.steps.length]);

  useEffect(() => {
    if (!playing) return;
    if (revealed >= run.steps.length) {
      setPlaying(false);
      return;
    }
    const t = setTimeout(() => setRevealed((r) => r + 1), 620);
    return () => clearTimeout(t);
  }, [playing, revealed, run.steps.length]);

  const replay = () => {
    setRevealed(0);
    setPlaying(true);
  };

  const selected = run.options.find(
    (o) => o.option_id === run.selected_option && o.moves.length > 0,
  );
  const ranked = [...run.options].sort(
    (a, b) => (a.rank ?? 99) - (b.rank ?? 99),
  );

  return (
    <div className="space-y-5">
      <Panel ticked className="rise">
        <PanelHead
          title={run.vessel_name}
          sub={`${run.run_id} · triggered by ${run.trigger.replace("_", " ").toLowerCase()} · ${stamp(run.started_at)}`}
          accent={
            run.outcome === "resources_allocated"
              ? "var(--color-starboard)"
              : "var(--color-port)"
          }
          right={
            <div className="flex items-center gap-2">
              <StatusChip status={run.outcome} />
              <Button variant="signal" onClick={replay}>
                <span className="inline-flex items-center gap-1.5">
                  <Play size={10} /> replay
                </span>
              </Button>
            </div>
          }
        />

        <div className="grid grid-cols-2 gap-px border-b border-[var(--color-rail)] bg-[var(--color-rail)] md:grid-cols-4">
          {[
            { k: "Previous ETA", v: hhmm(run.previous_eta) },
            { k: "New ETA", v: hhmm(run.new_eta), accent: true },
            {
              k: "Shift",
              v: run.previous_eta
                ? humanDelta(deltaMinutes(run.previous_eta, run.new_eta))
                : "—",
            },
            { k: "Agent latency", v: `${run.duration_ms} ms` },
          ].map((c) => (
            <div key={c.k} className="bg-[var(--color-hull)] px-5 py-3.5">
              <div className="label">{c.k}</div>
              <div
                className={`mono mt-1.5 text-[16px] ${
                  c.accent
                    ? "text-[var(--color-signal)]"
                    : "text-[var(--color-chalk)]"
                }`}
              >
                {c.v}
              </div>
            </div>
          ))}
        </div>

        {/* pipeline */}
        <ol className="relative px-6 py-5">
          <div className="absolute top-8 bottom-8 left-[33px] w-px bg-[var(--color-rail)]" />
          {run.steps.map((s, i) => {
            const meta = ACTOR[s.actor];
            const Icon = meta.icon;
            const shown = i < revealed;
            return (
              <li
                key={s.key}
                className="relative flex gap-4 pb-5 last:pb-0"
                style={{
                  opacity: shown ? 1 : 0.12,
                  transform: shown ? "none" : "translateY(6px)",
                  transition: "opacity .4s ease, transform .4s ease",
                }}
              >
                <span
                  className="relative z-10 mt-0.5 flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-full border bg-[var(--color-hull)]"
                  style={{
                    borderColor:
                      s.status === "blocked" ? "var(--color-port)" : meta.color,
                  }}
                >
                  {s.status === "blocked" ? (
                    <Lock size={9} className="text-[var(--color-port)]" />
                  ) : (
                    <Check size={9} style={{ color: meta.color }} />
                  )}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                    <h4 className="text-[13px] font-semibold text-[var(--color-chalk)]">
                      {s.title}
                    </h4>
                    <span
                      className="mono inline-flex items-center gap-1 text-[9.5px] tracking-[0.1em] uppercase"
                      style={{ color: meta.color }}
                    >
                      <Icon size={10} /> {meta.label}
                    </span>
                    <span className="mono text-[9.5px] text-[var(--color-slate-ink)]">
                      {s.ms} ms
                    </span>
                  </div>
                  <p className="mt-1 max-w-[80ch] text-[12px] leading-relaxed text-[var(--color-fog)]">
                    {s.detail}
                  </p>
                </div>
              </li>
            );
          })}
        </ol>

        <div className="border-t border-[var(--color-rail)] px-6 py-5">
          <div className="label mb-2.5">Agent rationale</div>
          <blockquote className="border-l-2 border-[var(--color-beacon)] pl-4 text-[13px] leading-relaxed text-[var(--color-chalk)] italic">
            {run.rationale}
          </blockquote>
        </div>
      </Panel>

      <div className="grid gap-5 xl:grid-cols-[1.5fr_1fr]">
        <Panel ticked className="rise">
          <PanelHead
            title="Generated options"
            sub={`${run.options_generated} produced deterministically · ${run.options_valid} survived the hard constraints`}
            accent="var(--color-signal)"
          />
          <div className="scroll-thin overflow-x-auto">
            <table className="w-full min-w-[640px]">
              <thead>
                <tr className="border-b border-[var(--color-rail)]">
                  {["Rank", "Option", "Berth", "Window", "Displaces", "Shift", "Verdict"].map(
                    (h) => (
                      <th key={h} className="label px-4 py-2.5 text-left">
                        {h}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody>
                {ranked.map((o, i) => {
                  const chosen = o.option_id === run.selected_option;
                  return (
                    <tr
                      key={o.option_id}
                      className={`rise border-b border-dashed border-[var(--color-rail)] last:border-0 ${
                        chosen
                          ? "bg-[color-mix(in_srgb,var(--color-starboard)_8%,transparent)]"
                          : ""
                      }`}
                      style={{ animationDelay: `${i * 45}ms` }}
                    >
                      <td className="px-4 py-2.5">
                        {o.rank ? (
                          <span
                            className={`numeral text-[18px] ${
                              o.rank === 1
                                ? "text-[var(--color-starboard)]"
                                : "text-[var(--color-slate-ink)]"
                            }`}
                          >
                            {o.rank}
                          </span>
                        ) : (
                          <span className="mono text-[11px] text-[var(--color-slate-ink)]">
                            —
                          </span>
                        )}
                      </td>
                      <td className="mono px-4 py-2.5 text-[11.5px] text-[var(--color-chalk)]">
                        {o.option_id}
                        {chosen && (
                          <Chip tone="clear" className="ml-2">
                            applied
                          </Chip>
                        )}
                      </td>
                      <td className="mono px-4 py-2.5 text-[11px] text-[var(--color-fog)]">
                        {o.moves[0]?.to_resource ?? "—"}
                      </td>
                      <td className="mono px-4 py-2.5 text-[11px] text-[var(--color-fog)]">
                        {o.moves[0]
                          ? `${hhmm(o.moves[0].to_start)} – ${hhmm(o.moves[0].to_end)}`
                          : "—"}
                      </td>
                      <td className="px-4 py-2.5 text-[11px] text-[var(--color-fog)]">
                        {o.displaced_vessels.length
                          ? o.displaced_vessels.join(", ")
                          : "—"}
                      </td>
                      <td className="mono px-4 py-2.5 text-[11px] text-[var(--color-fog)]">
                        {o.total_shift_minutes} min
                      </td>
                      <td className="px-4 py-2.5">
                        {o.valid ? (
                          <Chip tone="clear">valid</Chip>
                        ) : (
                          <span
                            className="inline-flex items-start gap-1.5"
                            title={o.invalid_reason ?? ""}
                          >
                            <TriangleAlert
                              size={11}
                              className="mt-[3px] shrink-0 text-[var(--color-port)]"
                            />
                            {/* The rejection reason is the evidence that the
                                agent refused for a stated cause — never clip it. */}
                            <span className="max-w-[30ch] text-[11px] leading-snug text-balance text-[var(--color-port)]">
                              {o.invalid_reason}
                            </span>
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Panel>

        <div className="space-y-5">
          {selected ? (
            <Panel ticked className="rise">
              <PanelHead
                title="What changed"
                sub="Written under a row-level lock, then re-read to verify"
                accent="var(--color-starboard)"
              />
              <div className="px-5 py-4">
                <MoveStrip option={selected} />
              </div>
            </Panel>
          ) : (
            <Panel ticked className="rise">
              <PanelHead
                title="Nothing was written"
                sub="The agent escalated instead of displacing confirmed traffic"
                accent="var(--color-port)"
              />
              <p className="px-5 py-5 text-[12px] leading-relaxed text-[var(--color-fog)]">
                Every generated option failed a hard constraint. The allocation
                was flagged{" "}
                <span className="mono text-[var(--color-port)]">pending_review</span>{" "}
                and no row in the allocation tables was modified — the agent has
                no authority to break a buffer rule.
              </p>
            </Panel>
          )}

          <Panel ticked className="rise">
            <PanelHead
              title="Change ledger"
              sub="schedule_changes rows written by this vessel's runs"
            />
            <ul>
              {SCHEDULE_CHANGES.filter((c) => c.imo_number === run.imo_number)
                .slice(0, 6)
                .map((c) => (
                  <li
                    key={c.change_id}
                    className="border-b border-dashed border-[var(--color-rail)] px-5 py-3 last:border-0"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span className="mono text-[11px] text-[var(--color-chalk)]">
                        #{c.change_id} · {c.resource_type} {c.resource_id}
                      </span>
                      <Chip tone="agent">{c.execution_mode}</Chip>
                    </div>
                    <div className="mono mt-1.5 text-[10.5px] text-[var(--color-slate-ink)]">
                      {hhmm(c.old_start_time)} → {hhmm(c.new_start_time)} ·{" "}
                      {relative(c.changed_at)}
                    </div>
                  </li>
                ))}
              {SCHEDULE_CHANGES.filter((c) => c.imo_number === run.imo_number)
                .length === 0 && (
                <li className="px-5 py-5 text-[12px] text-[var(--color-slate-ink)]">
                  No rows written for this vessel.
                </li>
              )}
            </ul>
          </Panel>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------
   Page
   ------------------------------------------------------------ */
export default function Agent() {
  const { agentRuns: AGENT_RUNS } = useData();
  const [runId, setRunId] = useState<string>("");
  const run = useMemo(
    () => AGENT_RUNS.find((r) => r.run_id === runId) ?? AGENT_RUNS[0],
    [runId, AGENT_RUNS],
  );

  if (!run)
    return (
      <p className="text-[12px] text-[var(--color-slate-ink)]">No agent runs.</p>
    );

  return (
    <div className="mx-auto grid max-w-[1560px] gap-5 pb-10 xl:grid-cols-[300px_1fr]">
      <Panel ticked className="rise h-fit">
        <PanelHead
          title="Agent runs"
          sub={`${AGENT_RUNS.length} on this operating day`}
        />
        <ul>
          {AGENT_RUNS.map((r, i) => {
            const active = r.run_id === run.run_id;
            return (
              <li key={r.run_id}>
                <button
                  onClick={() => setRunId(r.run_id)}
                  className={`rise relative w-full cursor-pointer border-b border-dashed border-[var(--color-rail)] px-5 py-3.5 text-left transition-colors ${
                    active
                      ? "bg-[color-mix(in_srgb,var(--color-beacon)_9%,transparent)]"
                      : "hover:bg-[color-mix(in_srgb,var(--color-plate)_70%,transparent)]"
                  }`}
                  style={{ animationDelay: `${i * 50}ms` }}
                >
                  <span
                    className={`absolute inset-y-0 left-0 w-[2px] ${
                      active ? "bg-[var(--color-beacon)]" : "bg-transparent"
                    }`}
                  />
                  <div className="flex items-center justify-between gap-2">
                    <span className="mono text-[10px] text-[var(--color-slate-ink)]">
                      {r.run_id}
                    </span>
                    <StatusChip status={r.outcome} />
                  </div>
                  <div className="mt-1.5 text-[12.5px] font-medium text-[var(--color-chalk)]">
                    {r.vessel_name}
                  </div>
                  <div className="mono mt-1 text-[10px] text-[var(--color-slate-ink)]">
                    {r.previous_eta
                      ? humanDelta(deltaMinutes(r.previous_eta, r.new_eta))
                      : "new"}{" "}
                    · {r.options_valid}/{r.options_generated} valid ·{" "}
                    {relative(r.started_at)}
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      </Panel>

      <RunDetail key={run.run_id} run={run} />
    </div>
  );
}
