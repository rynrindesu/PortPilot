import { useEffect, useState } from "react";
import { Lock, Play, RefreshCw, Server } from "lucide-react";

import { Button, Chip, KeyVal, Panel, PanelHead, StatusChip } from "../components/ui";
import { runMonitor } from "../lib/api";
import { hhmm, relative, stamp } from "../lib/format";
import { useData } from "../lib/store";
import type { MonitorChange } from "../lib/types";

/* ------------------------------------------------------------
   Day dial — 24 hours as a ring, with the lifecycle jobs on it
   ------------------------------------------------------------ */
function DayDial() {
  const { dayStart: DAY_START, operatingDay: OPERATING_DAY } = useData();
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(t);
  }, []);

  const minutes = (now.getTime() - DAY_START.getTime()) / 60000;
  const angle = (minutes / 1440) * 360 - 90;
  const R = 78;
  const cx = 100;
  const cy = 100;

  const marks = [
    { hour: 0, label: "00:00 init", color: "var(--color-starboard)" },
    { hour: 21, label: "21:00 stage", color: "var(--color-beacon)" },
  ];

  return (
    <div className="relative mx-auto w-[220px]">
      <svg viewBox="0 0 200 200" className="w-full">
        <circle cx={cx} cy={cy} r={R} fill="none" stroke="var(--color-rail)" strokeWidth="1" />
        <circle cx={cx} cy={cy} r={R - 12} fill="none" stroke="var(--color-rail)" strokeWidth="1" strokeDasharray="2 6" />

        {/* hourly monitoring ticks at minute 05 */}
        {Array.from({ length: 24 }, (_, h) => {
          const a = ((h + 5 / 60) / 24) * 360 - 90;
          const rad = (a * Math.PI) / 180;
          const past = h * 60 + 5 <= minutes;
          return (
            <line
              key={h}
              x1={cx + Math.cos(rad) * (R - 7)}
              y1={cy + Math.sin(rad) * (R - 7)}
              x2={cx + Math.cos(rad) * (R + 5)}
              y2={cy + Math.sin(rad) * (R + 5)}
              stroke={past ? "var(--color-signal)" : "var(--color-mist)"}
              strokeWidth={h % 6 === 0 ? 2 : 1}
              opacity={past ? 0.95 : 0.45}
            />
          );
        })}

        {marks.map((m) => {
          const a = ((m.hour / 24) * 360 - 90) * (Math.PI / 180);
          return (
            <circle
              key={m.hour}
              cx={cx + Math.cos(a) * R}
              cy={cy + Math.sin(a) * R}
              r="4.5"
              fill={m.color}
            />
          );
        })}

        {/* elapsed arc */}
        <circle
          cx={cx}
          cy={cy}
          r={R}
          fill="none"
          stroke="var(--color-signal)"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeDasharray={`${(minutes / 1440) * 2 * Math.PI * R} ${2 * Math.PI * R}`}
          transform={`rotate(-90 ${cx} ${cy})`}
          opacity="0.75"
        />

        {/* hand */}
        <line
          x1={cx}
          y1={cy}
          x2={cx + Math.cos((angle * Math.PI) / 180) * (R - 4)}
          y2={cy + Math.sin((angle * Math.PI) / 180) * (R - 4)}
          stroke="var(--color-signal)"
          strokeWidth="1.5"
        />
        <circle cx={cx} cy={cy} r="3" fill="var(--color-signal)" />
      </svg>
      <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
        <span className="label">Operating day</span>
        <span className="mono mt-1 text-[13px] text-[var(--color-chalk)]">
          {OPERATING_DAY}
        </span>
      </div>
    </div>
  );
}

