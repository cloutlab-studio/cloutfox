<script lang="ts">
  import type { Snippet } from "svelte";
  import IconButton from "./IconButton.svelte";
  import { t } from "../lib/i18n.svelte";

  let {
    title,
    subtitle,
    onclose,
    children,
    actions,
  }: {
    title: string;
    subtitle?: string;
    onclose: () => void;
    children: Snippet;
    actions?: Snippet;
  } = $props();
</script>

<div class="drawer" role="dialog" aria-modal="true" aria-label={title}>
  <header>
    <div class="titles">
      <h2 class="display">{title}</h2>
      {#if subtitle}<p class="sub">{subtitle}</p>{/if}
    </div>
    <IconButton icon="close" title={t("close_btn")} onclick={onclose} />
  </header>
  <div class="body">{@render children()}</div>
  {#if actions}<footer>{@render actions()}</footer>{/if}
</div>

<style>
  .drawer {
    position: fixed;
    top: 0;
    right: 0;
    bottom: 0;
    width: min(560px, calc(100vw - 80px));
    display: flex;
    flex-direction: column;
    border-left: var(--t-border-w) solid var(--t-line);
    background: var(--t-surface);
    box-shadow: -10px 0 0 var(--t-line);
    animation: slide 0.5s var(--t-ease);
  }
  header {
    display: flex;
    align-items: flex-start;
    gap: 12px;
    padding: 24px 20px 16px 28px;
    border-bottom: var(--t-border-w) solid var(--t-line);
    background: var(--t-accent);
  }
  .titles {
    flex: 1;
    min-width: 0;
  }
  h2 {
    margin: 0;
    font-size: 34px;
    overflow-wrap: anywhere;
  }
  .sub {
    margin: 8px 0 0;
    font-size: 13.5px;
  }
  .body {
    flex: 1;
    display: grid;
    align-content: start;
    gap: 16px;
    padding: 22px 28px 28px;
    overflow: auto;
  }
  footer {
    display: flex;
    justify-content: flex-end;
    gap: 12px;
    padding: 16px 28px;
    border-top: var(--t-border-w) solid var(--t-line);
    background: var(--t-bg);
  }
  @keyframes slide {
    from {
      transform: translateX(110%);
    }
  }
</style>
