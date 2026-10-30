import { SvelteSet } from "svelte/reactivity";
import { py, type HelpRequest, type LogLine, type Options, type Row, type Settings } from "./bridge";
import { setStrings } from "./i18n.svelte";
import { applyMotion } from "./motion";
import { configure, play } from "./sound";

export type Page = "profiles" | "log" | "agents" | "settings";

export const app = $state({
  phase: "boot" as "boot" | "lock" | "open",
  page: "profiles" as Page,
  rows: [] as Row[],
  help: [] as HelpRequest[],
  master: false,
  loaded: false,
  filter: "all",
  query: "",
  log: [] as LogLine[],
  settings: null as Settings | null,
  options: null as Options | null,
  version: "",
  // Bumped when the list should cascade in again (new filter, first load).
  wave: 0,
});

export const selected = new SvelteSet<string>();

let pending: Promise<void> | null = null;
let again = false;

/** Up and ready: the process runs and the launch finished. */
export const isLive = (r: Row) => r.running && !r.loading;

function sounds(before: Map<string, Row>, after: Row[]): void {
  if (!app.loaded) return;
  for (const r of after) {
    const old = before.get(r.name);
    if (!old) continue;
    if (!old.failed && r.failed) play("error");
    else if (!isLive(old) && isLive(r)) play("live");
    else if (old.running && !r.running) play(old.warmup ? "done" : "stop");
  }
}

/** Fetch a fresh snapshot; calls while one is in flight coalesce into one more. */
export function refresh(): Promise<void> {
  if (pending) {
    again = true;
    return pending;
  }
  pending = (async () => {
    try {
      const snap = await py().snapshot();
      const before = new Map(app.rows.map((r) => [r.name, r]));
      sounds(before, snap.profiles);
      const known = new Set(app.help.map((h) => h.id));
      if (snap.help.some((h) => !known.has(h.id))) play("help", true);
      app.rows = snap.profiles;
      app.help = snap.help;
      app.master = snap.master;
      const names = new Set(snap.profiles.map((r) => r.name));
      for (const n of selected) if (!names.has(n)) selected.delete(n);
      if (!app.loaded) {
        app.loaded = true;
        app.wave++;
      }
    } finally {
      pending = null;
    }
    if (again) {
      again = false;
      await refresh();
    }
  })();
  return pending;
}

export function applySettings(s: Settings): void {
  app.settings = s;
  configure(s.sound, s.sound_volume);
  applyMotion(s.motion, s.cursor);
}

export async function saveSettings(changes: Partial<Settings>): Promise<string | undefined> {
  const result = await py().settings_update(changes);
  if (result.error) return result.error;
  applySettings(result as Settings);
  return undefined;
}

export async function setLanguage(code: string): Promise<void> {
  const result = await py().set_language(code);
  if (!result.error) {
    setStrings(result.language, result.strings);
    if (app.settings) app.settings.language = result.language;
  }
}

export async function loadOptions(): Promise<Options> {
  app.options = await py().options();
  return app.options;
}

/** Called once the profiles are readable (unlocked, or no master password). */
export async function opened(): Promise<void> {
  app.phase = "open";
  window.__cf = {
    push(message) {
      if (message.type === "changed") void refresh();
      else if (message.type === "log") {
        app.log.push(...message.lines);
        if (app.log.length > 2000) app.log.splice(0, app.log.length - 2000);
      }
    },
  };
  app.log = await py().log_history();
  await Promise.all([refresh(), loadOptions()]);
}

export function setFilter(id: string): void {
  if (app.filter === id) return;
  app.filter = id;
  app.wave++;
  play("toggle");
}
