<script lang="ts">
  import { flip } from "svelte/animate";
  import { fly } from "svelte/transition";
  import { dismiss, toasts } from "../lib/toast.svelte";
</script>

<div class="toasts" aria-live="polite">
  {#each toasts as toast (toast.id)}
    <button
      type="button"
      class="toast {toast.kind}"
      animate:flip={{ duration: 300 }}
      in:fly={{ x: 420, duration: 420, opacity: 1, easing: (t) => 1 - Math.pow(1 - t, 4) }}
      out:fly={{ x: 420, duration: 240 }}
      onclick={() => dismiss(toast.id)}
    >
      <span class="tab"></span>
      <span class="text selectable">{toast.text}</span>
    </button>
  {/each}
</div>

<style>
  .toasts {
    position: fixed;
    right: 24px;
    bottom: 24px;
    z-index: 400;
    display: grid;
    gap: 12px;
    width: min(420px, calc(100vw - 48px));
    pointer-events: none;
  }
  .toast {
    pointer-events: auto;
    display: flex;
    align-items: stretch;
    min-height: 52px;
    padding: 0;
    border: var(--t-border-w) solid var(--t-line);
    background: var(--t-surface);
    box-shadow: var(--t-hard);
    text-align: left;
  }
  .tab {
    flex: none;
    width: 14px;
    border-right: 2px solid var(--t-line);
    background: var(--t-accent);
  }
  .ok .tab {
    background: var(--success);
  }
  .error .tab {
    background: var(--error);
  }
  .error {
    box-shadow: 6px 6px 0 var(--error);
  }
  .text {
    padding: 12px 14px;
    font-size: 13.5px;
    overflow-wrap: anywhere;
  }
</style>
