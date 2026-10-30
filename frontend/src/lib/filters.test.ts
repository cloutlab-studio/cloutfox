import { describe, expect, it } from "vitest";
import type { Row } from "./bridge";
import { filterCounts, topTags, visible } from "./filters";
import { format } from "./i18n.svelte";
import { lastSeen } from "./format";

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
    device: "",
    encrypted: false,
    sealed: false,
    locked: false,
    ...extra,
  };
}

const rows = [
  row("fb-01", { proxy: "192.0.2.10:8080", tags: ["fb", "us"], running: true }),
  row("fb-02", { tags: ["fb"], status: "banned" }),
  row("tt-01", { engine: "chrome", wireguard: "198.51.100.7:51820", notes: "Client A" }),
];

describe("filters", () => {
  it("counts filters and hides empty statuses", () => {
    const counts = Object.fromEntries(filterCounts(rows).map((f) => [f.id, f.count]));
    expect(counts).toMatchObject({ all: 3, running: 1, proxy: 2, direct: 1, chrome: 1 });
    expect(counts["status:banned"]).toBe(1);
    expect("status:new" in counts).toBe(false);
    expect(counts["tag:fb"]).toBe(2);
  });

  it("orders tags by use, then name", () => {
    expect(topTags(rows)).toEqual(["fb", "us"]);
  });

  it("searches name, proxy, tunnel, tags and notes", () => {
    expect(visible(rows, "all", "192.0.2").map((r) => r.name)).toEqual(["fb-01"]);
    expect(visible(rows, "all", "client a").map((r) => r.name)).toEqual(["tt-01"]);
    expect(visible(rows, "tag:fb", "02").map((r) => r.name)).toEqual(["fb-02"]);
    expect(visible(rows, "proxy", "").length).toBe(2);
  });
});

describe("text", () => {
  it("formats Python-style placeholders and leaves unknown ones", () => {
    expect(format("{count} of {total}", { count: 2, total: 5 })).toBe("2 of 5");
    expect(format("{missing}")).toBe("{missing}");
  });

  it("shows the last launch as dd.mm HH:MM", () => {
    expect(lastSeen("2026-10-29T14:05:09+03:00")).toBe("29.10 14:05");
    expect(lastSeen(null)).toBe("");
  });
});
