// The Python side (src/ui/bridge.py), reached through pywebview's js_api.

export type Engine = "camoufox" | "chrome";
export type Os = "windows" | "macos" | "linux";

export interface Row {
  name: string;
  os: Os;
  engine: Engine;
  proxy: string;
  scheme: string;
  wireguard: string | null;
  timezone: string | null;
  locale: string | null;
  tags: string[];
  notes: string;
  status: string;
  temporary: boolean;
  rotate: boolean;
  last: { at: string | null; ip: string | null; country: string | null };
  running: boolean;
  loading: boolean;
  failed: boolean;
  since: string;
  warmup: { done: number; total: number } | null;
  device: string;
  encrypted: boolean;
  sealed: boolean;
  locked: boolean;
}

export interface HelpRequest {
  id: string;
  profile: string;
  reason: string;
}

export interface Snapshot {
  profiles: Row[];
  help: HelpRequest[];
  master: boolean;
}

export interface Settings {
  geo_guard: boolean;
  backup_dir: string;
  backup_hours: number;
  backup_keep: number;
  last_backup: string;
  warmup_sites: string[];
  warmup_count: number;
  language: string;
  sound: boolean;
  sound_volume: number;
  motion: "system" | "full" | "reduced";
  cursor: boolean;
}

export interface Boot {
  locked: boolean;
  language: string;
  strings: Record<string, string>;
  settings: Settings;
  version: string;
  platform: string;
}

export interface LogLine {
  id: number;
  at: string;
  text: string;
}

export interface Extension {
  id: string;
  name: string;
  version: string;
  engine: Engine;
}

export interface Options {
  statuses: string[];
  extensions: Extension[];
  max_bulk: number;
  warmup_counts: number[];
  backup_hours: number[];
  backup_keep: number[];
}

export interface ProfileDetail {
  name: string;
  proxy: string;
  os: Os;
  engine: Engine;
  timezone: string;
  locale: string;
  tags: string;
  notes: string;
  status: string;
  start_urls: string;
  proxy_rotate_url: string;
  extensions: string[];
  wireguard: string | null;
  running: boolean;
}

export interface GeoReport {
  exit_ip: string | null;
  country: string | null;
  timezone: string | null;
  timezone_pinned: boolean;
  locale: string | null;
  locale_pinned: boolean;
  suggested_locale: string | null;
  sources: {
    source: string;
    ip: string | null;
    country: string | null;
    city: string | null;
    timezone: string | null;
    error: string | null;
  }[];
  warnings: string[];
  error: string | null;
}

export interface Activity {
  at: string;
  action: string;
  params: Record<string, unknown> | string;
  ok: boolean;
  error?: string;
}

export interface McpInfo {
  url: string;
  has_token: boolean;
  configs: { id: string; name: string; where: string; language: string; code: string }[];
}

export interface EncryptionInfo {
  encrypted: boolean;
  key_by: string[];
  needs_password: boolean;
  master: boolean;
  ram: boolean;
  running: boolean;
}

/** Errors the person should read come back as {error}; anything else is data. */
export type Result<T = object> = T & { error?: string; message?: string; cancelled?: boolean };
export type FieldError = { field: string; error: string } | null;

