<script lang="ts">
  import type { Snippet } from "svelte";
  import { play } from "../lib/sound";
  import Icon, { type IconName } from "./Icon.svelte";

  // accent: yellow, the main action. ink: black (Stop, secondary strong).
  // outline: white with a black rule. danger: red, destructive. ghost: text only.
  type Variant = "accent" | "ink" | "outline" | "danger" | "ghost";

  let {
    variant = "outline",
    icon,
    size = "md",
    disabled = false,
    busy = false,
    wide = false,
    type = "button",
    title,
    sound = true,
    onclick,
    children,
  }: {
    variant?: Variant;
    icon?: IconName;
    size?: "sm" | "md" | "lg";
    disabled?: boolean;
    busy?: boolean;
    wide?: boolean;
    type?: "button" | "submit";
    title?: string;
    sound?: boolean;
    onclick?: (e: MouseEvent) => void;
    children?: Snippet;
  } = $props();

  function click(e: MouseEvent) {
    if (sound) play("tap");
    onclick?.(e);
  }
</script>

<button
  {type}
  {title}
  class="btn {variant} {size}"
  class:wide
  class:busy
  disabled={disabled || busy}
  data-press
  onclick={click}
>
  {#if busy}
    <span class="spin" aria-hidden="true"></span>
  {:else if icon}
    <Icon name={icon} size={size === "sm" ? 15 : 17} />
  {/if}
  {#if children}<span class="text">{@render children()}</span>{/if}
</button>

<style>
  .btn {
    --shadow: 4px;
    position: relative;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    height: 38px;
    padding: 0 14px;
    border: 2px solid var(--t-line);
    border-radius: 0;
    background: var(--t-surface);
    color: var(--t-fg);
    font: 600 12px/1 var(--font-mono);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    white-space: nowrap;
    box-shadow: var(--shadow) var(--shadow) 0 var(--t-line);
    transition:
      transform var(--t-dur) var(--t-ease),
      box-shadow var(--t-dur) var(--t-ease),
      background-color var(--t-dur-fast) linear,
      color var(--t-dur-fast) linear;
  }
  .btn:hover:not(:disabled) {
    transform: translate(-2px, -2px);
    box-shadow: calc(var(--shadow) + 2px) calc(var(--shadow) + 2px) 0 var(--t-line);
  }
  .btn:active:not(:disabled) {
    transform: translate(var(--shadow), var(--shadow));
    box-shadow: 0 0 0 var(--t-line);
    transition-duration: 0.06s;
  }
  .sm {
    height: 30px;
    padding: 0 10px;
    font-size: 11px;
    --shadow: 3px;
  }
  .lg {
    height: 48px;
    padding: 0 22px;
    font-size: 13px;
    --shadow: 6px;
  }
  .wide {
    width: 100%;
  }

  .accent {
    background: var(--t-accent);
    color: var(--t-on-accent);
  }
  .accent:hover:not(:disabled) {
    background: var(--t-accent-2);
  }
  .ink {
    background: var(--t-fg);
    color: var(--t-bg);
  }
  .ink:hover:not(:disabled) {
    background: var(--live);
    color: #fff;
  }
  .outline:hover:not(:disabled) {
    background: var(--t-accent);
  }
  .danger {
    background: var(--error);
    color: #fff;
  }
  .danger:hover:not(:disabled) {
    background: var(--error-deep);
  }
  .ghost {
    border-color: transparent;
    background: transparent;
    box-shadow: none;
  }
  .ghost:hover:not(:disabled) {
    transform: none;
    box-shadow: none;
    text-decoration: underline;
    text-decoration-thickness: 2px;
    text-underline-offset: 4px;
  }

  .btn:disabled {
    cursor: default;
    color: var(--dim);
    background: var(--t-bg-2);
    border-color: var(--rule-soft);
    box-shadow: none;
  }
  .btn.busy:disabled {
    color: var(--t-fg);
    border-color: var(--t-line);
    background: var(--t-surface);
  }

  .spin {
    width: 14px;
    height: 14px;
    border: 2px solid currentColor;
    border-right-color: transparent;
    animation: turn 0.7s linear infinite;
    animation-play-state: var(--loops);
  }
  @keyframes turn {
    to {
      transform: rotate(360deg);
    }
  }
</style>
