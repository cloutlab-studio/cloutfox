<script lang="ts">
  import type { Snippet } from "svelte";
  import { play } from "../lib/sound";

  let {
    checked = $bindable(false),
    indeterminate = false,
    label,
    title,
    onchange,
    children,
  }: {
    checked?: boolean;
    indeterminate?: boolean;
    label?: string;
    title?: string;
    onchange?: (v: boolean) => void;
    children?: Snippet;
  } = $props();
</script>

<label class="cb" {title}>
  <input
    type="checkbox"
    bind:checked
    {indeterminate}
    aria-label={label ?? title}
    onchange={() => {
      play("toggle");
      onchange?.(checked);
    }}
  />
  <span class="box" data-press>
    <svg viewBox="0 0 16 16" aria-hidden="true">
      {#if indeterminate}
        <path d="M3.5 8h9" />
      {:else}
        <path d="M3 8.5l3.2 3.2L13 4.8" />
      {/if}
    </svg>
  </span>
  {#if label}<span class="text">{label}</span>{/if}
  {#if children}{@render children()}{/if}
</label>

<style>
  .cb {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    min-width: 0;
  }
  input {
    position: absolute;
    opacity: 0;
    pointer-events: none;
  }
  .box {
    flex: none;
    width: 20px;
    height: 20px;
    display: grid;
    place-items: center;
    border: 2px solid var(--t-line);
    background: var(--t-surface);
    transition:
      background-color var(--t-dur-fast) linear,
      transform var(--t-dur) var(--t-ease);
  }
  svg {
    width: 14px;
    height: 14px;
    fill: none;
    stroke: var(--t-fg);
    stroke-width: 2.6;
    stroke-linecap: square;
    stroke-dasharray: 16;
    stroke-dashoffset: 16;
    transition: stroke-dashoffset 0.22s var(--t-ease-out);
  }
  input:checked + .box,
  input:indeterminate + .box {
    background: var(--t-accent);
    transform: rotate(-6deg);
  }
  input:checked + .box svg,
  input:indeterminate + .box svg {
    stroke-dashoffset: 0;
  }
  input:focus-visible + .box {
    outline: 3px solid var(--t-focus);
    outline-offset: 2px;
  }
  .cb:hover .box {
    box-shadow: 2px 2px 0 var(--t-line);
  }
  .text {
    font-size: 14px;
    overflow: hidden;
    text-overflow: ellipsis;
  }
</style>