export interface Api {
  boot(): Promise<Boot>;
  unlock(password: string): Promise<Result>;
  unlock_recovery(key: string): Promise<Result>;
  start(): Promise<Result>;
  set_language(code: string): Promise<Result<{ language: string; strings: Record<string, string> }>>;
  snapshot(): Promise<Snapshot>;
  log_history(): Promise<LogLine[]>;
  profile_detail(name: string): Promise<ProfileDetail | null>;
  options(): Promise<Options>;
  activity(name: string): Promise<Activity[]>;
  profile_save(original: string | null, form: Record<string, unknown>): Promise<FieldError>;
  profile_delete(names: string[]): Promise<{ deleted: number; skipped: number }>;
  profile_clone(name: string, newName: string): Promise<Result | null>;
  bulk_create(form: Record<string, unknown>): Promise<Result<{ created?: number }>>;
  bulk_edit(names: string[], form: Record<string, unknown>): Promise<Result>;
  import_profiles(): Promise<{ picked: number; imported: number }>;
  export_profiles(names: string[], includeData: boolean): Promise<Result<{ exported?: number; folder?: string }>>;
  launch(name: string): Promise<Result<{ needs_password?: boolean }>>;
  launch_many(names: string[]): Promise<{ started: number; skipped: number }>;
  stop_many(names: string[]): Promise<{ stopped: number }>;
  warmup_info(): Promise<{ count: number; shared: number }>;
  warmup(names: string[], own: string, count: number): Promise<Result<{ started?: number; needs_password?: string }>>;
  rotate(name: string): Promise<Result>;
  show_browser(name: string): Promise<Result>;
  answer_help(id: string, done: boolean): Promise<Result>;
  check_proxy(proxy: string): Promise<Result<{ ok?: boolean }>>;
  check_geo(proxy: string, timezone: string, locale: string): Promise<Result<Partial<GeoReport>>>;
  cookies_info(name: string): Promise<{ fingerprint: string }>;
  cookies_export(name: string, fmt: "json" | "netscape"): Promise<Result>;
  cookies_import(name: string): Promise<Result>;
  fingerprint_reset(name: string): Promise<Result>;
  wireguard_load(): Promise<Result<{ text?: string }>>;
  wireguard_check(name: string, text: string): Promise<Result<Partial<GeoReport>>>;
  wireguard_save(name: string, text: string | null): Promise<Result>;
  encryption_info(name: string): Promise<EncryptionInfo>;
  profile_unlock(name: string, password: string): Promise<Result>;
  encrypt(name: string, password: string): Promise<Result>;
  decrypt(name: string): Promise<Result>;
  set_profile_password(name: string, password: string): Promise<Result>;
  security_info(): Promise<{ master: boolean; duress: boolean }>;
  enable_master(password: string): Promise<Result<{ key?: string }>>;
  change_master(password: string): Promise<Result>;
  new_recovery_key(): Promise<{ key: string }>;
  disable_master(): Promise<Result>;
  set_duress(password: string | null): Promise<Result>;
  settings(): Promise<Settings>;
  settings_update(changes: Partial<Settings>): Promise<Result<Partial<Settings>>>;
  extension_add(folder: boolean): Promise<Result>;
  extension_remove(id: string): Promise<Result>;
  backup_dir(): Promise<Result<Partial<Settings>>>;
  backup_now(): Promise<Result>;
  mcp_info(realToken: boolean): Promise<McpInfo>;
  mcp_health(): Promise<{ ok: boolean; error?: string }>;
  open_external(url: string): Promise<Result>;
}

export type Push = { type: "changed" } | { type: "log"; lines: LogLine[] };

declare global {
  interface Window {
    pywebview?: { api: Api };
    __cf?: { push(message: Push): void };
  }
}

let ready: Promise<Api> | null = null;

/** The API once pywebview has injected it (or the mock while developing in a browser). */
export function bridge(): Promise<Api> {
  if (ready) return ready;
  ready = new Promise<Api>((resolve) => {
    if (window.pywebview?.api) return resolve(window.pywebview.api);
    window.addEventListener("pywebviewready", () => resolve(window.pywebview!.api), { once: true });
    if (import.meta.env.DEV) {
      // No window around the page: `npm run dev` in a plain browser.
      setTimeout(async () => {
        if (window.pywebview?.api) return;
        const { mockApi } = await import("./mock");
        resolve(mockApi());
      }, 400);
    }
  });
  return ready;
}

let api: Api | null = null;

export async function init(): Promise<Api> {
  api = await bridge();
  return api;
}

/** The API after init(); every screen runs after it. */
export function py(): Api {
  if (!api) throw new Error("bridge not ready");
  return api;
}
