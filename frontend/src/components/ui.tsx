import type { ReactNode } from "react";

/* ============================================================
   Tone — every colour in the console is a navigation light.
   green = clear, red = blocked, amber = needs a human,
   cyan = the agent did it autonomously.
   ============================================================ */

export type Tone = "clear" | "blocked" | "hold" | "agent" | "mute";

export const TONE: Record<Tone, { fg: string; bg: string; bd: string }> = {
  clear: {
    fg: "text-[var(--color-starboard)]",
    bg: "bg-[color-mix(in_srgb,var(--color-starboard)_13%,transparent)]",
    bd: "border-[color-mix(in_srgb,var(--color-starboard)_38%,transparent)]",
  },
  blocked: {
    fg: "text-[var(--color-port)]",
    bg: "bg-[color-mix(in_srgb,var(--color-port)_13%,transparent)]",
    bd: "border-[color-mix(in_srgb,var(--color-port)_38%,transparent)]",
  },
  hold: {
    fg: "text-[var(--color-signal)]",
    bg: "bg-[color-mix(in_srgb,var(--color-signal)_13%,transparent)]",
    bd: "border-[color-mix(in_srgb,var(--color-signal)_38%,transparent)]",
  },
  agent: {
    fg: "text-[var(--color-beacon)]",
    bg: "bg-[color-mix(in_srgb,var(--color-beacon)_13%,transparent)]",
    bd: "border-[color-mix(in_srgb,var(--color-beacon)_38%,transparent)]",
  },
  mute: {
    fg: "text-[var(--color-fog)]",
    bg: "bg-[color-mix(in_srgb,var(--color-mist)_18%,transparent)]",
    bd: "border-[var(--color-rail)]",
  },
};

const CLEAR = new Set([
  "confirmed",
  "arrival_cleared",
  "departure_cleared",
  "inspection_cleared",
  "completed",
  "operations",
  "pass",
  "low",
  "done",
  "ok",
  "resources_allocated",
  "no_inspection",
  "none",
  "proceed",
]);
const BLOCKED = new Set([
  "correction_required",
  "inspection_rejected",
  "error",
  "high",
  "blocked",
  "request_correction",
  "pending_review",
]);
const HOLD = new Set([
  "human_review",
  "inspection_required",
  "inspection_in_progress",
  "warning",
  "medium",
  "unconfirmed",
  "request_human_review",
  "request_inspection",
  "staged",
  "arrival_pending",
  "departure_pending",
]);

export function toneOf(value: string): Tone {
  const v = value.toLowerCase();
  if (CLEAR.has(v)) return "clear";
  if (BLOCKED.has(v)) return "blocked";
  if (HOLD.has(v)) return "hold";
  return "mute";
}

/* ============================================================
   Panel
   ============================================================ */

export function Panel({
  children,
  className = "",
  ticked = false,
  live = false,
}: {
  children: ReactNode;
  className?: string;
  ticked?: boolean;
  live?: boolean;
}) {
  return (
    <section
      className={`panel overflow-hidden ${ticked ? "ticked" : ""} ${
        live ? "scan" : ""
      } ${className}`}
    >
      {children}
    </section>
  );
}

export function PanelHead({
  title,
  sub,
  right,
  accent = "var(--color-signal)",
}: {
  title: string;
  sub?: string;
  right?: ReactNode;
  accent?: string;
}) {
  return (
    <header className="flex items-end justify-between gap-4 border-b border-[var(--color-rail)] px-5 py-3.5">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span
            className="inline-block h-2.5 w-[3px]"
            style={{ background: accent }}
          />
          <h2 className="display text-[13px] leading-none text-[var(--color-chalk)]">
            {title}
          </h2>
        </div>
        {sub && (
          <p className="mt-1.5 pl-[11px] text-[11.5px] leading-snug text-[var(--color-slate-ink)]">
            {sub}
          </p>
        )}
      </div>
      {right && <div className="shrink-0">{right}</div>}
    </header>
  );
}

/* ============================================================
   Chip
   ============================================================ */

export function Chip({
  children,
  tone = "mute",
  dot = false,
  className = "",
}: {
  children: ReactNode;
  tone?: Tone;
  dot?: boolean;
  className?: string;
}) {
  const t = TONE[tone];
  return (
    <span
      className={`mono inline-flex items-center gap-1.5 whitespace-nowrap rounded-[3px] border px-1.5 py-[3px] text-[10px] font-medium tracking-[0.09em] uppercase ${t.fg} ${t.bg} ${t.bd} ${className}`}
    >
      {dot && (
        <span className="pulse-dot inline-block h-1.5 w-1.5 rounded-full bg-current" />
      )}
      {children}
    </span>
  );
}

export function StatusChip({ status, dot }: { status: string; dot?: boolean }) {
  return (
    <Chip tone={toneOf(status)} dot={dot}>
      {status.replace(/_/g, " ")}
    </Chip>
  );
}

/* ============================================================
   Metric — the big Archivo numerals
   ============================================================ */

