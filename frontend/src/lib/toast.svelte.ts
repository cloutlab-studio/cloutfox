import { play } from "./sound";

export type ToastKind = "info" | "ok" | "error";

export interface Toast {
  id: number;
  kind: ToastKind;
  text: string;
}

let seq = 0;
export const toasts = $state<Toast[]>([]);

export function dismiss(id: number): void {
  const i = toasts.findIndex((t) => t.id === id);
  if (i >= 0) toasts.splice(i, 1);
}

export function toast(text: string, kind: ToastKind = "info", ms = 4200): void {
  const id = ++seq;
  toasts.push({ id, kind, text });
  while (toasts.length > 4) toasts.shift();
  if (kind === "error") play("error");
  else if (kind === "ok") play("done");
  setTimeout(() => dismiss(id), kind === "error" ? ms + 2500 : ms);
}

/** Toast a bridge result: its error, else its message (if any). */
export function report(result: { error?: string; message?: string } | null | undefined): boolean {
  if (result?.error) {
    toast(result.error, "error");
    return false;
  }
  if (result?.message) toast(result.message, "ok");
  return true;
}
