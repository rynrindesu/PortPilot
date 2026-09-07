/** Everything in the console is displayed in Singapore time — the port's clock. */
export const SGT = "Asia/Singapore";

const sgt = (opts: Intl.DateTimeFormatOptions) =>
  new Intl.DateTimeFormat("en-GB", { timeZone: SGT, ...opts });

const fTime = sgt({ hour: "2-digit", minute: "2-digit", hour12: false });
const fDay = sgt({ day: "2-digit", month: "short" });
const fFull = sgt({
  day: "2-digit",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});
const fClock = sgt({
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});
const fDate = sgt({ weekday: "short", day: "2-digit", month: "short", year: "numeric" });

export const hhmm = (iso: string | null | undefined) =>
  iso ? fTime.format(new Date(iso)) : "—";

export const dayShort = (iso: string) => fDay.format(new Date(iso)).toUpperCase();

export const stamp = (iso: string | null | undefined) =>
  iso ? fFull.format(new Date(iso)).toUpperCase() : "—";

export const clock = (d: Date) => fClock.format(d);

export const longDate = (d: Date) => fDate.format(d).toUpperCase();

/** Signed minute delta between two ISO timestamps. */
export const deltaMinutes = (from: string, to: string) =>
  Math.round((new Date(to).getTime() - new Date(from).getTime()) / 60000);

/** "+2h 15m" / "-45m" / "on time" */
export function humanDelta(minutes: number): string {
  if (minutes === 0) return "on time";
  const sign = minutes > 0 ? "+" : "−";
  const abs = Math.abs(minutes);
  const h = Math.floor(abs / 60);
  const m = abs % 60;
  if (h === 0) return `${sign}${m}m`;
  if (m === 0) return `${sign}${h}h`;
  return `${sign}${h}h ${m}m`;
}

export const minutesBetween = (a: string, b: string) =>
  (new Date(b).getTime() - new Date(a).getTime()) / 60000;

export const relative = (iso: string, now = Date.now()) => {
  const diff = Math.round((now - new Date(iso).getTime()) / 60000);
  if (diff < 0) {
    const ahead = Math.abs(diff);
    return ahead < 60 ? `in ${ahead}m` : `in ${Math.round(ahead / 60)}h`;
  }
  if (diff < 1) return "just now";
  if (diff < 60) return `${diff}m ago`;
  const h = Math.floor(diff / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
};

export const titleCase = (s: string) =>
  s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

export const upperSnake = (s: string) => s.replace(/_/g, " ").toUpperCase();

export const pct = (n: number) => `${Math.round(n * 100)}%`;

export const clamp = (n: number, lo: number, hi: number) =>
  Math.min(hi, Math.max(lo, n));
