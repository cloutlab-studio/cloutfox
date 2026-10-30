import type { Settings } from "./bridge";

const query = window.matchMedia("(prefers-reduced-motion: reduce)");

export function reduced(choice: Settings["motion"]): boolean {
  return choice === "reduced" || (choice === "system" && query.matches);
}

/** Set data-motion and data-cursor on <html>; CSS and the cursor read them. */
export function applyMotion(choice: Settings["motion"], cursor: boolean): void {
  const root = document.documentElement;
  const less = reduced(choice);
  root.dataset.motion = less ? "reduced" : "full";
  const fine = window.matchMedia("(pointer: fine)").matches;
  root.dataset.cursor = cursor && !less && fine ? "on" : "off";
}

/** Set data-away on <html> while the window is in the background; looping animations read it. */
export function watchFocus(): void {
  const root = document.documentElement;
  root.toggleAttribute("data-away", !document.hasFocus());
  window.addEventListener("blur", () => root.toggleAttribute("data-away", true));
  window.addEventListener("focus", () => root.toggleAttribute("data-away", false));
}

export function onSystemMotion(cb: () => void): void {
  query.addEventListener("change", cb);
}

/** Delay for the n-th item of a cascade; only the first few wait. */
export function stagger(i: number, step = 28, max = 18): string {
  return `${Math.min(i, max) * step}ms`;
}
