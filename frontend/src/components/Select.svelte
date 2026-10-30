<script lang="ts">
  import { play } from "../lib/sound";
  import Icon from "./Icon.svelte";

  type Option = { value: string; label: string };

  let {
    value = $bindable(""),
    options,
    disabled = false,
    mono = false,
    onchange,
  }: {
    value?: string;
    options: Option[];
    disabled?: boolean;
    mono?: boolean;
    onchange?: (value: string) => void;
  } = $props();

  let isOpen = $state(false);
  let root: HTMLDivElement;
  let active = $state(0);
  const current = $derived(options.find((o) => o.value === value) ?? options[0]);

  function choose(o: Option) {
    value = o.value;
    isOpen = false;
    play("toggle");
    onchange?.(o.value);
  }

  function toggle() {
    if (disabled) return;
    isOpen = !isOpen;
    active = Math.max(0, options.findIndex((o) => o.value === value));
    play("tap");
  }

  function key(e: KeyboardEvent) {
    if (disabled) return;
    if (!isOpen && (e.key === "Enter" || e.key === " " || e.key === "ArrowDown")) {
      e.preventDefault();
      toggle();
    } else if (isOpen) {
      if (e.key === "ArrowDown") active = Math.min(options.length - 1, active + 1);
      else if (e.key === "ArrowUp") active = Math.max(0, active - 1);
      else if (e.key === "Enter") choose(options[active]);
      else if (e.key === "Escape") {
        isOpen = false;
        e.stopPropagation();
      } else return;
      e.preventDefault();
    }
  }

  $effect(() => {
    if (!isOpen) return;
    const away = (e: PointerEvent) => {
      if (!root.contains(e.target as Node)) isOpen = false;
    };
    window.addEventListener("pointerdown", away, true);
    return () => window.removeEventListener("pointerdown", away, true);
  });
</script>

<div class="select" class:open={isOpen} class:disabled bind:this={root}>
  <button
    type="button"
    class="trigger"
    class:mono
    {disabled}
    data-press
    aria-haspopup="listbox"
    aria-expanded={isOpen}
    onclick={toggle}
    onkeydown={key}
  >
    <span class="value">{current?.label ?? ""}</span>
    <span class="chev"><Icon name="down" size={15} /></span>
  </button>
  {#if isOpen}
    <ul class="menu" role="listbox">
      {#each options as o, i (o.value)}
        <li>
          <button
            type="button"
            role="option"
            aria-selected={o.value === value}
            class:active={i === active}
            class:chosen={o.value === value}
            class:mono
            data-press
            style:animation-delay="{i * 18}ms"
            onmouseenter={() => (active = i)}
            onclick={() => choose(o)}>{o.label}</button
          >
        </li>
      {/each}
    </ul>
  {/if}
</div>

<style>
  .select {
    position: relative;
    min-width: 0;
  }
  .trigger {
    width: 100%;
    height: 38px;
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 0 10px 0 12px;
    border: 2px solid var(--t-line);
    background: var(--t-surface);
    text-align: left;
    font-size: 14px;
    transition:
      box-shadow var(--t-dur) var(--t-ease),
      transform var(--t-dur) var(--t-ease);
  }
  .trigger:focus-visible,
  .open .trigger {
    outline: none;
    box-shadow: 4px 4px 0 var(--t-focus);
    transform: translate(-1px, -1px);
  }
  .value {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .chev {
    transition: transform var(--t-dur) var(--t-ease);
  }
  .open .chev {
    transform: rotate(180deg);
  }
  .disabled .trigger {
    background: var(--t-bg-2);
    border-color: var(--rule-soft);
    color: var(--dim);
    cursor: default;
  }
  .menu {
    position: absolute;
    z-index: 50;
    top: calc(100% + 6px);
    left: 0;
    right: 0;
    max-height: 260px;
    overflow: auto;
    margin: 0;
    padding: 0;
    list-style: none;
    border: 2px solid var(--t-line);
    background: var(--t-surface);
    box-shadow: var(--t-hard-sm);
    transform-origin: top;
    animation: drop var(--t-dur) var(--t-ease);
  }
  .menu button {
    width: 100%;
    padding: 9px 12px;
    border: 0;
    border-bottom: 1px solid var(--t-bg-2);
    background: transparent;
    text-align: left;
    font-size: 14px;
    animation: rise 0.24s var(--t-ease-out) backwards;
  }
  .menu button.active {
    background: var(--t-accent);
  }
  .menu button.chosen {
    font-weight: 600;
  }
  .menu button.chosen::before {
    content: "■ ";
    font-size: 9px;
    vertical-align: 2px;
  }
  .mono {
    font-family: var(--font-mono);
    font-size: 13px !important;
  }
  @keyframes drop {
    from {
      opacity: 0;
      transform: scaleY(0.6) translateY(-6px);
    }
  }
</style>