export default function Automation() {
  const { automation: AUTOMATION, operatingDay: OPERATING_DAY, refresh } = useData();
  const [busy, setBusy] = useState(false);
  const [changes, setChanges] = useState<MonitorChange[] | null>(null);

  const trigger = async () => {
    setBusy(true);
    try {
      const res = await runMonitor();
      setChanges(res as MonitorChange[]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-[1560px] space-y-5 pb-10">
      <div className="grid gap-5 xl:grid-cols-[1fr_360px]">
        <Panel className="rise" ticked live>
          <PanelHead
            title="Lifecycle jobs"
            sub={`In-process scheduler · ${AUTOMATION.timezone} · one FastAPI worker, PostgreSQL advisory lock`}
            accent="var(--color-starboard)"
            right={
              <Chip tone={AUTOMATION.running ? "clear" : "blocked"} dot>
                {AUTOMATION.running ? "running" : "stopped"}
              </Chip>
            }
          />
          <ul>
            {AUTOMATION.jobs.map((job, i) => (
              <li
                key={job.name}
                className="rise border-b border-dashed border-[var(--color-rail)] px-6 py-4 last:border-0"
                style={{ animationDelay: `${i * 70}ms` }}
              >
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <Server size={14} className="text-[var(--color-slate-ink)]" />
                    <span className="mono text-[12.5px] text-[var(--color-chalk)]">
                      {job.name}
                    </span>
                    <Chip tone="mute">{job.schedule}</Chip>
                  </div>
                  <StatusChip status={job.status} />
                </div>
                <p className="mt-2 pl-[26px] text-[12px] leading-relaxed text-[var(--color-fog)]">
                  {job.summary}
                </p>
                <div className="mono mt-2 flex flex-wrap gap-x-6 gap-y-1 pl-[26px] text-[10px] text-[var(--color-slate-ink)]">
                  <span>last {job.last_run ? relative(job.last_run) : "—"}</span>
                  <span>next {hhmm(job.next_run)}</span>
                </div>
              </li>
            ))}
          </ul>
        </Panel>

        <div className="space-y-5">
          <Panel className="rise" ticked>
            <PanelHead title="Day dial" sub="Hourly monitoring fires at minute 05" />
            <div className="px-5 py-5">
              <DayDial />
              <div className="mt-4 space-y-2">
                <div className="flex items-center gap-2.5">
                  <span className="h-2 w-2 rounded-full bg-[var(--color-starboard)]" />
                  <span className="text-[11.5px] text-[var(--color-fog)]">
                    00:00 — initialise the operating day
                  </span>
                </div>
                <div className="flex items-center gap-2.5">
                  <span className="h-2 w-2 rounded-full bg-[var(--color-beacon)]" />
                  <span className="text-[11.5px] text-[var(--color-fog)]">
                    21:00 — stage tomorrow's arrivals
                  </span>
                </div>
                <div className="flex items-center gap-2.5">
                  <span className="h-2 w-[2px] bg-[var(--color-signal)]" />
                  <span className="text-[11.5px] text-[var(--color-fog)]">
                    HH:05 — monitor the current day
                  </span>
                </div>
              </div>
            </div>
          </Panel>

          <Panel className="rise" ticked>
            <PanelHead
              title="Concurrency"
              sub="Why two jobs can never overlap"
              accent="var(--color-port)"
            />
            <div className="px-5 py-4">
              <div className="flex items-start gap-3">
                <Lock size={14} className="mt-0.5 shrink-0 text-[var(--color-port)]" />
                <p className="text-[12px] leading-relaxed text-[var(--color-fog)]">
                  Staging, initialisation, hourly monitoring and startup recovery
                  all take the same PostgreSQL advisory lock. A restart mid-day
                  triggers a catch-up rather than waiting for the next midnight
                  boundary.
                </p>
              </div>
            </div>
          </Panel>
        </div>
      </div>

      <Panel className="rise" ticked>
        <PanelHead
          title="Manual monitoring pass"
          sub={`POST /monitor?arrival_date=${OPERATING_DAY}`}
          accent="var(--color-signal)"
          right={
            <Button variant="signal" onClick={trigger} disabled={busy}>
              <span className="inline-flex items-center gap-1.5">
                {busy ? (
                  <RefreshCw size={10} className="animate-spin" />
                ) : (
                  <Play size={10} />
                )}
                {busy ? "running" : "run monitor"}
              </span>
            </Button>
          }
        />
        <div className="px-6 py-5">
          {!changes && (
            <p className="text-[12px] leading-relaxed text-[var(--color-fog)]">
              Runs one monitoring cycle against the arrival feed: records new
              vessels, detects ETA revisions and hands each change to the
              rescheduling agent. The returned change list is printed below.
            </p>
          )}
          {changes && changes.length === 0 && (
            <p className="mono text-[12px] text-[var(--color-starboard)]">
              [] — no changes since the last update.
            </p>
          )}
          {changes && changes.length > 0 && (
            <ol className="space-y-2">
              {changes.map((c, i) => (
                <li
                  key={`${c.imo_number}-${i}`}
                  className="rise flex items-center justify-between gap-4 rounded-[3px] border border-[var(--color-rail)] bg-[color-mix(in_srgb,var(--color-abyss)_55%,transparent)] px-4 py-3"
                  style={{ animationDelay: `${i * 90}ms` }}
                >
                  <div>
                    <Chip tone="agent">{c.event.replace(/_/g, " ")}</Chip>
                    <span className="mono ml-3 text-[12px] text-[var(--color-chalk)]">
                      {c.vessel_name}
                    </span>
                  </div>
                  <span className="mono text-[11px] text-[var(--color-fog)]">
                    {c.previous_eta ? `${hhmm(c.previous_eta)} → ` : ""}
                    {hhmm(c.new_eta ?? c.eta)}
                  </span>
                </li>
              ))}
            </ol>
          )}

          <div className="mt-6 grid gap-x-10 md:grid-cols-2">
            <KeyVal k="Timezone" v={AUTOMATION.timezone} />
            <KeyVal k="Workers" v="1 (in-process scheduler)" />
            <KeyVal k="Feed" v="OCEANS-X arrivals" />
            <KeyVal
              k="Last hourly pass"
              v={stamp(AUTOMATION.jobs[2].last_run)}
            />
          </div>
        </div>
      </Panel>
    </div>
  );
}
