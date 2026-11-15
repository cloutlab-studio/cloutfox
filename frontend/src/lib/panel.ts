// What the page says about itself. The window reloads a panel that never reports
// ready (src/ui/window.py) and logs the numbers, so a leak or a 4K window at 200%
// scaling shows up in the app log and in the diagnostics archive.

import { py } from "./bridge";

export function panelStats(bootStart = 0): Record<string, string | number> {
  const memory = (performance as { memory?: { usedJSHeapSize: number; jsHeapSizeLimit: number } }).memory;
  const stats: Record<string, string | number> = {
    user_agent: navigator.userAgent,
    device_pixel_ratio: window.devicePixelRatio,
    screen: `${screen.width}x${screen.height}`,
    window: `${innerWidth}x${innerHeight}`,
    heap_used: memory?.usedJSHeapSize ?? 0,
    heap_limit: memory?.jsHeapSizeLimit ?? 0,
    dom_nodes: document.getElementsByTagName("*").length,
    body_text: (document.body.innerText || "").length,
    uptime_s: Math.round(performance.now() / 1000),
  };
  if (bootStart) stats.boot_ms = Math.round(performance.now() - bootStart);
  return stats;
}

/** Keep the window's liveness check honest and the log useful over a long day. */
export function startHeartbeat(every = 60_000): void {
  const tick = () => {
    try {
      void py().panel_ready(panelStats());
    } catch {
      // The bridge is gone (reload in progress): the next tick after load reports.
    }
  };
  setInterval(tick, every);
}
