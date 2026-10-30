<script lang="ts">
  import { play } from "../lib/sound";
  import Icon, { type IconName } from "./Icon.svelte";

  let {
    icon,
    title,
    disabled = false,
    danger = false,
    active = false,
    size = 34,
    onclick,
  }: {
    icon: IconName;
    title: string;
    disabled?: boolean;
    danger?: boolean;
    active?: boolean;
    size?: number;
    onclick?: (e: MouseEvent) => void;
  } = $props();
</script>

<button
  type="button"
  class="ib"
  class:danger
  class:active
  {title}
  aria-label={title}
  {disabled}
  data-press
  style:--s="{size}px"
  onclick={(e) => {
    play("tap");
    onclick?.(e);
  }}
>
  <Icon name={icon} size={Math.round(size * 0.53)} />
</button>

<style>
  .ib {
    width: var(--s);
    height: var(--s);
    display: inline-grid;
    place-items: center;
    padding: 0;
    border: 2px solid transparent;
    background: transparent;
    color: var(--t-muted);
    transition:
      transform var(--t-dur) var(--t-ease),
      background-color var(--t-dur-fast) linear,
      border-color var(--t-dur-fast) linear;
  }
  .ib:hover:not(:disabled),
  .ib.active {
    color: var(--t-fg);
    border-color: var(--t-line);
    background: var(--t-accent);
    transform: rotate(-4deg) scale(1.06);
  }
  .ib.danger:hover:not(:disabled) {
    background: var(--error);
    color: #fff;
  }
  .ib:active:not(:disabled) {
    transform: scale(0.9);
    transition-duration: 0.06s;
  }
  .ib:disabled {
    color: var(--rule-soft);
    cursor: default;
  }
</style>
