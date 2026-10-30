import type { Component } from "svelte";
import { play } from "./sound";

// Modals and drawers as a stack: open() resolves with what the overlay passed
// to close(). Esc closes the top one.

interface Entry {
  id: number;
  component: Component<any>;
  props: Record<string, unknown>;
  resolve: (value: unknown) => void;
}

let seq = 0;
export const stack = $state<Entry[]>([]);

export function open<T = unknown>(component: Component<any>, props: Record<string, unknown> = {}): Promise<T | undefined> {
  play("open");
  return new Promise((resolve) => {
    stack.push({ id: ++seq, component, props, resolve: resolve as (v: unknown) => void });
  });
}

export function close(id: number, value?: unknown): void {
  const i = stack.findIndex((e) => e.id === id);
  if (i < 0) return;
  const [entry] = stack.splice(i, 1);
  play("close");
  entry.resolve(value);
}

/** Esc: close the top overlay unless it must be answered (props.sticky). */
export function closeTop(): boolean {
  const top = stack.at(-1);
  if (!top) return false;
  if (!top.props.sticky) close(top.id);
  return true;
}
