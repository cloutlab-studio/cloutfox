<script lang="ts">
  import { play } from "../lib/sound";

  let {
    value = $bindable(""),
    options,
    onchange,
    dark = false,
  }: {
    value?: string;
    options: { value: string; label: string }[];
    onchange?: (value: string) => void;
    dark?: boolean;
  } = $props();

  const index = $derived(Math.max(0, options.findIndex((o) => o.value === value)));
</script>

<div class="seg" class:dark role="radiogroup" style:--n={options.length} style:--i={index}>
  <span class="thumb" aria-hidden="true"></span>
  {#each options as o (o.value)}
    <button
      type="button"
      role="radio"
      aria-checked={o.value === value}
      class:on={o.value === value}
      data-press
      onclick={() => {
        if (value === o.value) return;
        value = o.value;
        play("toggle");
        onchange?.(o.value);
      }}>{o.label}</button
    >
  {/each}
</div>

<style>
  .seg {
    position: relative;
    display: grid;
    grid-template-columns: repeat(var(--n), 1fr);
    border: 2px solid var(--t-line);
    background: var(--t-surface);
  }
  .thumb {
    position: absolute;
    top: 0;
    bottom: 0;
    left: 0;
    width: calc(100% / var(--n));
    background: var(--t-accent);
    border-right: 2px solid var(--t-line);
    border-left: 2px solid var(--t-line);
    transform: translateX(calc(var(--i) * 100%));
    transition: transform var(--t-dur) var(--t-ease);
  }
  button {
    position: relative;
    height: 34px;
    padding: 0 10px;
    border: 0;
    background: transparent;
    font: 600 11.5px/1 var(--font-mono);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    white-space: nowrap;
  }
  .dark {
    border-color: var(--rail-line);
    background: var(--rail-deep);
  }
  .dark button {
    color: var(--rail-muted);
  }
  .dark button.on {
    color: var(--t-fg);
  }
  .dark .thumb {
    border-color: var(--t-fg);
  }
</style>
