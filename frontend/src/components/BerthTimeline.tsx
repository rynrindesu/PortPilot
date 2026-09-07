import { useEffect, useMemo, useRef, useState } from "react";

import { useData } from "../lib/store";
import { hhmm, minutesBetween } from "../lib/format";
import type { ResourceType, VesselState } from "../lib/types";
import { Chip } from "./ui";

const DAY_MINUTES = 24 * 60;

/** Width of the resource-name gutter, in px. Must match the class below. */
const GUTTER = 92;

/** IBM Plex Mono at 9px advances ~5.4px per character. */
const CHAR_PX = 5.4;
const LABEL_PAD_PX = 12;

const STATUS_FILL: Record<string, string> = {
  confirmed:
    "linear-gradient(180deg, color-mix(in srgb, var(--color-starboard) 34%, transparent), color-mix(in srgb, var(--color-starboard) 16%, transparent))",
  unconfirmed:
    "repeating-linear-gradient(135deg, color-mix(in srgb, var(--color-signal) 30%, transparent) 0 5px, transparent 5px 10px)",
  pending_review:
    "linear-gradient(180deg, color-mix(in srgb, var(--color-port) 38%, transparent), color-mix(in srgb, var(--color-port) 18%, transparent))",
};

const STATUS_EDGE: Record<string, string> = {
  confirmed: "var(--color-starboard)",
  unconfirmed: "var(--color-signal)",
  pending_review: "var(--color-port)",
};

type Allocation = NonNullable<VesselState["allocations"][ResourceType]>;
type LabelSide = "inside" | "left" | "right" | "none";

interface Item {
  v: VesselState;
  a: Allocation;
  lane: number;
  left: number;
  width: number;
  labelSide: LabelSide;
}

interface Props {
  vessels: VesselState[];
  resource: ResourceType;
  /** Restrict the rendered rows — used by the compact overview strip. */
  maxRows?: number;
  compact?: boolean;
  onSelect?: (v: VesselState) => void;
}