export function Metric({
  label,
  value,
  unit,
  hint,
  tone = "mute",
  delay = 0,
}: {
  label: string;
  value: ReactNode;
  unit?: string;
  hint?: string;
  tone?: Tone;
  delay?: number;
}) {
  return (
    <div
      className="rise group relative px-5 py-4"
      style={{ animationDelay: `${delay}ms` }}
    >
      <div className="label">{label}</div>
      <div className="mt-2.5 flex items-baseline gap-1.5">
        <span
          className={`numeral text-[40px] ${
            tone === "mute" ? "text-[var(--color-chalk)]" : TONE[tone].fg
          }`}
        >
          {value}
        </span>
        {unit && (
          <span className="mono text-[11px] text-[var(--color-slate-ink)]">
            {unit}
          </span>
        )}
      </div>
      {hint && (
        <div className="mt-2 text-[11px] leading-snug text-[var(--color-slate-ink)]">
          {hint}
        </div>
      )}
    </div>
  );
}

/* ============================================================
   Bars & meters
   ============================================================ */

export function ConfidenceBar({ value }: { value: number }) {
  const tone: Tone = value >= 0.85 ? "clear" : value >= 0.6 ? "hold" : "blocked";
  const color =
    tone === "clear"
      ? "var(--color-starboard)"
      : tone === "hold"
        ? "var(--color-signal)"
        : "var(--color-port)";
  return (
    <div className="flex items-center gap-2">
      <div className="relative h-[3px] w-16 overflow-hidden rounded-full bg-[var(--color-rail)]">
        <div
          className="absolute inset-y-0 left-0 rounded-full"
          style={{ width: `${Math.max(3, value * 100)}%`, background: color }}
        />
      </div>
      <span className={`mono text-[10.5px] ${TONE[tone].fg}`}>
        {(value * 100).toFixed(0)}%
      </span>
    </div>
  );
}

export function RiskMeter({
  score,
  level,
}: {
  score: number;
  level: "low" | "medium" | "high";
}) {
  const tone: Tone = level === "low" ? "clear" : level === "medium" ? "hold" : "blocked";
  const color =
    level === "low"
      ? "var(--color-starboard)"
      : level === "medium"
        ? "var(--color-signal)"
        : "var(--color-port)";
  const r = 46;
  const c = Math.PI * r; // half-circle arc length
  const filled = Math.min(1, score / 120) * c;

  return (
    <div className="relative w-[150px] shrink-0">
      <svg viewBox="0 0 120 68" className="w-full">
        <path
          d="M 14 60 A 46 46 0 0 1 106 60"
          fill="none"
          stroke="var(--color-rail)"
          strokeWidth="7"
          strokeLinecap="round"
        />
        <path
          d="M 14 60 A 46 46 0 0 1 106 60"
          fill="none"
          stroke={color}
          strokeWidth="7"
          strokeLinecap="round"
          strokeDasharray={`${filled} ${c}`}
          style={{ transition: "stroke-dasharray .9s cubic-bezier(.16,1,.3,1)" }}
        />
        {[30, 60].map((mark) => {
          const a = Math.PI * (1 - mark / 120);
          return (
            <line
              key={mark}
              x1={60 + Math.cos(a) * 39}
              y1={60 - Math.sin(a) * 39}
              x2={60 + Math.cos(a) * 53}
              y2={60 - Math.sin(a) * 53}
              stroke="var(--color-abyss)"
              strokeWidth="2"
            />
          );
        })}
      </svg>
      <div className="absolute inset-x-0 bottom-0 text-center">
        <div className={`numeral text-[34px] ${TONE[tone].fg}`}>{score}</div>
        <div className="label mt-1">{level} risk</div>
      </div>
    </div>
  );
}

/* ============================================================
   Misc
   ============================================================ */

export function KeyVal({
  k,
  v,
  mono = true,
}: {
  k: string;
  v: ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-dashed border-[var(--color-rail)] py-2 last:border-0">
      <span className="label shrink-0">{k}</span>
      <span
        className={`text-right text-[12.5px] text-[var(--color-chalk)] ${
          mono ? "mono" : ""
        }`}
      >
        {v}
      </span>
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-14 text-center">
      <div className="h-px w-10 bg-[var(--color-rail)]" />
      <p className="text-[12px] text-[var(--color-slate-ink)]">{children}</p>
    </div>
  );
}

export function Button({
  children,
  onClick,
  variant = "ghost",
  disabled,
  className = "",
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "ghost" | "signal" | "danger";
  disabled?: boolean;
  className?: string;
}) {
  const styles = {
    ghost:
      "border-[var(--color-rail)] text-[var(--color-fog)] hover:border-[var(--color-mist)] hover:text-[var(--color-chalk)] hover:bg-[var(--color-plate)]",
    signal:
      "border-[color-mix(in_srgb,var(--color-signal)_55%,transparent)] text-[var(--color-signal)] hover:bg-[color-mix(in_srgb,var(--color-signal)_14%,transparent)]",
    danger:
      "border-[color-mix(in_srgb,var(--color-port)_55%,transparent)] text-[var(--color-port)] hover:bg-[color-mix(in_srgb,var(--color-port)_14%,transparent)]",
  }[variant];

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`mono cursor-pointer rounded-[3px] border px-3 py-[7px] text-[10.5px] font-medium tracking-[0.12em] uppercase transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-40 ${styles} ${className}`}
    >
      {children}
    </button>
  );
}

export function Rule({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 py-1">
      <div className="hairline flex-1" />
      {label && <span className="label">{label}</span>}
      <div className="hairline flex-1" />
    </div>
  );
}
