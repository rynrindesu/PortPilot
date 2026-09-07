import { useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Search, X } from "lucide-react";

import { Chip, KeyVal, Panel, PanelHead, StatusChip, Rule } from "../components/ui";
import { deltaMinutes, hhmm, humanDelta, stamp } from "../lib/format";
import { useData } from "../lib/store";
import type { ResourceType, VesselState } from "../lib/types";

type Filter = "all" | "changed" | "attention" | "staged";

const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "changed", label: "ETA changed" },
  { key: "attention", label: "Needs attention" },
  { key: "staged", label: "Staged" },
];

function Drawer({
  vessel,
  onClose,
}: {
  vessel: VesselState;
  onClose: () => void;
}) {
  const { etaHistory } = useData();
  const history = etaHistory
    .filter(
      (e) =>
        e.imo_number === vessel.imo_number &&
        e.vessel_name === vessel.vessel_name,
    )
    .sort(
    (a, b) => new Date(a.received_at).getTime() - new Date(b.received_at).getTime(),
  );

  return (
    <motion.aside
      initial={{ x: 40, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: 40, opacity: 0 }}
      transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
      className="panel ticked sticky top-0 self-start"
    >
      <header className="flex items-start justify-between gap-3 border-b border-[var(--color-rail)] px-5 py-4">
        <div>
          <div className="label">
            {[vessel.vessel_type, vessel.flag].filter(Boolean).join(" · ")}
          </div>
          <h3 className="display mt-1.5 text-[16px] text-[var(--color-chalk)]">
            {vessel.vessel_name}
          </h3>
        </div>
        <button
          onClick={onClose}
          className="cursor-pointer rounded-[3px] border border-[var(--color-rail)] p-1.5 text-[var(--color-slate-ink)] transition-colors hover:border-[var(--color-mist)] hover:text-[var(--color-chalk)]"
          aria-label="Close"
        >
          <X size={13} />
        </button>
      </header>

      <div className="px-5 py-3">
        <KeyVal k="IMO" v={vessel.imo_number} />
        <KeyVal k="Call sign" v={vessel.call_sign} />
        {vessel.loa_m !== null && <KeyVal k="LOA" v={`${vessel.loa_m} m`} />}
        <KeyVal k="From" v={vessel.location_from} mono={false} />
        <KeyVal k="Current ETA" v={stamp(vessel.current_eta)} />
        <KeyVal
          k="Feed confidence"
          v={`${(vessel.eta_confidence * 100).toFixed(0)}%`}
        />
      </div>

      <Rule label="ETA history" />

      <ol className="relative px-5 py-3">
        <div className="absolute top-6 bottom-6 left-[26px] w-px bg-[var(--color-rail)]" />
        {history.map((e, i) => {
          const d = e.previous_eta
            ? deltaMinutes(e.previous_eta, e.reported_eta)
            : 0;
          return (
            <li key={e.eta_event_id} className="relative flex gap-3 pb-4 last:pb-0">
              <span
                className={`relative z-10 mt-1 h-2 w-2 shrink-0 rounded-full ${
                  i === history.length - 1
                    ? "bg-[var(--color-signal)]"
                    : "bg-[var(--color-mist)]"
                }`}
              />
              <div className="min-w-0">
                <div className="mono text-[12px] text-[var(--color-chalk)]">
                  {stamp(e.reported_eta)}
                </div>
                <div className="mono mt-0.5 text-[10px] text-[var(--color-slate-ink)]">
                  reported {stamp(e.received_at)} · {e.source}
                </div>
                {d !== 0 && (
                  <span
                    className={`mono mt-1 inline-block text-[10.5px] ${
                      d > 0
                        ? "text-[var(--color-port)]"
                        : "text-[var(--color-starboard)]"
                    }`}
                  >
                    {humanDelta(d)} against previous
                  </span>
                )}
              </div>
            </li>
          );
        })}
      </ol>

      <Rule label="Allocations" />

      <div className="space-y-2 px-5 py-4">
        {(["berth", "pilot", "tug"] as ResourceType[]).map((t) => {
          const a = vessel.allocations[t];
          if (!a) return null;
          return (
            <div
              key={t}
              className="flex items-center justify-between gap-3 rounded-[3px] border border-[var(--color-rail)] bg-[color-mix(in_srgb,var(--color-plate)_55%,transparent)] px-3 py-2.5"
            >
              <div>
                <div className="label">{t}</div>
                <div className="mono mt-1 text-[12px] text-[var(--color-chalk)]">
                  {a.resource_id}
                </div>
              </div>
              <div className="text-right">
                <div className="mono text-[11px] text-[var(--color-fog)]">
                  {hhmm(a.start_time)} – {hhmm(a.end_time)}
                </div>
                <div className="mt-1.5">
                  <StatusChip status={a.status} />
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </motion.aside>
  );
}

export default function Arrivals() {
  const { vessels: VESSELS } = useData();
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [selected, setSelected] = useState<VesselState | null>(null);

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return VESSELS.filter((v) => {
      if (filter === "changed" && !v.previous_eta) return false;
      if (filter === "staged" && v.status !== "staged") return false;
      if (
        filter === "attention" &&
        !Object.values(v.allocations).some((a) => a && a.status !== "confirmed")
      )
        return false;
      if (!q) return true;
      return (
        v.vessel_name.toLowerCase().includes(q) ||
        v.imo_number.includes(q) ||
        v.call_sign.toLowerCase().includes(q) ||
        v.location_from.toLowerCase().includes(q)
      );
    });
  }, [query, filter, VESSELS]);

  return (
    <div
      className={`mx-auto grid max-w-[1560px] gap-5 pb-10 ${
        selected ? "xl:grid-cols-[1fr_360px]" : ""
      }`}
    >
      <Panel className="rise h-fit" ticked>
        <PanelHead
          title="Arrival board"
          sub={`${rows.length} of ${VESSELS.length} vessels on the operating-day feed`}
          right={
            <div className="flex items-center gap-2">
              <div className="relative">
                <Search
                  size={12}
                  className="absolute top-1/2 left-2.5 -translate-y-1/2 text-[var(--color-slate-ink)]"
                />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="vessel · imo · port"
                  className="mono w-[190px] rounded-[3px] border border-[var(--color-rail)] bg-[var(--color-abyss)] py-[6px] pr-2 pl-7 text-[11px] text-[var(--color-chalk)] placeholder:text-[var(--color-slate-ink)] focus:border-[var(--color-signal)] focus:outline-none"
                />
              </div>
              {FILTERS.map((f) => (
                <button
                  key={f.key}
                  onClick={() => setFilter(f.key)}
                  className={`mono cursor-pointer rounded-[3px] border px-2.5 py-[6px] text-[10px] tracking-[0.1em] uppercase transition-colors ${
                    filter === f.key
                      ? "border-[color-mix(in_srgb,var(--color-signal)_55%,transparent)] bg-[color-mix(in_srgb,var(--color-signal)_12%,transparent)] text-[var(--color-signal)]"
                      : "border-[var(--color-rail)] text-[var(--color-slate-ink)] hover:text-[var(--color-fog)]"
                  }`}
                >
                  {f.label}
                </button>
              ))}
            </div>
          }
        />

        <div className="scroll-thin overflow-x-auto">
          <table className="w-full min-w-[980px]">
            <thead>
              <tr className="border-b border-[var(--color-rail)]">
                {[
                  "Vessel",
                  "IMO / call sign",
                  "Origin",
                  "Original ETA",
                  "Current ETA",
                  "Δ",
                  "Berth",
                  "Pilot",
                  "Tug",
                  "Conf.",
                ].map((h) => (
                  <th key={h} className="label px-4 py-2.5 text-left">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((v, i) => {
                const d = v.previous_eta
                  ? deltaMinutes(v.previous_eta, v.current_eta)
                  : 0;
                const isSel = selected?.imo_number === v.imo_number;
                return (
                  <tr
                    key={`${v.vessel_name}-${v.imo_number}`}
                    onClick={() => setSelected(isSel ? null : v)}
                    className={`rise cursor-pointer border-b border-dashed border-[var(--color-rail)] transition-colors last:border-0 ${
                      isSel
                        ? "bg-[color-mix(in_srgb,var(--color-signal)_8%,transparent)]"
                        : "hover:bg-[color-mix(in_srgb,var(--color-plate)_70%,transparent)]"
                    }`}
                    style={{ animationDelay: `${Math.min(i, 16) * 28}ms` }}
                  >
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-2">
                        <span className="text-[12.5px] font-medium text-[var(--color-chalk)]">
                          {v.vessel_name}
                        </span>
                        {v.status === "staged" && <Chip tone="hold">staged</Chip>}
                      </div>
                      <div className="mono text-[9.5px] tracking-[0.06em] text-[var(--color-slate-ink)] uppercase">
                        {[v.vessel_type, v.loa_m ? `${v.loa_m} m` : null, v.flag]
                        .filter(Boolean)
                        .join(" · ")}
                      </div>
                    </td>
                    <td className="mono px-4 py-2.5 text-[11px] text-[var(--color-fog)]">
                      {v.imo_number}
                      <span className="block text-[10px] text-[var(--color-slate-ink)]">
                        {v.call_sign}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-[11.5px] text-[var(--color-fog)]">
                      {v.location_from}
                    </td>
                    <td className="mono px-4 py-2.5 text-[11.5px] text-[var(--color-slate-ink)]">
                      {hhmm(v.original_eta)}
                    </td>
                    <td className="mono px-4 py-2.5 text-[13px] font-medium text-[var(--color-chalk)]">
                      {hhmm(v.current_eta)}
                    </td>
                    <td className="px-4 py-2.5">
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
                    {(["berth", "pilot", "tug"] as ResourceType[]).map((t) => (
                      <td key={t} className="px-4 py-2.5">
                        <div className="mono text-[11px] text-[var(--color-fog)]">
                          {v.allocations[t]?.resource_id}
                        </div>
                        <div className="mt-1">
                          <StatusChip status={v.allocations[t]?.status ?? "—"} />
                        </div>
                      </td>
                    ))}
                    <td className="mono px-4 py-2.5 text-[11px] text-[var(--color-fog)]">
                      {(v.eta_confidence * 100).toFixed(0)}%
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Panel>

      <AnimatePresence>
        {selected && (
          <Drawer
            key={`${selected.vessel_name}-${selected.imo_number}`}
            vessel={selected}
            onClose={() => setSelected(null)}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