export function BerthTimeline({
  vessels,
  resource,
  maxRows,
  compact = false,
  onSelect,
}: Props) {
  const [hover, setHover] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const { pools: POOL, dayStart: DAY_START } = useData();

  // Label fitting is a pixel question, so measure the track rather than
  // assuming a viewport. Without this, labels that fit at 1700px overlap at
  // 1280px, where the same percentage buys far fewer pixels.
  const [trackPx, setTrackPx] = useState(1200);
  useEffect(() => {
    const el = rootRef.current;
    if (!el) return;
    const measure = () => setTrackPx(Math.max(240, el.clientWidth - GUTTER));
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const nowPct = useMemo(() => {
    const mins = minutesBetween(DAY_START.toISOString(), new Date().toISOString());
    return Math.min(100, Math.max(0, (mins / DAY_MINUTES) * 100));
  }, [DAY_START]);

  const rows = useMemo(() => {
    const dayStart = DAY_START.toISOString();
    const pctOf = (iso: string) =>
      Math.min(100, Math.max(0, (minutesBetween(dayStart, iso) / DAY_MINUTES) * 100));

    const ids = POOL[resource];
    const byResource = new Map<string, Item[]>();
    ids.forEach((id) => byResource.set(id, []));

    vessels.forEach((v) => {
      const a = v.allocations[resource];
      if (!a) return;
      const left = pctOf(a.start_time);
      const width = Math.max(0.7, pctOf(a.end_time) - left);
      byResource
        .get(a.resource_id)
        ?.push({ v, a, lane: 0, left, width, labelSide: "none" });
    });

    const all = ids.map((id) => {
      const items = (byResource.get(id) ?? []).sort((x, y) => x.left - y.left);

      // Two bookings on one resource must never sit on top of each other:
      // pack overlapping windows into stacked lanes.
      const laneEnds: number[] = [];
      items.forEach((item) => {
        let lane = laneEnds.findIndex((e) => e <= item.left);
        if (lane === -1) lane = laneEnds.length;
        laneEnds[lane] = item.left + item.width;
        item.lane = lane;
      });

      // Decide where each name goes. Pilot and tug windows are 30-110 minutes
      // — a few percent of the day — so their names cannot sit inside the bar
      // and have to spill into the empty track beside it. The gap between two
      // bars is a single resource: one label may claim it, never two, or the
      // names overprint each other.
      const byLane = new Map<number, Item[]>();
      items.forEach((it) => {
        const list = byLane.get(it.lane) ?? [];
        list.push(it);
        byLane.set(it.lane, list);
      });

      byLane.forEach((list) => {
        const claimed = new Set<number>();
        list.forEach((it, k) => {
          if (it.width > 7) {
            it.labelSide = "inside";
            return;
          }
          const needPct =
            ((it.v.vessel_name.length * CHAR_PX + LABEL_PAD_PX) / trackPx) * 100;

          const end = it.left + it.width;
          const gapRight = (k + 1 < list.length ? list[k + 1].left : 100) - end;
          const gapLeft = it.left - (k > 0 ? list[k - 1].left + list[k - 1].width : 0);

          // Gap slot k sits before item k; slot k+1 sits after it.
          if (!claimed.has(k + 1) && gapRight >= needPct && end + needPct <= 100) {
            it.labelSide = "right";
            claimed.add(k + 1);
          } else if (!claimed.has(k) && gapLeft >= needPct) {
            it.labelSide = "left";
            claimed.add(k);
          } else {
            it.labelSide = "none";
          }
        });
      });

      return { id, items, lanes: Math.max(1, laneEnds.length) };
    });

    const used = all.filter((r) => r.items.length > 0);
    const list = used.length ? used : all;
    return maxRows ? list.slice(0, maxRows) : list;
  }, [vessels, resource, maxRows, trackPx, POOL, DAY_START]);

  const rowH = compact ? 20 : 26;

  return (
    <div className="relative" ref={rootRef}>
      {/* hour ruler */}
      <div className="relative ml-[92px] h-5 border-b border-[var(--color-rail)]">
        {Array.from({ length: 13 }, (_, i) => i * 2).map((h) => (
          <div
            key={h}
            className="absolute top-0 bottom-0"
            style={{ left: `${(h / 24) * 100}%` }}
          >
            <div className="h-full w-px bg-[var(--color-rail)]" />
            {h < 24 && (
              <span className="mono absolute top-0 left-1 text-[9px] text-[var(--color-slate-ink)]">
                {String(h).padStart(2, "0")}
              </span>
            )}
          </div>
        ))}
      </div>

      <div className="relative">
        {/* vertical hour grid behind the bars */}
        <div className="pointer-events-none absolute inset-0 left-[92px]">
          {Array.from({ length: 12 }, (_, i) => (i + 1) * 2).map((h) => (
            <div
              key={h}
              className="absolute top-0 bottom-0 w-px bg-[color-mix(in_srgb,var(--color-rail)_60%,transparent)]"
              style={{ left: `${(h / 24) * 100}%` }}
            />
          ))}
          {/* now line */}
          <div
            className="absolute top-0 bottom-0 z-20 w-px bg-[var(--color-signal)]"
            style={{ left: `${nowPct}%` }}
          >
            <div className="absolute -top-[3px] -left-[3px] h-[7px] w-[7px] rotate-45 bg-[var(--color-signal)]" />
          </div>
        </div>

        {rows.map(({ id, items, lanes }) => (
          <div
            key={id}
            className="relative flex items-stretch border-b border-dashed border-[color-mix(in_srgb,var(--color-rail)_70%,transparent)] last:border-0"
            style={{ height: rowH * lanes + 6 }}
          >
            <div className="mono w-[92px] shrink-0 pt-[7px] pr-3 text-right text-[10px] tracking-[0.06em] text-[var(--color-fog)]">
              {id}
            </div>
            <div className="relative h-full flex-1">
              {items.map(({ v, a, lane, left, width, labelSide }) => {
                const key = `${v.vessel_name}-${v.imo_number}-${a.resource_id}`;
                const active = hover === key;
                const spill = !compact && (labelSide === "left" || labelSide === "right");

                return (
                  <div key={key} className="contents">
                    <button
                      type="button"
                      onMouseEnter={() => setHover(key)}
                      onMouseLeave={() => setHover(null)}
                      onClick={() => onSelect?.(v)}
                      className="absolute cursor-pointer overflow-hidden rounded-[2px] border text-left transition-[box-shadow,filter] duration-150"
                      style={{
                        left: `${left}%`,
                        width: `${width}%`,
                        top: lane * rowH + 4,
                        height: rowH - 8,
                        background: STATUS_FILL[a.status],
                        borderColor: STATUS_EDGE[a.status],
                        filter: active ? "brightness(1.35)" : "none",
                        boxShadow: active
                          ? `0 0 0 1px ${STATUS_EDGE[a.status]}, 0 6px 20px -6px ${STATUS_EDGE[a.status]}`
                          : "none",
                        zIndex: active ? 30 : 10,
                      }}
                      title={`${v.vessel_name} · ${hhmm(a.start_time)}–${hhmm(a.end_time)} · ${a.status}`}
                    >
                      {!compact && labelSide === "inside" && (
                        <span
                          className="mono block truncate px-1.5 text-[9px] text-[var(--color-chalk)]"
                          style={{ lineHeight: `${rowH - 10}px` }}
                        >
                          {v.vessel_name}
                        </span>
                      )}
                    </button>

                    {spill && (
                      <span
                        className="mono pointer-events-none absolute whitespace-nowrap text-[9px]"
                        style={{
                          ...(labelSide === "left"
                            ? { right: `${100 - left}%`, marginRight: 5 }
                            : { left: `${left + width}%`, marginLeft: 5 }),
                          top: lane * rowH + 4,
                          height: rowH - 8,
                          lineHeight: `${rowH - 8}px`,
                          color: active
                            ? "var(--color-chalk)"
                            : "var(--color-fog)",
                          zIndex: active ? 31 : 11,
                        }}
                      >
                        {v.vessel_name}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {!compact && (
        <div className="mt-3 flex flex-wrap items-center gap-2 pl-[92px]">
          <Chip tone="clear">confirmed</Chip>
          <Chip tone="hold">unconfirmed</Chip>
          <Chip tone="blocked">pending review</Chip>
          <span className="mono ml-2 flex items-center gap-1.5 text-[10px] text-[var(--color-slate-ink)]">
            <span className="inline-block h-3 w-px bg-[var(--color-signal)]" /> now
          </span>
        </div>
      )}
    </div>
  );
}
