/**
 * Collect garbage every half minute when the window exposes gc() (src/ui/window.py).
 * Qt WebEngine leaves Blink's heap to grow while the JS heap stays small; without
 * this the renderer runs out of memory after about an hour of drawing frames.
 */
export function collectGarbage(every = 30_000): void {
  const gc = (window as { gc?: () => void }).gc;
  if (typeof gc === "function") setInterval(gc, every);
}
