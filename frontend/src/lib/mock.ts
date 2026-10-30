// Development only (`npm run dev` in a plain browser): a fake bridge with fake
// profiles, so the panel can be designed without Python. Addresses come from
// the documentation ranges; nothing here is real.

import type { Api, Row, Settings } from "./bridge";

const ru: Record<string, string> = {};

function row(name: string, extra: Partial<Row> = {}): Row {
  return {
    name,
    os: "windows",
    engine: "camoufox",
    proxy: "",
    scheme: "",
    wireguard: null,
    timezone: null,
    locale: null,
    tags: [],
    notes: "",
    status: "",
    temporary: false,
    rotate: false,
    last: { at: null, ip: null, country: null },
    running: false,
    loading: false,
    failed: false,
    since: "",
    warmup: null,
    device: "1920x1080 · 8 CPU",
    encrypted: false,
    sealed: false,
    locked: false,
    ...extra,
  };
}

export function mockApi(): Api {
  const rows: Row[] = [
    row("shop-facebook-01", {
      proxy: "192.0.2.10:8080",
      scheme: "http",
      tags: ["fb", "us"],
      status: "active",
      running: true,
      since: "14:05",
      last: { at: "2026-10-29T14:05:00+03:00", ip: "192.0.2.10", country: "US" },
    }),
    row("shop-facebook-02", { proxy: "192.0.2.11:8080", scheme: "socks5", tags: ["fb"], status: "warming", running: true, warmup: { done: 3, total: 10 } }),
    row("tiktok-eu-01", { engine: "chrome", os: "macos", wireguard: "198.51.100.7:51820", timezone: "Europe/Berlin", locale: "de-DE", status: "new" }),
    row("ads-client-a", { proxy: "203.0.113.5:3128", scheme: "http", notes: "Client A, main account", encrypted: true, failed: true }),
    row("shopee-vn-07", { os: "linux", status: "banned", tags: ["shopee"], last: { at: "2026-10-28T09:12:00+03:00", ip: "203.0.113.9", country: "VN" } }),
    row("google-ads-03", { proxy: "198.51.100.20:1080", scheme: "socks5", loading: true, tags: ["google"], rotate: true }),
  ];
  for (let i = 1; i <= 14; i++) rows.push(row(`batch-${String(i).padStart(2, "0")}`, { tags: ["batch"], proxy: `192.0.2.${40 + i}:8000`, scheme: "http" }));
  const settings: Settings = {
    geo_guard: false,
    backup_dir: "",
    backup_hours: 0,
    backup_keep: 7,
    last_backup: "",
    warmup_sites: ["google.com", "wikipedia.org", "bbc.com"],
    warmup_count: 10,
    language: "ru",
    sound: true,
    sound_volume: 60,
    motion: "system",
    cursor: true,
  };
  const ok = async () => ({});
  const api: Partial<Api> = {
    boot: async () => {
      const strings = await fetch("/mock-strings.json").then((r) => (r.ok ? r.json() : ru)).catch(() => ru);
      return { locked: location.hash === "#lock", language: "ru", strings, settings, version: "dev", platform: "linux" };
    },
    unlock: async (pw) => (pw === "pass" ? {} : { error: "Неверный пароль" }),
    unlock_recovery: async () => ({ error: "Ключ восстановления не подходит" }),
    start: ok,
    snapshot: async () => ({
      profiles: rows,
      help: location.hash === "#help" ? [{ id: "h1", profile: "shop-facebook-01", reason: "Solve the captcha on the login page, please." }] : [],
      master: false,
    }),
    log_history: async () => [
      { id: 1, at: "14:05:01", text: "Запускаю shop-facebook-01..." },
      { id: 2, at: "14:05:07", text: "Browser started" },
      { id: 3, at: "14:06:12", text: "[ads-client-a] LAUNCH_FAILED: proxy refused" },
    ],
    options: async () => ({
      statuses: ["", "new", "warming", "active", "paused", "banned"],
      extensions: [{ id: "ublock", name: "uBlock Origin", version: "1.60", engine: "camoufox" }],
      max_bulk: 500,
      warmup_counts: [3, 5, 10, 15, 20, 30],
      backup_hours: [0, 6, 12, 24, 72, 168],
      backup_keep: [3, 7, 14, 30],
    }),
    launch: async (name) => {
      const r = rows.find((x) => x.name === name)!;
      r.loading = !r.running;
      setTimeout(() => {
        r.loading = false;
        r.running = !r.running;
        r.since = "15:00";
        window.__cf?.push({ type: "changed" });
      }, 1200);
      return {};
    },
    settings: async () => settings,
    settings_update: async (changes) => Object.assign(settings, changes),
    set_language: async (code) => ({ language: code, strings: ru }),
    profile_detail: async (name) => ({
      name,
      proxy: "",
      os: "windows",
      engine: "camoufox",
      timezone: "",
      locale: "",
      tags: "",
      notes: "",
      status: "",
      start_urls: "",
      proxy_rotate_url: "",
      extensions: [],
      wireguard: null,
      running: false,
    }),
    mcp_info: async () => ({
      url: "http://127.0.0.1:8000/mcp",
      has_token: false,
      configs: [{ id: "claude-code", name: "Claude Code", where: "terminal", language: "bash", code: "claude mcp add cloutfox ..." }],
    }),
    mcp_health: async () => ({ ok: true }),
    security_info: async () => ({ master: false, duress: false }),
    activity: async () => [],
    cookies_info: async () => ({ fingerprint: "Windows, 1920x1080, 8" }),
    encryption_info: async () => ({ encrypted: false, key_by: [], needs_password: false, master: false, ram: true, running: false }),
    warmup_info: async () => ({ count: 10, shared: 3 }),
  };
  return new Proxy(api as Api, {
    get(target, prop: string) {
      return (target as unknown as Record<string, unknown>)[prop] ?? (async () => ({}));
    },
  });
}
