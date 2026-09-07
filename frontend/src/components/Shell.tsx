import { useEffect, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import {
  Activity,
  Anchor,
  ChartGantt,
  ClipboardCheck,
  Clock,
  Cpu,
  FileScan,
  Radar,
  Ship,
} from "lucide-react";

import { clock, longDate } from "../lib/format";
import { useData } from "../lib/store";
import { Chip } from "./ui";

const NAV = [
  { to: "/", label: "Harbour Watch", icon: Radar, hint: "Live operating picture", end: true },
  { to: "/arrivals", label: "Arrivals", icon: Ship, hint: "Vessel & ETA board" },
  { to: "/berths", label: "Berth Plan", icon: ChartGantt, hint: "24 h resource timeline" },
  { to: "/agent", label: "Reschedule Agent", icon: Cpu, hint: "Decision trace" },
  { to: "/port-calls", label: "Port Calls", icon: ClipboardCheck, hint: "Compliance workflow" },
  { to: "/documents", label: "Documents", icon: FileScan, hint: "Extraction & OCR" },
  { to: "/automation", label: "Automation", icon: Clock, hint: "Lifecycle jobs" },
];

/* ------------------------------------------------------------
   Mark — a radar dish sweeping over the harbour
   ------------------------------------------------------------ */
function Mark() {
  return (
    <div className="relative h-9 w-9 shrink-0">
      <div className="absolute inset-0 overflow-hidden rounded-full border border-[color-mix(in_srgb,var(--color-starboard)_30%,transparent)] bg-[var(--color-abyss)]">
        <div className="sweep" />
        <div className="absolute inset-[30%] rounded-full border border-[color-mix(in_srgb,var(--color-starboard)_22%,transparent)]" />
      </div>
      <Anchor
        size={13}
        strokeWidth={2.2}
        className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-[var(--color-signal)]"
      />
    </div>
  );
}

/* ------------------------------------------------------------
   Left rail
   ------------------------------------------------------------ */
function Rail() {
  const { source, vessels } = useData();

  return (
    <nav className="relative z-10 flex h-full w-[236px] shrink-0 flex-col border-r border-[var(--color-rail)] bg-[color-mix(in_srgb,var(--color-deep)_82%,transparent)] backdrop-blur-xl">
      <div className="flex items-center gap-3 border-b border-[var(--color-rail)] px-5 py-5">
        <Mark />
        <div className="min-w-0">
          <div className="display text-[15px] leading-none tracking-[0.02em] text-[var(--color-chalk)]">
            PortPilot
          </div>
          <div className="label mt-1.5">Harbour Control</div>
        </div>
      </div>

      <div className="scroll-thin flex-1 overflow-y-auto py-3">
        <div className="label px-5 pb-2">Operations</div>
        {NAV.map(({ to, label, icon: Icon, hint, end }, i) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `group relative flex items-center gap-3 px-5 py-2.5 transition-colors duration-150 ${
                isActive
                  ? "bg-[color-mix(in_srgb,var(--color-signal)_9%,transparent)] text-[var(--color-chalk)]"
                  : "text-[var(--color-fog)] hover:bg-[var(--color-hull)] hover:text-[var(--color-chalk)]"
              }`
            }
          >
            {({ isActive }) => (
              <>
                <span
                  className={`absolute inset-y-0 left-0 w-[2px] transition-all duration-200 ${
                    isActive
                      ? "bg-[var(--color-signal)]"
                      : "bg-transparent group-hover:bg-[var(--color-mist)]"
                  }`}
                />
                <Icon
                  size={15}
                  strokeWidth={1.75}
                  className={
                    isActive ? "text-[var(--color-signal)]" : "text-current"
                  }
                />
                <span className="min-w-0 flex-1">
                  <span className="block text-[12.5px] leading-tight font-medium">
                    {label}
                  </span>
                  <span className="mono block text-[9.5px] leading-tight tracking-[0.06em] text-[var(--color-slate-ink)] uppercase">
                    {hint}
                  </span>
                </span>
                <span
                  className="mono text-[9px] text-[var(--color-slate-ink)] opacity-0 transition-opacity group-hover:opacity-100"
                  aria-hidden
                >
                  {String(i + 1).padStart(2, "0")}
                </span>
              </>
            )}
          </NavLink>
        ))}
      </div>

      <div className="border-t border-[var(--color-rail)] px-5 py-4">
        <div className="flex items-center justify-between">
          <span className="label">Source</span>
          <Chip tone={source === "live" ? "clear" : "agent"} dot>
            {source === "live" ? "live api" : "demo set"}
          </Chip>
        </div>
        <p className="mt-2.5 text-[10.5px] leading-relaxed text-[var(--color-slate-ink)]">
          {source === "live"
            ? `Live from the rescheduling and port-ops services · ${vessels.length} vessels on the operating day.`
            : "Bundled operating-day snapshot. Set VITE_RESCHEDULING_API and VITE_PORT_OPS_API to read the live services."}
        </p>
      </div>
    </nav>
  );
}

/* ------------------------------------------------------------
   Command bar
   ------------------------------------------------------------ */
function CommandBar() {
  const { operatingDay } = useData();
  const [now, setNow] = useState(new Date());
  const { pathname } = useLocation();
  const current = NAV.find((n) =>
    n.end ? pathname === n.to : pathname.startsWith(n.to),
  );

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  return (
    <header className="relative z-10 flex h-[62px] shrink-0 items-center justify-between gap-6 border-b border-[var(--color-rail)] bg-[color-mix(in_srgb,var(--color-deep)_70%,transparent)] px-7 backdrop-blur-xl">
      <div className="flex min-w-0 items-baseline gap-3">
        <h1 className="display-tight text-[20px] text-[var(--color-chalk)]">
          {current?.label ?? "Harbour Watch"}
        </h1>
        <span className="mono truncate text-[11px] text-[var(--color-slate-ink)]">
          / {current?.hint ?? ""}
        </span>
      </div>

      <div className="flex items-center gap-5">
        <div className="hidden items-center gap-2 lg:flex">
          <Activity size={13} className="text-[var(--color-starboard)]" />
          <span className="mono text-[10.5px] tracking-[0.1em] text-[var(--color-fog)] uppercase">
            Automation running
          </span>
        </div>

        <div className="h-6 w-px bg-[var(--color-rail)]" />

        <div className="text-right">
          <div className="mono text-[10px] tracking-[0.14em] text-[var(--color-slate-ink)] uppercase">
            {longDate(now)} · SGT
          </div>
          <div className="mono text-[15px] leading-tight font-medium text-[var(--color-chalk)] tabular-nums">
            {clock(now)}
          </div>
        </div>

        <div className="hidden text-right xl:block">
          <div className="label">Operating day</div>
          <div className="mono text-[12px] text-[var(--color-signal)]">
            {operatingDay}
          </div>
        </div>
      </div>
    </header>
  );
}

/* ------------------------------------------------------------
   Layout
   ------------------------------------------------------------ */
export function Shell({ children }: { children: React.ReactNode }) {
  const { pathname } = useLocation();

  return (
    <>
      <div className="chart-ground" />
      <div className="chart-grid" />
      <div className="grain" />

      <div className="relative z-10 flex h-full">
        <Rail />
        <div className="flex min-w-0 flex-1 flex-col">
          <CommandBar />
          <main
            key={pathname}
            className="scroll-thin flex-1 overflow-y-auto overflow-x-hidden px-7 py-6"
          >
            {children}
          </main>
        </div>
      </div>
    </>
  );
}
