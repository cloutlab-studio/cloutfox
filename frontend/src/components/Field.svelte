<script lang="ts">
  import type { Snippet } from "svelte";

  let {
    label,
    hint,
    error,
    children,
  }: { label?: string; hint?: string | null; error?: string | null; children: Snippet } = $props();
</script>

<div class="field">
  {#if label}<span class="label">{label}</span>{/if}
  {@render children()}
  {#if error}
    <span class="error" role="alert">{error}</span>
  {:else if hint}
    <span class="hint">{hint}</span>
  {/if}
</div>

<style>
  .field {
    display: grid;
    align-content: start;
    gap: 6px;
    min-width: 0;
  }
  .hint {
    font-size: 12px;
    color: var(--dim);
  }
  .error {
    font-size: 12.5px;
    font-weight: 600;
    color: var(--error);
    animation: shake 0.4s;
  }
</style>
