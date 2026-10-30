import { describe, expect, it } from "vitest";
import { GAPS, Limiter } from "./sound";

describe("sound limiter", () => {
  it("plays a voice once per gap", () => {
    const l = new Limiter();
    expect(l.allow("live", 0)).toBe(true);
    expect(l.allow("live", GAPS.live - 1)).toBe(false);
    expect(l.allow("live", GAPS.live)).toBe(true);
  });

  it("keeps voices apart", () => {
    const l = new Limiter();
    expect(l.allow("live", 0)).toBe(true);
    expect(l.allow("stop", 1)).toBe(true);
  });
});
