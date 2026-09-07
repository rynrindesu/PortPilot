import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { BerthTimeline } from "../components/BerthTimeline";
import { Metric, Panel, PanelHead, StatusChip } from "../components/ui";
import { hhmm, minutesBetween } from "../lib/format";
import { useData } from "../lib/store";
import type { ResourceType, VesselState } from "../lib/types";

const RESOURCES: { key: ResourceType; label: string; blurb: string }[] = [
  { key: "berth", label: "Berths", blurb: "Alongside windows, 15-minute turnaround buffer" },
  { key: "pilot", label: "Pilots", blurb: "Boarding-to-arrival windows" },
  { key: "tug", label: "Tugs", blurb: "Assist windows from first line" },
];

export default function Berths() {
  const { vessels: VESSELS, pools: POOL } = useData();
  const [resource, setResource] = useState<ResourceType>("berth");
  const [focus, setFocus] = useState<VesselState | null>(null);

  const active = useMemo(
    () => VESSELS.filter((v) => v.status === "active"),
    [VESSELS],
  );

  const summary = useMemo(() => {
    const allocs = active
      .map((v) => v.allocations[resource])
      .filter(Boolean) as NonNullable<VesselState["allocations"][ResourceType]>[];
    const used = new Set(allocs.map((a) => a.resource_id)).size;
    const totalMinutes = allocs.reduce(
      (sum, a) => sum + minutesBetween(a.start_time, a.end_time),
      0,
    );
    return {
      used,
      pool: POOL[resource].length,
      bookings: allocs.length,
      utilisation: Math.round((totalMinutes / (POOL[resource].length * 24 * 60)) * 100),
      unconfirmed: allocs.filter((a) => a.status !== "confirmed").length,
      meanHours: (totalMinutes / Math.max(1, allocs.length) / 60).toFixed(1),
    };
  }, [active, resource, POOL]);

  return (
    <div className="mx-auto max-w-[1560px] space-y-5 pb-10">
      <Panel className="rise" ticked>
        <div className="grid grid-cols-2 gap-px bg-[var(--color-rail)] md:grid-cols-3 xl:grid-cols-5">
          <div className="bg-[var(--color-hull)]">
            <Metric
              label="Pool in use"
              value={summary.used}
              unit={`/ ${summary.pool}`}
              hint={`${RESOURCES.find((r) => r.key === resource)?.label.toLowerCase()} with at least one booking`}
            />
          </div>
          <div className="bg-[var(--color-hull)]">
            <Metric label="Bookings" value={summary.bookings} hint="on the operating day" />
          </div>
          <div className="bg-[var(--color-hull)]">
            <Metric
              label="Utilisation"
              value={summary.utilisation}
              unit="%"
              hint="occupied minutes across the pool"
              tone="agent"
            />
          </div>
          <div className="bg-[var(--color-hull)]">
            <Metric
              label="Mean window"
              value={summary.meanHours}
              unit="h"
              hint="per allocation"
            />
          </div>
          <div className="bg-[var(--color-hull)]">
            <Metric
              label="Not confirmed"
              value={summary.unconfirmed}
              hint="unconfirmed or pending review"
              tone={summary.unconfirmed ? "blocked" : "clear"}
            />
          </div>
        </div>
      </Panel>

      <Panel className="rise" ticked>
        <PanelHead
          title="Resource plan · 24 h"
          sub={RESOURCES.find((r) => r.key === resource)?.blurb}
          accent="var(--color-beacon)"
          right={
            <div className="flex gap-1.5">
              {RESOURCES.map((r) => (
                <button
                  key={r.key}
                  onClick={() => setResource(r.key)}
                  className={`mono cursor-pointer rounded-[3px] border px-3 py-[6px] text-[10px] tracking-[0.12em] uppercase transition-colors ${
                    resource === r.key
                      ? "border-[color-mix(in_srgb,var(--color-beacon)_55%,transparent)] bg-[color-mix(in_srgb,var(--color-beacon)_12%,transparent)] text-[var(--color-beacon)]"
                      : "border-[var(--color-rail)] text-[var(--color-slate-ink)] hover:text-[var(--color-fog)]"
                  }`}
                >
                  {r.label}
                </button>
              ))}
            </div>
          }
        />
        <div className="px-6 py-5">
          <BerthTimeline
            vessels={active}
            resource={resource}
            onSelect={(v) => setFocus(v)}
          />
        </div>
      </Panel>

      <div className="grid gap-5 lg:grid-cols-[1fr_1fr]">
        <Panel className="rise" ticked>
          <PanelHead
            title="Selected movement"
            sub={focus ? focus.vessel_name : "Click a bar on the plan to inspect it"}
          />
          {focus ? (
            <div className="px-5 py-4">
              <div className="grid grid-cols-3 gap-px bg-[var(--color-rail)]">
                {(["berth", "pilot", "tug"] as ResourceType[]).map((t) => {
                  const a = focus.allocations[t];
                  return (
                    <div key={t} className="bg-[var(--color-hull)] px-4 py-3.5">
                      <div className="label">{t}</div>
                      <div className="mono mt-2 text-[14px] text-[var(--color-chalk)]">
                        {a?.resource_id}
                      </div>
                      <div className="mono mt-1 text-[11px] text-[var(--color-fog)]">
                        {hhmm(a?.start_time)} – {hhmm(a?.end_time)}
                      </div>
                      <div className="mt-2">
                        <StatusChip status={a?.status ?? "—"} />
                      </div>
                    </div>
                  );
                })}
              </div>
              <p className="mt-4 text-[12px] leading-relaxed text-[var(--color-fog)]">
                {focus.vessel_name} ({focus.imo_number}) inbound from{" "}
                {focus.location_from}, {focus.loa_m} m LOA. The pilot boards{" "}
                {Math.round(
                  minutesBetween(
                    focus.allocations.pilot!.start_time,
                    focus.current_eta,
                  ),
                )}{" "}
                minutes before ETA; tugs release{" "}
                {Math.round(
                  minutesBetween(
                    focus.current_eta,
                    focus.allocations.tug!.end_time,
                  ),
                )}{" "}
                minutes after first line.
              </p>
              <Link
                to="/arrivals"
                className="mono mt-4 inline-block text-[10px] tracking-[0.12em] text-[var(--color-signal)] uppercase hover:underline"
              >
                Open on the arrival board →
              </Link>
            </div>
          ) : (
            <div className="px-5 py-10 text-center text-[12px] text-[var(--color-slate-ink)]">
              Nothing selected.
            </div>
          )}
        </Panel>

        <Panel className="rise" ticked>
          <PanelHead
            title="Allocation exceptions"
            sub="Everything the deterministic pipeline could not confirm"
            accent="var(--color-port)"
          />
          <ul>
            {active
              .flatMap((v) =>
                Object.values(v.allocations)
                  .filter((a) => a && a.status !== "confirmed")
                  .map((a) => ({ v, a: a! })),
              )
              .map(({ v, a }, i) => (
                <li
                  key={`${v.vessel_name}-${v.imo_number}-${a.resource_type}`}
                  className="rise flex items-center justify-between gap-4 border-b border-dashed border-[var(--color-rail)] px-5 py-3 last:border-0"
                  style={{ animationDelay: `${i * 45}ms` }}
                >
                  <div>
                    <div className="mono text-[10.5px] tracking-[0.08em] text-[var(--color-chalk)] uppercase">
                      {v.vessel_name}
                    </div>
                    <div className="mt-1 text-[11.5px] text-[var(--color-slate-ink)]">
                      {a.resource_type} {a.resource_id} · {hhmm(a.start_time)}–
                      {hhmm(a.end_time)}
                    </div>
                  </div>
                  <StatusChip status={a.status} />
                </li>
              ))}
          </ul>
        </Panel>
      </div>
    </div>
  );
}
