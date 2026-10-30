<script lang="ts">
  import type { Snippet } from "svelte";
  import Icon, { type IconName } from "../../components/Icon.svelte";

  let {
    title,
    icon,
    index = 0,
    children,
  }: { title: string; icon: IconName; index?: number; children: Snippet } = $props();
</script>

<section class="card" style:animation-delay="{index * 70}ms">
  <h2 class="display"><span class="ico"><Icon name={icon} size={18} /></span>{title}</h2>
  <div class="body">{@render children()}</div>
</section>

<style>
  .card {
    display: flex;
    flex-direction: column;
    border: var(--t-border-w) solid var(--t-line);
    background: var(--t-surface);
    box-shadow: var(--t-hard);
    animation: rise 0.5s var(--t-ease) backwards;
    break-inside: avoid;
    margin-bottom: 24px;
  }
  h2 {
    display: flex;
    align-items: center;
    gap: 12px;
    margin: 0;
    padding: 14px 18px;
    border-bottom: var(--t-border-w) solid var(--t-line);
    background: var(--t-bg-2);
    font-size: 22px;
  }
  .ico {
    display: grid;
    place-items: center;
    width: 32px;
    height: 32px;
    border: 2px solid var(--t-line);
    background: var(--t-accent);
    transform: rotate(-5deg);
  }
  .body {
    display: grid;
    gap: 14px;
    padding: 18px;
  }
  .body :global(.hint) {
    margin: 0;
    font-size: 12.5px;
    line-height: 1.5;
    color: var(--dim);
  }
  .body :global(.state) {
    display: flex;
    align-items: center;
    gap: 10px;
    margin: 0;
    font-size: 14px;
  }
  .body :global(.pill) {
    padding: 2px 8px;
    border: 2px solid var(--t-line);
    font: 600 11px var(--font-mono);
    text-transform: uppercase;
  }
  .body :global(.pill.on) {
    background: var(--success);
    border-color: var(--success);
    color: #fff;
  }
  .body :global(.buttons) {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
  }
</style>
