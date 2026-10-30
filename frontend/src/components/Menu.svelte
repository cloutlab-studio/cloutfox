<script lang="ts" module>
  import type { IconName } from "./Icon.svelte";
  export type MenuItem = { id: string; label: string; icon: IconName; disabled?: boolean; danger?: boolean };
</script>

<script lang="ts">
  import { play } from "../lib/sound";
  import Icon from "./Icon.svelte";
  import IconButton from "./IconButton.svelte";

  let {
    items,
    title,
    onpick,
  }: { items: MenuItem[]; title: string; onpick: (id: string) => void } = $props();

  let isOpen = $state(false);
  let root: HTMLDivElement;
  let up = $state(false);

  function toggle() {
    isOpen = !isOpen;
    if (isOpen) {
      const box = root.getBoundingClientRect();
      up = window.innerHeight - box.bottom < items.length * 40 + 30;
    }
  }

  $effect(() => {
    if (!isOpen) return;
    const away = (e: PointerEvent) => {
      if (!root.contains(e.target as Node)) isOpen = false;
    };
    const esc = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        isOpen = false;
        e.stopPropagation();
      }
    };
    window.addEventListener("pointerdown", away, true);
    window.addEventListener("keydown", esc, true);
    return () => {
      window.removeEventListener("pointerdown", away, true);
      window.removeEventListener("keydown", esc, true);
    };
  });
</script>

<div class="menu-root" bind:this={root}>
  <IconButton size={32} icon="more" {title} active={isOpen} onclick={toggle} />
  {#if isOpen}
    <ul class="menu" class:up role="menu">
      {#each items as item, i (item.id)}
        <li>
          <button
            type="button"
            role="menuitem"
            disabled={item.disabled}
            class:danger={item.danger}
            data-press
            style:animation-delay="{i * 22}ms"
            onclick={() => {
              isOpen = false;
              play("tap");
              onpick(item.id);
            }}
          >
            <Icon name={item.icon} size={16} />
            <span>{item.label}</span>
          </button>
        </li>
      {/each}
    </ul>
  {/if}
</div>

<style>
  .menu-root {
    position: relative;
  }
  .menu {
    position: absolute;
    z-index: 60;
    top: calc(100% + 6px);
    right: 0;
    min-width: 220px;
    margin: 0;
    padding: 0;
    list-style: none;
    border: 2px solid var(--t-line);
    background: var(--t-surface);
    box-shadow: var(--t-hard-sm);
    transform-origin: top right;
    animation: unfold 0.3s var(--t-ease);
  }
  .menu.up {
    top: auto;
    bottom: calc(100% + 6px);
    transform-origin: bottom right;
  }
  button {
    width: 100%;
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 14px;
    border: 0;
    border-bottom: 1px solid var(--t-bg-2);
    background: transparent;
    text-align: left;
    font-size: 14px;
    white-space: nowrap;
    animation: rise 0.22s var(--t-ease-out) backwards;
  }
  button:hover:not(:disabled) {
    background: var(--t-accent);
  }
  button.danger:hover:not(:disabled) {
    background: var(--error);
    color: #fff;
  }
  button:disabled {
    color: var(--rule-soft);
    cursor: default;
  }
  @keyframes unfold {
    from {
      opacity: 0;
      transform: scale(0.85) rotate(2deg);
    }
  }
</style>
