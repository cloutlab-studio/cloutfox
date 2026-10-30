import type { Row } from "./bridge";

export const STATUSES = ["new", "warming", "active", "paused", "banned"];
/** How many tags get their own filter: the most used ones. */
export const TAG_FILTERS = 8;

export function topTags(rows: Row[], limit = TAG_FILTERS): string[] {
  const counts = new Map<string, number>();
  for (const r of rows) for (const t of r.tags) counts.set(t, (counts.get(t) ?? 0) + 1);
  return [...counts.keys()]
    .sort((a, b) => counts.get(b)! - counts.get(a)! || a.localeCompare(b))
    .slice(0, limit);
}

export function filterTest(id: string): (r: Row) => boolean {
  if (id === "running") return (r) => r.running;
  if (id === "proxy") return (r) => Boolean(r.proxy || r.wireguard);
  if (id === "direct") return (r) => !(r.proxy || r.wireguard);
  if (id === "chrome") return (r) => r.engine === "chrome";
  if (id.startsWith("tag:")) return (r) => r.tags.includes(id.slice(4));
  if (id.startsWith("status:")) return (r) => r.status === id.slice(7);
  return () => true;
}

/** Every filter id the rail shows, with its count. */
export function filterCounts(rows: Row[]): { id: string; count: number }[] {
  const ids = [
    "all",
    "running",
    "proxy",
    "direct",
    "chrome",
    ...STATUSES.map((s) => `status:${s}`),
    ...topTags(rows).map((t) => `tag:${t}`),
  ];
  return ids
    .map((id) => ({ id, count: rows.filter(filterTest(id)).length }))
    .filter((f) => !f.id.startsWith("status:") || f.count > 0);
}

export function matches(r: Row, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return (
    r.name.toLowerCase().includes(q) ||
    r.proxy.toLowerCase().includes(q) ||
    (r.wireguard ?? "").toLowerCase().includes(q) ||
    r.tags.some((t) => t.includes(q)) ||
    r.notes.toLowerCase().includes(q)
  );
}

export function visible(rows: Row[], filter: string, query: string): Row[] {
  const test = filterTest(filter);
  return rows.filter((r) => test(r) && matches(r, query));
}
