import type { Row } from "./bridge";

export const OS_LABELS: Record<string, string> = { windows: "WIN", macos: "MAC", linux: "LIN" };

/** When the profile last came up, as dd.mm HH:MM, or "". */
export function lastSeen(at: string | null): string {
  if (!at) return "";
  const m = /^\d{4}-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(at);
  return m ? `${m[2]}.${m[1]} ${m[3]}:${m[4]}` : "";
}

/** The exit IP and country seen at the last launch, "" if none. */
export function exitIp(row: Row): string {
  return [row.last.ip, row.last.country].filter(Boolean).join(" · ");
}

export function initials(name: string): string {
  return name.replace(/[^\p{L}\p{N}]+/gu, " ").trim().slice(0, 2).toUpperCase() || "?";
}
